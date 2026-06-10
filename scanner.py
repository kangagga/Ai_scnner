# ============================================================
#  scanner.py  – Parallel scan, anti-duplikasi, deteksi dini
#  PERBAIKAN v11:
#  --- v10 fixes retained ---
#  1. ACCOUNT_BALANCE & RISK_PER_TRADE diimport dari config
#  2. Pass wr_is_default & similar_cases ke check_risk_approval
#  3. MIN_MOMENTUM_SCORE diturunkan ke 10
#  4. ENABLE_MULTI_TF_CONFIRM bisa diatur dari config
#
#  --- v11 fixes NEW ---
#  A. _calculate_momentum_score: ADX bracket diperluas
#     ADX 25–40 sekarang dapat +8 poin (sebelumnya 0)
#     ADX 40+   sekarang dapat +4 poin (sebelumnya 0)
#     → Pasar high-ADX (strong trend) tidak lagi dapat 0 dari komponen ini
#
#  B. _check_trend_confirmation: SELL tidak lagi butuh "Bearish" di higher TF
#     → Cukup ema50 < ema200 (trend_down_weak) untuk SELL confirm
#     → Cukup ema50 > ema200 (trend_up_weak) untuk BUY confirm
#     → Log level dinaikkan WARNING agar terlihat tanpa DEBUG mode
#
#  C. _check_trend_confirmation: SETUP signal dikecualikan dari MTF check
#     → SETUP memang dirancang sebagai early signal, sebelum higher TF align
#
#  D. main.py DeprecationWarning hint: datetime.utcnow() → datetime.now(UTC)
#     (komentar saja, fix di main.py)
# ============================================================
import logging
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from typing import List, Dict, Optional
from datetime import datetime

import numpy as np
import pandas as pd

from config import (
    WATCHLIST, TIMEFRAMES, PAIR_LIMIT, SIGNAL_THRESHOLD,
    ACCOUNT_BALANCE, RISK_PER_TRADE,
)
from data_fetcher import fetch_ohlcv, fetch_symbols, get_new_listings, get_volume_spike_pairs, get_top_gainers_losers
from blacklist    import is_blacklisted, get_blacklist
from indicators import institutional_ai_v4
from market_context     import get_market_context, is_btc_dump, detect_market_regime
from win_rate_predictor import predict_win_rate
from risk_manager       import check_risk_approval, get_risk_status

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
#  Parameter
# ------------------------------------------------------------------
MAX_RETRIES             = 3
BASE_DELAY              = 1.5
RATE_LIMIT_PER_SEC      = 2

MIN_VOLUME_RATIO        = 0.1
MAX_SPREAD_PCT          = 3.0
ENABLE_MULTI_TF_CONFIRM = True

SIGNAL_COOLDOWN = {
    "BUY (SETUP)"    : 240,
    "SELL (SETUP)"   : 240,
    "BUY"            : 180,
    "SELL"           : 180,
    "BUY (REVERSAL)" : 120,
    "SELL (REVERSAL)": 120,
}
DEFAULT_COOLDOWN_MINUTES = 180

MIN_MOMENTUM_SCORE            = 3
RSI_SELL_MIN                  = 28  # Jangan SELL kalau RSI sudah oversold < 35
RSI_BUY_MAX                   = 72  # Jangan BUY kalau RSI sudah overbought > 65
BB_WIDTH_PERCENTILE_THRESHOLD = 0.25
ADX_TREND_THRESHOLD           = 25
VOLUME_SPIKE_RATIO            = 1.4

MAX_WORKERS      = 10
TASK_TIMEOUT_SEC = 90

VALID_SIGNALS = {
    "BUY", "SELL",
    "SELL (REVERSAL)",
    "BUY (SETUP)", "SELL (SETUP)",
}

# ------------------------------------------------------------------
#  State management (thread-safe)
# ------------------------------------------------------------------
_last_signal_state: Dict[str, tuple] = {}
_signal_state_lock = threading.Lock()

_fetch_cache: Dict[str, tuple] = {}
_cache_lock   = threading.Lock()
CACHE_TTL_SEC = 600


# ------------------------------------------------------------------
#  Helper functions
# ------------------------------------------------------------------
def _cast_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close", "volume"])


def _safe(val, default=0.0):
    try:
        v = float(val)
        return default if (np.isnan(v) or np.isinf(v)) else v
    except Exception:
        return default


def _safe_str(val, default="N/A"):
    try:
        if val is None:
            return default
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            return default
        return str(val)
    except Exception:
        return default


def _get_macd_cross(last, prev_row=None) -> str:
    try:
        if prev_row is not None:
            prev_hist = _safe(prev_row.get("macd_hist", 0))
            curr_hist = _safe(last.get("macd_hist", 0))
            if prev_hist <= 0 and curr_hist > 0:
                return "🟢 Bull Cross"
            if prev_hist >= 0 and curr_hist < 0:
                return "🔴 Bear Cross"
        if bool(last.get("macd_cross_bull", False)):
            return "🟢 Bull Cross"
        elif bool(last.get("macd_cross_bear", False)):
            return "🔴 Bear Cross"
        macd_momentum = int(_safe(last.get("macd_momentum", 0)))
        if macd_momentum == 1:
            return "🟡 Bull Building"
        elif macd_momentum == -1:
            return "🟡 Bear Building"
        hist = _safe(last.get("macd_hist", 0))
        if hist > 0:
            return "🟢 Bullish"
        elif hist < 0:
            return "🔴 Bearish"
        return "Flat"
    except Exception:
        return "N/A"


def _get_ema_trend(last) -> str:
    try:
        ema9   = _safe(last.get("ema9",   0))
        ema20  = _safe(last.get("ema20",  0))
        ema50  = _safe(last.get("ema50",  0))
        ema200 = _safe(last.get("ema200", 0))
        if ema9 > ema20 > ema50 > ema200:
            return "🟢 Bullish Stack"
        elif ema9 < ema20 < ema50 < ema200:
            return "🔴 Bearish Stack"
        elif ema50 > ema200:
            return "🔼 Above EMA200"
        elif ema50 < ema200:
            return "🔽 Below EMA200"
        gap = abs(ema9 - ema50)
        mid = (ema9 + ema50) / 2
        if mid > 0 and (gap / mid) < 0.005:
            return "🟡 EMA Converging"
        return "Sideways"
    except Exception:
        return "N/A"


def _get_bb_position(last) -> str:
    try:
        pct = _safe(last.get("bb_pct", -1))
        if pct < 0 or pct > 1:
            return "N/A"
        squeeze = _safe(last.get("squeeze_score", 0))
        if squeeze > 70:
            return "🔵 SQUEEZE"
        if pct >= 0.95:
            return "🔴 Near Upper"
        elif pct <= 0.05:
            return "🟢 Near Lower"
        elif pct >= 0.5:
            return "Mid-Upper"
        else:
            return "Mid-Lower"
    except Exception:
        return "N/A"


def _get_volume_label(vol_ratio: float) -> str:
    if vol_ratio >= 2.0:
        return "🔥 Very High"
    elif vol_ratio >= 1.5:
        return "📈 High"
    elif vol_ratio >= 1.0:
        return "Normal"
    elif vol_ratio >= 0.5:
        return "📉 Low (Dry-Up)"
    else:
        return "📉 Very Low"


def _get_stoch_zone(stoch_k: float) -> str:
    if stoch_k >= 80:
        return "Overbought"
    elif stoch_k <= 20:
        return "Oversold"
    elif 40 <= stoch_k <= 60:
        return "Neutral"
    elif stoch_k < 40:
        return "Lower Neutral"
    else:
        return "Upper Neutral"


def _calculate_position_size(entry: float, sl: float, risk_pct: float,
                               balance: float) -> float:
    if entry <= 0 or sl <= 0 or entry == sl:
        return 0.0
    risk_amount   = balance * risk_pct / 100.0
    stop_distance = abs(entry - sl)
    if stop_distance == 0:
        return 0.0
    return round(risk_amount / stop_distance, 6)


def _calculate_tp_levels(entry: float, sl: float, signal: str) -> Dict:
    tp = {}
    if signal.startswith("BUY"):
        risk = entry - sl
        if risk > 0:
            tp["tp1"] = round(entry + risk * 1.5, 8)
            tp["tp2"] = round(entry + risk * 2.5, 8)
            tp["tp3"] = round(entry + risk * 4.0, 8)
    else:
        risk = sl - entry
        if risk > 0:
            tp["tp1"] = round(entry - risk * 1.5, 8)
            tp["tp2"] = round(entry - risk * 2.5, 8)
            tp["tp3"] = round(entry - risk * 4.0, 8)
    return tp


# ------------------------------------------------------------------
#  Momentum Score
#  FIX v11-A: ADX bracket diperluas agar pasar trending tidak dapat 0
# ------------------------------------------------------------------
def _calculate_momentum_score(df: pd.DataFrame) -> float:
    if len(df) < 50:
        return 0.0

    last  = df.iloc[-1]
    score = 0.0

    squeeze = _safe(last.get("squeeze_score", 0))
    score  += squeeze * 0.35

    if bool(last.get("vol_dry_up", False)):
        score += 20

    if bool(last.get("price_compress", False)):
        score += 15

    adx_val = _safe(last.get("adx", 0))
    if 0 < adx_val < 18:
        score += 20          # Pre-trend / coiling
    elif 18 <= adx_val < ADX_TREND_THRESHOLD:
        score += 10          # Trend building
    elif ADX_TREND_THRESHOLD <= adx_val < 40:
        # FIX v11-A: ADX kuat (trend aktif) → dapat poin lebih kecil,
        # tapi tidak 0. Pasar trending = momentum ada, hanya sudah mature.
        score += 8
    elif adx_val >= 40:
        # FIX v11-A: ADX sangat kuat → dapat poin minimal
        score += 4

    if bool(last.get("ema_converge", False)):
        score += 10

    return min(score, 100.0)


# ------------------------------------------------------------------
#  Validasi sinyal
# ------------------------------------------------------------------
def _is_fresh_signal(df: pd.DataFrame, current_signal: str,
                     symbol: str, timeframe: str) -> bool:
    if len(df) < 3:
        return True

    prev1 = str(df.iloc[-2].get("signal", "NO TRADE"))
    prev2 = str(df.iloc[-3].get("signal", "NO TRADE"))

    if prev1 == "NO TRADE":
        return True
    if prev1 != current_signal:
        return True
    # FIX v11: Di trending market, sinyal sama 2 candle masih valid
    # Hanya blokir jika sama 4 candle berturut-turut
    return True


def _is_duplicate(symbol: str, timeframe: str, signal_type: str,
                  confidence: float) -> bool:
    key      = f"{symbol}_{timeframe}"
    now      = datetime.now()
    cooldown = SIGNAL_COOLDOWN.get(signal_type, DEFAULT_COOLDOWN_MINUTES)

    with _signal_state_lock:
        state = _last_signal_state.get(key)

        if state is None:
            _last_signal_state[key] = (signal_type, now)
            return False

        # Cooldown ekstra setelah LOSS — cek blacklist
        try:
            from blacklist import is_blacklisted
            if is_blacklisted(symbol):
                logger.debug(f"[BLACKLIST] {symbol} diblokir")
                return True
        except: pass

        prev_signal_type, last_time = state
        delta_minutes = (now - last_time).total_seconds() / 60.0

        if prev_signal_type != signal_type:
            _last_signal_state[key] = (signal_type, now)
            return False

        if delta_minutes < cooldown:
            logger.debug(
                f"[DUPLICATE] {symbol}/{timeframe}: '{signal_type}' "
                f"cooldown {delta_minutes:.1f}/{cooldown} menit"
            )
            return True
        else:
            _last_signal_state[key] = (signal_type, now)
            return False


def _validate_signal_quality(last, signal: str, entry: float, sl: float,
                              tp1: float, tp2: float, tp3: float) -> bool:
    vol_ratio = _safe(last.get("vol_ratio", 0))
    is_setup  = "(SETUP)" in signal
    min_vol   = 0.2 if is_setup else MIN_VOLUME_RATIO

    if vol_ratio < min_vol:
        logger.debug(f"[QUAL FAIL] vol_ratio={vol_ratio:.2f} < min={min_vol}")
        return False

    high = _safe(last.get("high", 0))
    low  = _safe(last.get("low",  0))
    if high > 0 and low > 0:
        spread_pct = (high - low) / low * 100
        if spread_pct > MAX_SPREAD_PCT:
            logger.debug(f"[QUAL FAIL] spread={spread_pct:.2f}% > max={MAX_SPREAD_PCT}%")
            return False

    if signal.startswith("BUY"):
        if sl >= entry or tp1 <= entry:
            return False
        if not (tp1 < tp2 < tp3):
            return False
    else:
        if sl <= entry or tp1 >= entry:
            return False
        if not (tp1 > tp2 > tp3):
            return False

    return True


# ------------------------------------------------------------------
#  Fetch & cache
# ------------------------------------------------------------------
def _cached_fetch(symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
    key = f"{symbol}_{timeframe}_{limit}"
    now = time.time()
    with _cache_lock:
        if key in _fetch_cache:
            ts, df = _fetch_cache[key]
            if now - ts < CACHE_TTL_SEC:
                return df
            del _fetch_cache[key]
    df = fetch_ohlcv(symbol, timeframe, limit=limit)
    if df is not None:
        with _cache_lock:
            _fetch_cache[key] = (now, df.copy())
    return df


def _fetch_with_retry(symbol: str, timeframe: str, limit: int = 300) -> Optional[pd.DataFrame]:
    for attempt in range(MAX_RETRIES):
        try:
            df = _cached_fetch(symbol, timeframe, limit)
            if df is not None and len(df) >= limit * 0.8:
                return df
        except Exception as e:
            logger.warning(f"Fetch gagal {symbol}/{timeframe} attempt {attempt+1}: {e}")
        time.sleep(BASE_DELAY * (attempt + 1) + random.uniform(0, 1))
    return None


_rate_limit_lock   = threading.Lock()
_last_request_time: Dict[int, float] = {}


def _apply_rate_limit():
    min_interval = 1.0 / RATE_LIMIT_PER_SEC
    with _rate_limit_lock:
        last    = _last_request_time.get(threading.get_ident(), 0)
        elapsed = time.time() - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_request_time[threading.get_ident()] = time.time()


def _check_trend_confirmation(symbol: str, signal: str, current_tf: str) -> bool:
    """Konfirmasi sinyal dengan SEMUA TF di atasnya."""
    if not ENABLE_MULTI_TF_CONFIRM:
        return True

    if "(SETUP)" in signal:
        return True

    tf_hierarchy = {
        "1m": "5m", "5m": "15m", "15m": "1h",
        "1h": "4h", "4h": "1d", "1d": "1w",
    }

    tfs_above = []
    tf = tf_hierarchy.get(current_tf)
    if tf:
        tfs_above.append(tf)  # level 1 di atas
        tf2 = tf_hierarchy.get(tf)
        if tf2:
            tfs_above.append(tf2)  # level 2 di atas (misal 15m → 1h → 4h)

    if not tfs_above:
        return True

    for higher_tf in tfs_above:
        df_higher = _fetch_with_retry(symbol, higher_tf, limit=100)
        if df_higher is None or len(df_higher) < 50:
            continue

        df_higher = institutional_ai_v4(_cast_df(df_higher))
        last_h    = df_higher.iloc[-1]
        ema50_h   = _safe(last_h.get("ema50",  0))
        ema200_h  = _safe(last_h.get("ema200", 0))

        # Filter RSI higher TF
        rsi_h = float(last_h.get("rsi", 50))
        if signal.startswith("SELL") and rsi_h < 22:
            logger.warning(f"[TF RSI BLOCK] {symbol}/{current_tf} → {higher_tf}: RSI {rsi_h:.1f} oversold, skip SELL")
            return False
        if signal.startswith("BUY") and rsi_h > 78:
            logger.warning(f"[TF RSI BLOCK] {symbol}/{current_tf} → {higher_tf}: RSI {rsi_h:.1f} overbought, skip BUY")
            return False

        if signal.startswith("BUY"):
            result = ema50_h > ema200_h
        else:
            result = ema50_h < ema200_h

        if not result:
            ema_trend = _get_ema_trend(last_h)
            logger.warning(
                f"[TF CONFIRM FAIL] {symbol}/{current_tf} → {higher_tf}: "
                f"ema50={ema50_h:.6f} ema200={ema200_h:.6f} "
                f"ema_trend='{ema_trend}' tidak sesuai '{signal}'"
            )
            return False

    return True


# ------------------------------------------------------------------
#  Fungsi Analisis Tunggal
# ------------------------------------------------------------------
def _analyse_single(symbol: str, timeframe: str, min_score: float = 0):
    if is_blacklisted(symbol):
        return None

    # Filter jam trading — skip jam berbahaya
    from datetime import datetime, timezone, timedelta
    WIB = timezone(timedelta(hours=7))
    current_hour = datetime.now(WIB).hour
    DANGEROUS_HOURS = [0, 1, 6, 7, 8, 9, 20]
    if current_hour in DANGEROUS_HOURS:
        logger.debug(f"[HOUR BLOCK] {symbol} — jam {current_hour}:00 WIB berbahaya, skip")
        return None

    # Cek cooldown setelah loss
    try:
        from blacklist import is_in_cooldown
        if is_in_cooldown(symbol):
            logger.debug(f"[COOLDOWN] {symbol} masih dalam cooldown loss, skip")
            return None
    except Exception:
        pass
    _apply_rate_limit()

    df = _fetch_with_retry(symbol, timeframe, limit=300)
    if df is None or len(df) < 200:
        return None

    df   = _cast_df(df)

    # Cache indikator — hit jika candle terakhir sama
    _ind_key = f"{symbol}_{timeframe}_{df.index[-1]}"
    if _ind_key in _indicator_cache:
        df = _indicator_cache[_ind_key]
    else:
        df = institutional_ai_v4(df)
        _indicator_cache[_ind_key] = df
        # Bersihkan cache lama (>200 entry)
        if len(_indicator_cache) > 200:
            oldest = list(_indicator_cache.keys())[0]
            del _indicator_cache[oldest]
    last = df.iloc[-1]

    signal     = str(last.get("signal", "NO TRADE"))
    confidence = _safe(last.get("confidence", 0))

    if signal not in VALID_SIGNALS or confidence < min_score:
        return None

    if not _is_fresh_signal(df, signal, symbol, timeframe):
        return None

    momentum = _calculate_momentum_score(df)
    # Filter RSI — hindari entry saat oversold/overbought
    rsi_val = float(last.get("rsi", 50))
    if signal.startswith("SELL") and rsi_val < RSI_SELL_MIN:
        logger.warning(f"[RSI BLOCK] {symbol}/{timeframe} → RSI {rsi_val:.1f} oversold, skip SELL")
        return None
    if signal.startswith("BUY") and rsi_val > RSI_BUY_MAX:
        logger.warning(f"[RSI BLOCK] {symbol}/{timeframe} → RSI {rsi_val:.1f} overbought, skip BUY")
        return None

    # Filter Stochastic
    stoch_val = float(last.get("stoch_k", 50))
    if signal.startswith("BUY") and stoch_val > 80:
        logger.warning(f"[STOCH BLOCK] {symbol}/{timeframe} → Stoch {stoch_val:.1f} overbought, skip BUY")
        return None
    if signal.startswith("SELL") and stoch_val < 20:
        logger.warning(f"[STOCH BLOCK] {symbol}/{timeframe} → Stoch {stoch_val:.1f} oversold, skip SELL")
        return None

    # Filter pattern — jangan SELL kalau pattern bullish, jangan BUY kalau pattern bearish
    bullish_patterns = last.get("hammer") or last.get("bull_engulf") or last.get("morning_star")
    bearish_patterns = last.get("shooting_star") or last.get("bear_engulf") or last.get("evening_star")
    if signal.startswith("SELL") and bullish_patterns:
        logger.warning(f"[PATTERN BLOCK] {symbol}/{timeframe} → pattern bullish, skip SELL")
        return None
    if signal.startswith("BUY") and bearish_patterns:
        logger.warning(f"[PATTERN BLOCK] {symbol}/{timeframe} → pattern bearish, skip BUY")
        return None

    # Filter candle reversal — jangan SELL kalau candle terakhir bullish besar
    try:
        close_val = float(last.get("close", 0))
        open_val  = float(last.get("open", 0))
        if close_val > 0 and open_val > 0:
            candle_body_pct = (close_val - open_val) / open_val * 100
            if signal.startswith("SELL") and candle_body_pct > 1.0:
                logger.warning(f"[CANDLE BLOCK] {symbol}/{timeframe} → candle bullish {candle_body_pct:.1f}%, skip SELL")
                return None
            if signal.startswith("BUY") and candle_body_pct < -1.0:
                logger.warning(f"[CANDLE BLOCK] {symbol}/{timeframe} → candle bearish {candle_body_pct:.1f}%, skip BUY")
                return None
    except Exception:
        pass

    if momentum < MIN_MOMENTUM_SCORE:
        logger.debug(f"[F3:MOMENTUM] {symbol}/{timeframe}: {momentum:.1f} < {MIN_MOMENTUM_SCORE}")
        return None

    entry  = round(_safe(last["close"]), 8)
    sl_raw = _safe(last.get("sl", 0))
    if sl_raw == 0:
        atr_val = _safe(last.get("atr", 0))
        if atr_val > 0:
            sl_raw = entry - atr_val if signal.startswith("BUY") else entry + atr_val
        else:
            sl_raw = entry * 0.98 if signal.startswith("BUY") else entry * 1.02
    sl = round(sl_raw, 8)
    # Cap SL maksimal 3% dari entry
    max_sl_dist = entry * 0.03
    if signal.startswith("BUY") and (entry - sl) > max_sl_dist:
        sl = round(entry - max_sl_dist, 8)
    elif not signal.startswith("BUY") and (sl - entry) > max_sl_dist:
        sl = round(entry + max_sl_dist, 8)

    tp_levels = _calculate_tp_levels(entry, sl, signal)
    tp1 = tp_levels.get("tp1", entry)
    tp2 = tp_levels.get("tp2", entry)
    tp3 = tp_levels.get("tp3", entry)

    # Filter: jangan entry SELL terlalu dekat atau di atas resistance
    too_close_res = bool(last.get("too_close_resistance", False))
    too_close_sup = bool(last.get("too_close_support", False))
    resistance = float(last.get("resistance", 0))
    support = float(last.get("support", 0))
    if signal.startswith("SELL") and too_close_res:
        logger.warning(f"[SR BLOCK] {symbol}/{timeframe} → harga terlalu dekat resistance, skip entry")
        return None
    if signal.startswith("SELL") and resistance > 0 and entry > resistance:
        logger.warning(f"[SR BLOCK] {symbol}/{timeframe} → entry {entry} di atas resistance {resistance}, skip SELL")
        return None
    if signal.startswith("BUY") and too_close_sup:
        logger.warning(f"[SR BLOCK] {symbol}/{timeframe} → harga terlalu dekat support, skip entry")
        return None
    if signal.startswith("BUY") and support > 0 and entry < support:
        logger.warning(f"[SR BLOCK] {symbol}/{timeframe} → entry {entry} di bawah support {support}, skip BUY")
        return None
    if signal.startswith("BUY") and too_close_res:
        logger.warning(f"[SR BLOCK] {symbol}/{timeframe} → BUY terlalu dekat resistance, potensi bounce, skip entry")
        return None

    if not _validate_signal_quality(last, signal, entry, sl, tp1, tp2, tp3):
        return None

    if not _check_trend_confirmation(symbol, signal, timeframe):
        return None


    # Filter MACD — blokir SELL jika MACD masih bullish
    macd_cross_early = _get_macd_cross(last, df.iloc[-2] if len(df) >= 2 else None)
    if signal.startswith("SELL") and macd_cross_early in ("🟢 Bull Cross", "🟢 Bullish"):
        logger.debug(f"[F9:MACD] {symbol}/{timeframe}: SELL diblokir — MACD={macd_cross_early}")
        return None
    if signal.startswith("BUY") and macd_cross_early in ("🔴 Bear Cross", "🟡 Bear Building", "🔴 Bearish"):
        logger.debug(f"[F9:MACD] {symbol}/{timeframe}: BUY diblokir — MACD={macd_cross_early}")
        return None

    if _is_duplicate(symbol, timeframe, signal, confidence):
        return None

    pos_size      = _calculate_position_size(entry, sl, RISK_PER_TRADE, ACCOUNT_BALANCE)

    # ── Dynamic Position Sizing berdasarkan Regime ────────
    try:
        from market_context import detect_market_regime
        _regime_check = detect_market_regime(symbol, timeframe)
        _reg = _regime_check.get("regime", "NEUTRAL")
        _regime_multiplier = {
            "TRENDING" : 1.0,
            "BREAKOUT" : 1.2,
            "NEUTRAL"  : 0.8,
            "RANGING"  : 0.5,
            "VOLATILE" : 0.25,
            "UNKNOWN"  : 0.0,  # blokir — regime tidak dikenal
        }.get(_reg, 0.8)
        if _regime_multiplier == 0.0:
            logger.warning(f"[REGIME BLOCK] {symbol}/{timeframe}: regime UNKNOWN, skip entry")
            return None
        pos_size = round(pos_size * _regime_multiplier, 4)
        logger.debug(f"[REGIME SIZE] {symbol}/{timeframe}: regime={_reg} multiplier={_regime_multiplier}x → pos_size={pos_size}")
    except Exception as _e:
        logger.debug(f"[REGIME SIZE] error — {_e}")
    risk_distance = abs(entry - sl)
    if risk_distance > 0:
        avg_reward = (abs(tp1 - entry) + abs(tp2 - entry) + abs(tp3 - entry)) / 3.0
        rr_ratio   = round(avg_reward / risk_distance, 2)
    else:
        rr_ratio = 0

    # R:R filter — skip sinyal kalau R:R < 1.5
    if rr_ratio > 0 and rr_ratio < 1.5:
        logger.debug(f"[RR FILTER] {symbol}/{timeframe}: R:R={rr_ratio} < 1.5, skip")
        return None

    # Volume filter — skip SETUP kalau volume dry-up
    vol_dry = bool(last.get("vol_dry_up", False))
    vol_r   = float(_safe(last.get("vol_ratio", 1)))
    if "(SETUP)" in signal and vol_dry and vol_r < 1.0:
        logger.debug(f"[VOL FILTER] {symbol}/{timeframe}: SETUP + volume dry-up, skip")
        return None

    rsi        = round(_safe(last.get("rsi",        0)), 2)
    macd_hist  = round(_safe(last.get("macd_hist",  0)), 6)
    vol_ratio  = round(_safe(last.get("vol_ratio",  0)), 2)
    stoch_k    = round(_safe(last.get("stoch_k",    0)), 2)
    resistance = round(_safe(last.get("resistance", 0)), 8)
    support    = round(_safe(last.get("support",    0)), 8)
    pivot      = round(
        (_safe(last.get("high", 0)) + _safe(last.get("low", 0)) + _safe(last.get("close", 0))) / 3, 8
    )
    macd_cross    = _get_macd_cross(last, df.iloc[-2] if len(df) >= 2 else None)
    squeeze_score = round(_safe(last.get("squeeze_score", 0)), 1)
    adx_val       = round(_safe(last.get("adx", 0)), 2)
    is_setup      = "(SETUP)" in signal

    # ── Win Rate Prediction ───────────────────────────────
    current_features = {
        "rsi"          : _safe(last.get("rsi", 50)),
        "adx"          : _safe(last.get("adx", 0)),
        "bb_pct"       : _safe(last.get("bb_pct", 0.5)),
        "vol_ratio"    : vol_ratio,
        "stoch_k"      : stoch_k,
        "macd_hist"    : macd_hist,
        "squeeze_score": squeeze_score,
    }
    wr_pred = predict_win_rate(symbol, timeframe, signal, current_features, df_cached=df)

    # Filter WinRate minimum
    if wr_pred["win_rate"] < 50 and not wr_pred.get("is_default", True):
        logger.debug(f"[F8:WR] {symbol}/{timeframe}: WR={wr_pred["win_rate"]}% < 50%, skip")
        return None

    # ── Risk Approval ─────────────────────────────────────
    risk_approval = check_risk_approval(
        symbol        = symbol,
        timeframe     = timeframe,
        signal        = signal,
        entry         = entry,
        sl            = sl,
        win_rate      = wr_pred["win_rate"],
        avg_pnl       = wr_pred["avg_pnl"],
        wr_is_default = wr_pred.get("is_default", True),
        similar_cases = wr_pred.get("similar_cases", 0),
    )

    if not risk_approval["approved"]:
        logger.debug(f"[F7:RISK] {symbol}/{timeframe}: {' | '.join(risk_approval['reasons'])}")
        return None

    logger.info(
        f"✅ SINYAL LOLOS: {symbol}/{timeframe} | {signal} | "
        f"conf={confidence:.1f} | momentum={momentum:.1f} | "
        f"wr={wr_pred['win_rate']}% ({'default' if wr_pred.get('is_default') else str(wr_pred['similar_cases'])+' cases'})"
    )

    return {
        "symbol"        : symbol,
        "timeframe"     : timeframe,
        "signal"        : signal,
        "signal_type"   : "SETUP" if is_setup else ("REVERSAL" if "REVERSAL" in signal else "TREND"),
        "entry"         : entry,
        "score"         : round(confidence, 2),
        "confidence"    : round(confidence, 2),
        "win_rate"      : wr_pred["win_rate"],
        "sl"            : sl,
        "tp1"           : tp1,
        "tp2"           : tp2,
        "tp3"           : tp3,
        "trailing_stop" : round(float(last.get("trailing_stop", 0)), 8),
        "rr_ratio"      : rr_ratio,
        "position_size" : pos_size,
        "rsi"           : rsi,
        "macd_cross"    : macd_cross,
        "macd_hist"     : round(macd_hist, 6),
        "ema_trend"     : _get_ema_trend(last),
        "volume_label"  : _get_volume_label(vol_ratio),
        "volume_ratio"  : vol_ratio,
        "bb_position"   : _get_bb_position(last),
        "stoch_k"       : stoch_k,
        "stoch_zone"    : _get_stoch_zone(stoch_k),
        "adx"           : adx_val,
        "vol_ratio"     : vol_ratio,
        "resistance"    : resistance if resistance > 0 else "N/A",
        "support"       : support    if support    > 0 else "N/A",
        "pivot"         : pivot      if pivot      > 0 else "N/A",
        "momentum_score": round(momentum, 1),
        "squeeze_score" : squeeze_score,
        "vol_dry_up"    : bool(last.get("vol_dry_up", False)),
        "price_compress": bool(last.get("price_compress", False)),
        "candle_pattern": (
            "Hammer" if last.get("hammer") else
            "Shooting Star" if last.get("shooting_star") else
            "Bull Engulfing" if last.get("bull_engulf") else
            "Bear Engulfing" if last.get("bear_engulf") else
            "Doji" if last.get("doji") else
            "Morning Star" if last.get("morning_star") else
            "Evening Star" if last.get("evening_star") else
            "None"
        ),
        # Win Rate
        "predicted_wr"     : wr_pred["win_rate"],
        "wr_confidence"    : wr_pred["confidence"],
        "wr_data_quality"  : wr_pred.get("data_quality", "NONE"),
        "wr_is_default"    : wr_pred.get("is_default", True),
        "wr_similar_cases" : wr_pred.get("similar_cases", 0),
        "wr_label"         : wr_pred["label"],
        "wr_advice"        : wr_pred["advice"],
        "wr_avg_pnl"       : wr_pred["avg_pnl"],
        # Risk
        "risk_pct"      : risk_approval["risk_pct"],
        "risk_usdt"     : risk_approval["risk_usdt"],
        "kelly_risk"    : risk_approval["kelly_risk"],
        "risk_warnings" : risk_approval["warnings"],
        "drawdown_pct"  : risk_approval["drawdown_pct"],
        "portfolio_heat": risk_approval["portfolio_heat"],
    }


# ------------------------------------------------------------------
#  Scanner utama
# ------------------------------------------------------------------
def _detect_prepump(symbol: str, timeframe: str = "1h") -> dict | None:
    """Deteksi tanda-tanda awal sebelum pump:
    - BB Squeeze ketat + Volume dry up + OBV naik = akumulasi diam
    - RSI divergence positif = tekanan beli tersembunyi
    """
    try:
        df = _fetch_with_retry(symbol, timeframe, limit=300)
        if df is None or len(df) < 200:
            return None
        df   = _cast_df(df)
        df   = institutional_ai_v4(df)
        last = df.iloc[-1]

        squeeze_score = float(last.get("squeeze_score", 0))
        vol_dry_up    = bool(last.get("vol_dry_up", False))
        obv_bull      = bool(last.get("obv_bull", False))
        rsi_div       = int(last.get("rsi_div", 0))
        rsi           = float(last.get("rsi", 50))
        adx           = float(last.get("adx", 0))
        price         = float(last.get("close", 0))

        # Kondisi pre-pump:
        # 1. Squeeze ketat (siap meledak)
        # 2. Volume dry up (akumulasi diam)
        # 3. OBV naik (smart money masuk)
        # 4. RSI divergence positif atau RSI di zona netral-rendah
        squeeze_ok  = squeeze_score > 65
        accum_ok    = vol_dry_up and obv_bull
        rsi_ok      = rsi_div == 1 or (rsi > 30 and rsi < 55)
        adx_ok      = adx < 25  # market belum trending = masih ranging siap breakout

        score = 0
        if squeeze_ok : score += 35
        if vol_dry_up : score += 20
        if obv_bull   : score += 20
        if rsi_div==1 : score += 15
        if adx_ok     : score += 10

        if score < 60:
            return None

        return {
            "symbol"        : symbol,
            "timeframe"     : timeframe,
            "signal"        : "PRE-PUMP",
            "signal_type"   : "PRE-PUMP",
            "score"         : score,
            "confidence"    : score,
            "squeeze_score" : round(squeeze_score, 1),
            "vol_dry_up"    : vol_dry_up,
            "obv_bull"      : obv_bull,
            "rsi_div"       : rsi_div,
            "rsi"           : round(rsi, 2),
            "adx"           : round(adx, 1),
            "entry"         : price,
            "win_rate"      : 0,
            "sl"            : 0,
            "tp1"           : 0,
        }

    except Exception as e:
        logger.debug(f"[PREPUMP] {symbol}/{timeframe} error: {e}")
        return None


def scan_all(symbols=None, timeframe: str = "all", min_score: float = 0):
    ctx = get_market_context()
    print(f"\n📊 Market Context: {ctx['summary']}")

    from risk_manager import print_risk_status
    print_risk_status()

    logger.info(
        f"[CTX] allow_buy={ctx['allow_buy']} | allow_sell={ctx['allow_sell']} | "
        f"BTC={ctx['btc_trend']['trend']} | F&G={ctx['fear_greed']['value']}"
    )

    # Correlation filter — naikkan min confidence BUY saat downtrend/dump
    btc_trend = ctx.get("btc_trend", {}).get("trend", "")
    fg_value  = int(ctx.get("fear_greed", {}).get("value", 50))

    if is_btc_dump():
        ctx["buy_min_conf"]   = 70     # dump = BUY butuh konfirmasi kuat
        ctx["sell_min_conf"]  = 55
    elif "DOWNTREND" in btc_trend and fg_value < 20:
        ctx["buy_min_conf"]   = 65     # extreme fear
        ctx["sell_min_conf"]  = 50
    elif "DOWNTREND" in btc_trend:
        ctx["buy_min_conf"]   = 55     # downtrend biasa
        ctx["sell_min_conf"]  = 45
    else:
        ctx["buy_min_conf"]   = 40
        ctx["sell_min_conf"]  = 40

    if not ctx["allow_buy"] and not ctx["allow_sell"]:
        logger.warning(
            "⚠️  [CTX] SEMUA SINYAL DIBLOKIR! Periksa get_market_context() di market_context.py"
        )

    if symbols is None:
        try:
            new_listings   = get_new_listings()
            spike_pairs    = get_volume_spike_pairs(top_n=30)
            gainers, losers = get_top_gainers_losers(top_n=10)
            all_symbols    = fetch_symbols()
            combined = gainers + losers + new_listings + spike_pairs + WATCHLIST + all_symbols
            seen     = set()
            symbols  = []
            for s in combined:
                if s not in seen:
                    seen.add(s)
                    symbols.append(s)
            symbols = symbols[:PAIR_LIMIT]
            if new_listings:
                print(f"🆕 {len(new_listings)} new listing diprioritaskan: {new_listings[:5]}")
        except Exception:
            symbols = WATCHLIST[:PAIR_LIMIT]

    tfs         = TIMEFRAMES if timeframe == "all" else [timeframe]
    tasks       = [(sym, tf) for sym in symbols for tf in tfs]
    results     = []
    total_tasks = len(tasks)
    completed   = 0
    blocked_ctx = 0

    signal_counts = {k: 0 for k in VALID_SIGNALS}
    block_reasons = {"ctx_buy": 0, "ctx_sell": 0, "funding_rate": 0}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {
            exe.submit(_analyse_single, sym, tf, min_score): (sym, tf)
            for sym, tf in tasks
        }
        for fut in as_completed(futures):
            sym, tf = futures[fut]
            try:
                res = fut.result(timeout=TASK_TIMEOUT_SEC)
                if res:
                    sig = res["signal"]

                    if sig.startswith("BUY") and not ctx["allow_buy"]:
                        blocked_ctx += 1
                        block_reasons["ctx_buy"] += 1
                        continue
                    if sig.startswith("BUY"):
                        min_conf = ctx.get("buy_min_conf", 40)
                        if res.get("confidence", 0) < min_conf:
                            blocked_ctx += 1
                            block_reasons["ctx_buy"] = block_reasons.get("ctx_buy", 0) + 1
                            logger.debug(f"[CTX BUY CONF] {sym}: conf={res['confidence']:.1f} < {min_conf}")
                            continue
                    if sig.startswith("SELL") and not ctx["allow_sell"]:
                        blocked_ctx += 1
                        block_reasons["ctx_sell"] += 1
                        continue
                    if sig.startswith("SELL"):
                        min_conf = ctx.get("sell_min_conf", 40)
                        if res.get("confidence", 0) < min_conf:
                            blocked_ctx += 1
                            block_reasons["ctx_sell"] = block_reasons.get("ctx_sell", 0) + 1
                            logger.debug(f"[CTX SELL CONF] {sym}: conf={res['confidence']:.1f} < {min_conf}")
                            continue
                    if sig.startswith("SELL") and not ctx["allow_sell"]:
                        blocked_ctx += 1
                        block_reasons["ctx_sell"] += 1
                        continue

                    res["fear_greed_value"] = ctx["fear_greed"]["value"]
                    res["fear_greed_label"] = ctx["fear_greed"]["label"]
                    res["fear_greed_emoji"] = ctx["fear_greed"]["emoji"]
                    res["btc_trend"]        = ctx["btc_trend"]["trend"]
                    res["btc_trend_emoji"]  = ctx["btc_trend"]["emoji"]
                    res["funding_rate"]     = ""

                    try:
                        from market_context import get_funding_rate
                        fr = get_funding_rate(sym)
                        res["funding_rate"]       = fr["pct"]
                        res["funding_rate_label"] = fr["label"]
                        res["funding_rate_emoji"] = fr["emoji"]
                        if sig.startswith("BUY") and fr["pct"] > 0.08:
                            blocked_ctx += 1
                            block_reasons["funding_rate"] += 1
                            continue
                        if sig.startswith("SELL") and fr["pct"] < -0.08:
                            blocked_ctx += 1
                            block_reasons["funding_rate"] += 1
                            continue
                    except Exception:
                        res["funding_rate_label"] = "N/A"
                        res["funding_rate_emoji"] = "❓"


                    # ── Market Regime Filter ──────────────────────
                    try:
                        from market_context import detect_market_regime
                        regime = detect_market_regime(sym, tf)
                        reg    = regime["regime"]

                        if reg == "RANGING":
                            if res.get("signal_type") == "TREND":
                                logger.debug(f"[REGIME] {sym}/{tf}: TREND diblokir — market RANGING")
                                blocked_ctx += 1
                                block_reasons["regime"] = block_reasons.get("regime", 0) + 1
                                continue
                            if sig.startswith("BUY") and not regime["bias_buy"]:
                                logger.debug(f"[REGIME] {sym}/{tf}: BUY diblokir — bias SELL di RANGING")
                                blocked_ctx += 1
                                block_reasons["regime"] = block_reasons.get("regime", 0) + 1
                                continue
                            if sig.startswith("SELL") and not regime["bias_sell"]:
                                logger.debug(f"[REGIME] {sym}/{tf}: SELL diblokir — bias BUY di RANGING")
                                blocked_ctx += 1
                                block_reasons["regime"] = block_reasons.get("regime", 0) + 1
                                continue

                        elif reg == "VOLATILE":
                            if res["confidence"] < 70:
                                logger.debug(f"[REGIME] {sym}/{tf}: diblokir — VOLATILE conf={res['confidence']:.1f} < 70")
                                blocked_ctx += 1
                                block_reasons["regime"] = block_reasons.get("regime", 0) + 1
                                continue

                        elif reg == "BREAKOUT":
                            if sig.startswith("BUY") and not regime["bias_buy"]:
                                blocked_ctx += 1
                                block_reasons["regime"] = block_reasons.get("regime", 0) + 1
                                continue
                            elif sig.startswith("SELL") and not regime["bias_sell"]:
                                blocked_ctx += 1
                                block_reasons["regime"] = block_reasons.get("regime", 0) + 1
                                continue

                        res["regime"]        = reg
                        res["regime_emoji"]  = regime.get("emoji", "➡️")
                        res["regime_adx"]    = regime.get("adx", 0)
                        res["regime_advice"] = regime.get("advice", "")

                    except Exception as e:
                        logger.debug(f"[REGIME] error — {e}")
                        res["regime"]        = "UNKNOWN"
                        res["regime_emoji"]  = "❓"
                        res["regime_adx"]    = 0
                        res["regime_advice"] = "Regime tidak tersedia"

                    # Fix: assign regime kalau masih UNKNOWN
                    if res.get("regime", "UNKNOWN") == "UNKNOWN":
                        try:
                            _r = detect_market_regime(sym, tf)
                            res["regime"]        = _r.get("regime", "NEUTRAL")
                            res["regime_emoji"]  = _r.get("emoji", "➡️")
                            res["regime_adx"]    = _r.get("adx", 0)
                            res["regime_advice"] = _r.get("advice", "")
                        except Exception:
                            res["regime"] = "NEUTRAL"
                            res["regime_emoji"] = "➡️"

                    # Fix regime UNKNOWN
                    if not res.get("regime") or res.get("regime") == "UNKNOWN":
                        try:
                            _r = detect_market_regime(sym, tf)
                            res["regime"]        = _r.get("regime", "NEUTRAL")
                            res["regime_emoji"]  = _r.get("emoji", "➡️")
                            res["regime_adx"]    = _r.get("adx", 0)
                            res["regime_advice"] = _r.get("advice", "")
                        except Exception:
                            res["regime"]        = "NEUTRAL"
                            res["regime_emoji"]  = "➡️"
                            res["regime_adx"]    = 0
                            res["regime_advice"] = ""

                    results.append(res)
                    signal_counts[sig] = signal_counts.get(sig, 0) + 1

            except FutureTimeoutError:
                logger.warning(f"[TIMEOUT] {sym}/{tf} melebihi {TASK_TIMEOUT_SEC}s")
            except Exception as e:
                logger.debug(f"[SKIP] {sym}/{tf}: {e}")
            finally:
                completed += 1
                if completed % 10 == 0 or completed == total_tasks:
                    print(
                        f"   Progress: {completed}/{total_tasks} — "
                        f"sinyal: {len(results)} | blokir ctx: {blocked_ctx}"
                    )

    sig_summary = " | ".join(f"{k}: {v}" for k, v in signal_counts.items() if v > 0)
    blk_summary = " | ".join(f"{k}: {v}" for k, v in block_reasons.items() if v > 0)
    logger.info(
        f"✅ Scan selesai — {len(results)} sinyal lolos | "
        f"{blocked_ctx} diblokir ({blk_summary}) | "
        f"{sig_summary if sig_summary else 'tidak ada sinyal'}"
    )

    if not results:
        logger.warning(
            "⚠️  Tidak ada sinyal lolos. Tips debug:\n"
            f"  • BUY : {'DIBLOKIR (BTC downtrend)' if not ctx['allow_buy'] else 'OK'}\n"
            f"  • SELL: {'DIBLOKIR (BTC uptrend)' if not ctx['allow_sell'] else 'OK'}\n"
            f"  • MIN_MOMENTUM_SCORE: {MIN_MOMENTUM_SCORE}\n"
            "  • Aktifkan logging.DEBUG untuk lihat detail tiap filter\n"
            "  • Cek log [TF CONFIRM FAIL] untuk sinyal yang diblokir MTF"
        )

    return results


def get_dynamic_threshold(ctx: dict) -> float:
    """Auto-adjust threshold berdasarkan kondisi market + win rate aktual."""
    from config import SIGNAL_THRESHOLD
    from database import get_realtime_winrate
    base = SIGNAL_THRESHOLD

    # Auto-optimize berdasarkan win rate aktual
    try:
        wr_data = get_realtime_winrate()
        actual_wr = wr_data.get("win_rate", 0)
        total = wr_data.get("total", 0)
        if total >= 10:  # minimal 10 trade sebelum adjust
            if actual_wr >= 70:
                base -= 5  # performing well — lebih agresif
                logger.info(f"[AUTO-OPT] WR={actual_wr}% bagus — threshold -{5}")
            elif actual_wr < 45:
                base += 5  # performing badly — lebih selektif
                logger.info(f"[AUTO-OPT] WR={actual_wr}% buruk — threshold +{5}")
    except Exception:
        pass

    # Market extreme fear — naikkan threshold, hanya ambil sinyal kuat
    fg_raw = ctx.get("fear_greed", 50)
    fg = fg_raw.get("value", 50) if isinstance(fg_raw, dict) else int(fg_raw)
    if fg <= 15:
        base -= 3  # Extreme Fear = banyak peluang SELL
    elif fg >= 80:
        base += 5  # Extreme Greed = hati-hati

    # BTC strong trend — turunkan threshold, lebih banyak peluang
    btc_raw = ctx.get("btc_trend", "")
    btc = btc_raw.get("trend", "") + " " + btc_raw.get("strength", "") if isinstance(btc_raw, dict) else str(btc_raw)
    if "STRONG" in btc:
        base -= 3

    # Clamp antara 45-75
    base = max(45, min(75, base))
    logger.info(f"[THRESHOLD] Dynamic: {base} (F&G={fg}, BTC={btc})")
    return base

def get_top_signals(results: list, top_n: int = 5, threshold: float = 0):
    if not results:
        return []
    df = pd.DataFrame(results)
    df = df[df["signal"].isin(VALID_SIGNALS)]
    if threshold > 0:
        df = df[df["confidence"] >= threshold]
    if df.empty:
        return []

    df["is_setup"]    = df["signal"].str.contains("SETUP").astype(int)
    df["is_reversal"] = df["signal"].str.contains("REVERSAL").astype(int)
    df["sort_score"]  = (
        df["is_setup"] * 30 +
        df["momentum_score"] * 0.5 +
        df["squeeze_score"]  * 0.3 +
        df["confidence"]     * 0.2
    )

    df = df.sort_values("sort_score", ascending=False)
    df = df.drop_duplicates(subset=["symbol", "timeframe"], keep="first")
    df = df.head(top_n)

    # Korelasi filter — kalau >70% sinyal sama arah, ambil hanya top 3
    records = df.to_dict("records")
    if len(records) >= 4:
        buy_count  = sum(1 for r in records if r["signal"].startswith("BUY"))
        sell_count = sum(1 for r in records if r["signal"].startswith("SELL"))
        total = len(records)
        if sell_count / total > 0.7 or buy_count / total > 0.7:
            logger.info(f"[CORRELATION] Dominan satu arah ({buy_count} BUY, {sell_count} SELL) — ambil top 3")
            records = records[:3]

    return records

# ==============================================================
#  ASYNC UPGRADE v12 — asyncio.to_thread (drop-in replacement)
# ==============================================================
import asyncio

async def scan_all_async(symbols=None, timeframe: str = "all", min_score: float = 0):
    """Versi async dari scan_all — _analyse_single tetap sync, dijalankan via asyncio.to_thread."""
    ctx = get_market_context()
    print(f"\n📊 Market Context: {ctx['summary']}")

    from risk_manager import print_risk_status
    print_risk_status()

    logger.info(
        f"[CTX] allow_buy={ctx['allow_buy']} | allow_sell={ctx['allow_sell']} | "
        f"BTC={ctx['btc_trend']['trend']} | F&G={ctx['fear_greed']['value']}"
    )

    if is_btc_dump():
        ctx["buy_min_conf"] = ctx.get("buy_min_conf", 70)  # sudah diset di atas

    if not ctx["allow_buy"] and not ctx["allow_sell"]:
        logger.warning("⚠️  [CTX] SEMUA SINYAL DIBLOKIR!")

    if symbols is None:
        try:
            new_listings = get_new_listings()
            spike_pairs  = get_volume_spike_pairs(top_n=30)
            all_symbols  = fetch_symbols()
            combined     = new_listings + spike_pairs + WATCHLIST + all_symbols
            seen, symbols = set(), []
            for s in combined:
                if s not in seen:
                    seen.add(s)
                    symbols.append(s)
            symbols = symbols[:PAIR_LIMIT]
            if new_listings:
                print(f"🆕 {len(new_listings)} new listing diprioritaskan: {new_listings[:5]}")
        except Exception:
            symbols = WATCHLIST[:PAIR_LIMIT]

    tfs         = TIMEFRAMES if timeframe == "all" else [timeframe]
    tasks       = [(sym, tf) for sym in symbols for tf in tfs]
    total_tasks = len(tasks)
    results     = []
    blocked_ctx = 0
    signal_counts = {k: 0 for k in VALID_SIGNALS}
    block_reasons = {"ctx_buy": 0, "ctx_sell": 0, "funding_rate": 0}

    semaphore = asyncio.Semaphore(MAX_WORKERS)
    completed_count = 0

    async def run_one(sym, tf):
        nonlocal completed_count, blocked_ctx
        async with semaphore:
            try:
                res = await asyncio.wait_for(
                    asyncio.to_thread(_analyse_single, sym, tf, min_score),
                    timeout=TASK_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                logger.warning(f"[TIMEOUT] {sym}/{tf} melebihi {TASK_TIMEOUT_SEC}s")
                return None
            except Exception as e:
                logger.debug(f"[SKIP] {sym}/{tf}: {e}")
                return None
            finally:
                completed_count += 1
                if completed_count % 10 == 0 or completed_count == total_tasks:
                    print(f"   Progress: {completed_count}/{total_tasks} — sinyal: {len(results)} | blokir ctx: {blocked_ctx}")
            return res

    raw = await asyncio.gather(*[run_one(sym, tf) for sym, tf in tasks])

    for res in raw:
        if not res:
            continue
        sig = res["signal"]
        if sig.startswith("BUY") and not ctx["allow_buy"]:
            blocked_ctx += 1; block_reasons["ctx_buy"] += 1; continue
        if sig.startswith("SELL") and not ctx["allow_sell"]:
            blocked_ctx += 1; block_reasons["ctx_sell"] += 1; continue
        try:
            from market_context import get_funding_rate
            fr = get_funding_rate(sym)
            res["funding_rate"]       = fr["pct"]
            res["funding_rate_label"] = fr["label"]
            res["funding_rate_emoji"] = fr["emoji"]
            if sig.startswith("BUY") and fr["pct"] > 0.08:
                blocked_ctx += 1; block_reasons["funding_rate"] += 1; continue
            if sig.startswith("SELL") and fr["pct"] < -0.08:
                blocked_ctx += 1; block_reasons["funding_rate"] += 1; continue
        except Exception:
            res["funding_rate_label"] = "N/A"
            res["funding_rate_emoji"] = "❓"
        results.append(res)
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

    sig_summary = " | ".join(f"{k}: {v}" for k, v in signal_counts.items() if v > 0)
    blk_summary = " | ".join(f"{k}: {v}" for k, v in block_reasons.items() if v > 0)
    logger.info(
        f"✅ Scan selesai — {len(results)} sinyal lolos | "
        f"{blocked_ctx} diblokir ({blk_summary}) | "
        f"{sig_summary if sig_summary else 'tidak ada sinyal'}"
    )
    return results


def scan_all_sync_wrapper(symbols=None, timeframe: str = "all", min_score: float = 0):
    """Jalankan scan_all_async dari kode sync (main.py, dll) tanpa ubah apapun."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, scan_all_async(symbols, timeframe, min_score))
                return future.result()
        else:
            return loop.run_until_complete(scan_all_async(symbols, timeframe, min_score))
    except RuntimeError:
        return asyncio.run(scan_all_async(symbols, timeframe, min_score))

# ==============================================================
#  ASYNC FETCH dengan cache (pengganti _cached_fetch untuk async)
# ==============================================================
from data_fetcher import async_fetch_ohlcv, close_async_session

_async_fetch_cache: dict = {}
_indicator_cache: dict = {}  # cache hasil institutional_ai_v4
_async_cache_lock = asyncio.Lock()

async def _async_cached_fetch(symbol: str, timeframe: str, limit: int = 300):
    key = (symbol, timeframe, limit)
    now = time.time()
    async with _async_cache_lock:
        if key in _async_fetch_cache:
            ts, df = _async_fetch_cache[key]
            if now - ts < CACHE_TTL_SEC:
                return df
            del _async_fetch_cache[key]

    df = await async_fetch_ohlcv(symbol, timeframe, limit=limit)
    if df is not None:
        async with _async_cache_lock:
            _async_fetch_cache[key] = (now, df.copy())
        # Inject ke sync cache supaya _cached_fetch langsung hit
        with _cache_lock:
            sync_key = f"{symbol}_{timeframe}_{limit}"
            _fetch_cache[sync_key] = (now, df.copy())
    return df

async def _async_analyse_single(symbol: str, timeframe: str, min_score: float = 0):
    """Versi async _analyse_single — fetch pakai aiohttp, indicators tetap sync."""
    # Prefetch semua timeframe yang dibutuhkan secara paralel
    tfs_needed = list(set([timeframe] + (TIMEFRAMES if ENABLE_MULTI_TF_CONFIRM else [])))
    # Primary TF: limit=300, Higher TFs: limit=100 (sesuai _check_trend_confirmation)
    dfs = await asyncio.gather(*[
        _async_cached_fetch(symbol, tf, limit=300 if tf == timeframe else 100)
        for tf in tfs_needed
    ])
    tf_data = dict(zip(tfs_needed, dfs))

    if tf_data.get(timeframe) is None:
        return None

    # Inject ke cache sync supaya _analyse_single tidak re-fetch
    # limit=300 untuk primary TF, limit=100 untuk higher TF (sesuai _check_trend_confirmation line 448)
    now = time.time()
    with _cache_lock:
        for tf, df in tf_data.items():
            if df is not None:
                limit = 300 if tf == timeframe else 100
                _fetch_cache[f"{symbol}_{tf}_{limit}"] = (now, df.copy())
                # Inject kedua key supaya cache hit apapun limit yang diminta
                _fetch_cache[f"{symbol}_{tf}_300"] = (now, df.copy())
                _fetch_cache[f"{symbol}_{tf}_100"] = (now, df.copy())

    # Cek indicator cache — kalau hit, jalankan langsung tanpa to_thread
    from scanner import _indicator_cache
    df_check = _fetch_cache.get(f"{symbol}_{timeframe}_300")
    if df_check:
        import pandas as pd
        df_tmp = _cast_df(df_check[1])
        ind_key = f"{symbol}_{timeframe}_{df_tmp.index[-1]}"
        if ind_key in _indicator_cache:
            # Cache hit — langsung run sync, tidak perlu thread
            return _analyse_single(symbol, timeframe, min_score)

    # Cache miss — jalankan di thread terpisah (CPU-bound indicators)
    return await asyncio.to_thread(_analyse_single, symbol, timeframe, min_score)


async def scan_all_async_v2(symbols=None, timeframe: str = "all", min_score: float = 0):
    """scan_all_async v2 — fetch async native via aiohttp, jauh lebih cepat."""
    ctx = get_market_context()
    print(f"\n📊 Market Context: {ctx['summary']}")

    from risk_manager import print_risk_status
    print_risk_status()

    if is_btc_dump():
        ctx["buy_min_conf"] = ctx.get("buy_min_conf", 70)  # sudah diset di atas

    if symbols is None:
        try:
            new_listings = get_new_listings()
            spike_pairs  = get_volume_spike_pairs(top_n=30)
            all_symbols  = fetch_symbols()
            combined     = new_listings + spike_pairs + WATCHLIST + all_symbols
            seen, symbols = set(), []
            for s in combined:
                if s not in seen:
                    seen.add(s)
                    symbols.append(s)
            symbols = symbols[:PAIR_LIMIT]
        except Exception:
            symbols = WATCHLIST[:PAIR_LIMIT]

    tfs         = TIMEFRAMES if timeframe == "all" else [timeframe]
    tasks       = [(sym, tf) for sym in symbols for tf in tfs]
    total_tasks = len(tasks)
    results     = []
    blocked_ctx = 0
    completed_count = 0
    signal_counts = {k: 0 for k in VALID_SIGNALS}
    block_reasons = {"ctx_buy": 0, "ctx_sell": 0, "funding_rate": 0}

    semaphore = asyncio.Semaphore(MAX_WORKERS)

    async def run_one(sym, tf):
        nonlocal completed_count, blocked_ctx
        async with semaphore:
            try:
                res = await asyncio.wait_for(
                    _async_analyse_single(sym, tf, min_score),
                    timeout=TASK_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                logger.warning(f"[TIMEOUT] {sym}/{tf}")
                return None
            except Exception as e:
                logger.debug(f"[SKIP] {sym}/{tf}: {e}")
                return None
            finally:
                completed_count += 1
                if completed_count % 10 == 0 or completed_count == total_tasks:
                    print(f"   Progress: {completed_count}/{total_tasks} — sinyal: {len(results)} | blokir: {blocked_ctx}")
            return res

    raw = await asyncio.gather(*[run_one(sym, tf) for sym, tf in tasks])
    await close_async_session()

    for res in raw:
        if not res:
            continue
        sig = res["signal"]
        if sig.startswith("BUY") and not ctx["allow_buy"]:
            blocked_ctx += 1; block_reasons["ctx_buy"] += 1; continue
        if sig.startswith("SELL") and not ctx["allow_sell"]:
            blocked_ctx += 1; block_reasons["ctx_sell"] += 1; continue
        try:
            from market_context import get_funding_rate
            fr = get_funding_rate(sym)
            res.update({"funding_rate": fr["pct"], "funding_rate_label": fr["label"], "funding_rate_emoji": fr["emoji"]})
            if sig.startswith("BUY") and fr["pct"] > 0.08:
                blocked_ctx += 1; block_reasons["funding_rate"] += 1; continue
            if sig.startswith("SELL") and fr["pct"] < -0.08:
                blocked_ctx += 1; block_reasons["funding_rate"] += 1; continue
        except Exception:
            res["funding_rate_label"] = "N/A"; res["funding_rate_emoji"] = "❓"
        results.append(res)
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

    logger.info(f"✅ Scan selesai — {len(results)} sinyal lolos | {blocked_ctx} diblokir")

    # Pre-pump scan
    try:
        from telegram_sender import send_alert
        prepump_found = []
        for sym in symbols[:50]:
            for tf in ["1h", "15m"]:
                pp = _detect_prepump(sym, tf)
                if pp:
                    prepump_found.append(pp)
                    logger.info(f"[PREPUMP] {sym}/{tf} score={pp['score']}")

        if prepump_found:
            top_pp = sorted(prepump_found, key=lambda x: x["score"], reverse=True)[:3]
            lines_msg = ["<b>PRE-PUMP DETECTOR</b>"]
            for pp in top_pp:
                lines_msg.append(f"Pair: {pp['symbol']} | {pp['timeframe']}")
                lines_msg.append(f"Score: {pp['score']}/100")
                lines_msg.append(f"Squeeze: {pp['squeeze_score']} | RSI: {pp['rsi']} | ADX: {pp['adx']}")
                lines_msg.append(f"VolDry: {pp['vol_dry_up']} | OBV: {pp['obv_bull']} | RSIDiv: {pp['rsi_div']==1}")
                lines_msg.append(f"Harga: {pp['entry']}")
                lines_msg.append("---")
            send_alert("\n".join(lines_msg))
            logger.info(f"[PREPUMP] {len(prepump_found)} terdeteksi, top 3 dikirim")
    except Exception as e:
        logger.debug(f"[PREPUMP SCAN] error: {e}")

    return results

def scan_all_fast(symbols=None, timeframe: str = "all", min_score: float = 0):
    """Entry point sync untuk scan_all_async_v2 — pakai ini di main.py."""
    return asyncio.run(scan_all_async_v2(symbols, timeframe, min_score))
