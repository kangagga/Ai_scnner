import logging
import time
import random
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from indicators   import institutional_ai_v4
from market_context import get_market_context, is_btc_dump
from risk_manager   import check_risk_approval, get_risk_status

logger = logging.getLogger(__name__)

MAX_RETRIES        = 3
BASE_DELAY         = 1.5
RATE_LIMIT_PER_SEC = 2
MAX_WORKERS        = 10
TASK_TIMEOUT_SEC   = 90
CACHE_TTL_SEC      = 600

SIGNAL_COOLDOWN = {
    "BUY (SETUP)"    : 60,
    "SELL (SETUP)"   : 60,
    "BUY"            : 45,
    "SELL"           : 45,
    "BUY (REVERSAL)" : 30,
    "SELL (REVERSAL)": 30,
}
DEFAULT_COOLDOWN_MINUTES = 45

VALID_SIGNALS = {
    "BUY", "SELL",
    "BUY (REVERSAL)",
    "BUY (SETUP)", "SELL (SETUP)",
}

_last_signal_state: Dict[str, tuple] = {}
_signal_state_lock = threading.Lock()
_fetch_cache: Dict[str, tuple] = {}
_cache_lock   = threading.Lock()
_indicator_cache: Dict[str, pd.DataFrame] = {}
_rate_limit_lock   = threading.Lock()
_last_request_time: Dict[int, float] = {}

def _cast_df(df):
    for col in ["open","high","low","close","volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open","high","low","close","volume"])

def _safe(val, default=0.0):
    try:
        v = float(val)
        return default if (np.isnan(v) or np.isinf(v)) else v
    except:
        return default

def _get_macd_cross(last, prev=None):
    try:
        hist = _safe(last.get("macd_hist", 0))
        if prev is not None:
            ph = _safe(prev.get("macd_hist", 0))
            if ph <= 0 and hist > 0: return "🟢 Bull Cross"
            if ph >= 0 and hist < 0: return "🔴 Bear Cross"
        return "🟢 Bullish" if hist > 0 else ("🔴 Bearish" if hist < 0 else "Flat")
    except:
        return "N/A"

def _get_ema_trend(last):
    try:
        e9,e20,e50,e200 = (_safe(last.get(k,0)) for k in ["ema9","ema20","ema50","ema200"])
        if e9>e20>e50>e200: return "🟢 Bullish Stack"
        if e9<e20<e50<e200: return "🔴 Bearish Stack"
        if e50>e200: return "🔼 Above EMA200"
        if e50<e200: return "🔽 Below EMA200"
        return "Sideways"
    except:
        return "N/A"

def _calculate_tp_levels(entry, sl, signal):
    tp = {}
    if signal.startswith("BUY"):
        risk = entry - sl
        if risk > 0:
            tp["tp1"] = round(entry + risk*1.5, 8)
            tp["tp2"] = round(entry + risk*2.5, 8)
            tp["tp3"] = round(entry + risk*4.0, 8)
    else:
        risk = sl - entry
        if risk > 0:
            tp["tp1"] = round(entry - risk*1.5, 8)
            tp["tp2"] = round(entry - risk*2.5, 8)
            tp["tp3"] = round(entry - risk*4.0, 8)
    return tp

def _calculate_position_size(entry, sl, risk_pct, balance):
    if entry <= 0 or sl <= 0 or entry == sl: return 0.0
    risk_amount   = balance * risk_pct / 100.0
    stop_distance = abs(entry - sl)
    return round(risk_amount / stop_distance, 6) if stop_distance > 0 else 0.0

def _apply_rate_limit():
    min_interval = 1.0 / RATE_LIMIT_PER_SEC
    with _rate_limit_lock:
        last    = _last_request_time.get(threading.get_ident(), 0)
        elapsed = time.time() - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_request_time[threading.get_ident()] = time.time()

def _cached_fetch(symbol, timeframe, limit=300):
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

def _fetch_with_retry(symbol, timeframe, limit=300):
    for attempt in range(MAX_RETRIES):
        try:
            df = _cached_fetch(symbol, timeframe, limit)
            if df is not None and len(df) >= limit * 0.8:
                return df
        except Exception as e:
            logger.warning(f"Fetch gagal {symbol}/{timeframe} attempt {attempt+1}: {e}")
        time.sleep(BASE_DELAY * (attempt+1) + random.uniform(0,1))
    return None

def _is_duplicate(symbol, timeframe, signal_type, confidence):
    key      = f"{symbol}_{timeframe}"
    now      = datetime.now()
    cooldown = SIGNAL_COOLDOWN.get(signal_type, DEFAULT_COOLDOWN_MINUTES)
    with _signal_state_lock:
        state = _last_signal_state.get(key)
        if state is None:
            _last_signal_state[key] = (signal_type, now)
            return False
        prev_type, last_time = state
        delta = (now - last_time).total_seconds() / 60.0
        if delta < cooldown:
            return True
        _last_signal_state[key] = (signal_type, now)
        return False

def _analyse_single(symbol, timeframe, min_score=0):
    if is_blacklisted(symbol):
        return None

    _apply_rate_limit()
    df = _fetch_with_retry(symbol, timeframe, limit=300)
    if df is None or len(df) < 100:
        return None

    df = _cast_df(df)

    _ind_key = f"{symbol}_{timeframe}_{df.index[-1]}"
    if _ind_key in _indicator_cache:
        df = _indicator_cache[_ind_key]
    else:
        df = institutional_ai_v4(df)
        _indicator_cache[_ind_key] = df
        if len(_indicator_cache) > 300:
            del _indicator_cache[list(_indicator_cache.keys())[0]]

    last       = df.iloc[-1]
    signal     = str(last.get("signal", "NO TRADE"))
    confidence = _safe(last.get("confidence", 0))

    if signal not in VALID_SIGNALS:
        return None

    # ── ADAPTIVE CONFIDENCE MULTIPLIER berdasarkan market regime ──
    try:
        from market_context import detect_market_regime
        _reg_info = detect_market_regime(symbol, timeframe)
        _regime   = _reg_info.get("regime", "NEUTRAL")

        # Multiplier per regime, dibedakan arah sinyal
        ADAPTIVE_MULT = {
            "TRENDING": {"BUY": 1.15, "SELL": 1.15},   # tren kuat — boost ikut arah
            "BREAKOUT": {"BUY": 1.25, "SELL": 1.10},   # breakout — boost breakout BUY lebih besar
            "RANGING":  {"BUY": 0.85, "SELL": 0.85},   # sideways — kurangi confidence trend-following
            "VOLATILE": {"BUY": 0.70, "SELL": 0.70},   # volatil ekstrem — sangat hati-hati
            "NEUTRAL":  {"BUY": 1.00, "SELL": 1.00},
            "UNKNOWN":  {"BUY": 0.50, "SELL": 0.50},   # data tidak jelas — sangat dikurangi
        }
        _direction = "BUY" if signal.startswith("BUY") else "SELL"
        _mult = ADAPTIVE_MULT.get(_regime, {}).get(_direction, 1.0)
        confidence_before_adaptive = confidence
        confidence = round(confidence * _mult, 1)
        logger.debug(
            f"[ADAPTIVE] {symbol}/{timeframe} regime={_regime} dir={_direction} "
            f"mult={_mult}x conf {confidence_before_adaptive:.1f}→{confidence:.1f}"
        )
    except Exception as _e:
        logger.debug(f"[ADAPTIVE] error — {_e}")

    # Min confidence per signal type
    MIN_CONF = {
        "BUY"            : 35,
        "SELL"           : 35,
        "BUY (SETUP)"    : 45,
        "SELL (SETUP)"   : 45,
        "BUY (REVERSAL)" : 55,
    }
    if confidence < MIN_CONF.get(signal, 35):
        return None

    if confidence < min_score:
        return None
    # Market regime filter
    try:
        from market_context import detect_market_regime
        regime = detect_market_regime(symbol, timeframe)
        reg    = regime.get("regime", "NEUTRAL")

        regime_min_conf = {
            "TRENDING" : 35,
            "BREAKOUT" : 38,
            "NEUTRAL"  : 40,
            "RANGING"  : 50,
            "VOLATILE" : 60,
        }.get(reg, 40)

        if confidence < regime_min_conf:
            logger.debug(f"[REGIME] {symbol}/{timeframe}: conf={confidence} < {regime_min_conf} ({reg}), skip")
            return None

        if reg == "TRENDING":
            if signal.startswith("BUY") and not regime.get("bias_buy"):
                logger.debug(f"[REGIME] {symbol}/{timeframe}: BUY diblokir — bias SELL")
                return None
            if signal.startswith("SELL") and not regime.get("bias_sell"):
                logger.debug(f"[REGIME] {symbol}/{timeframe}: SELL diblokir — bias BUY")
                return None

    except Exception as e:
        logger.debug(f"[REGIME] error: {e}")

    if _is_duplicate(symbol, timeframe, signal, confidence):
        return None

    entry  = round(_safe(last["close"]), 8)

    # Adaptive SL multiplier berdasarkan regime — VOLATILE perlu SL lebih lebar,
    # RANGING bisa lebih sempit karena gerak harga terbatas
    ADAPTIVE_SL_MULT = {
        "TRENDING": 1.0,
        "BREAKOUT": 1.1,
        "RANGING":  0.8,
        "VOLATILE": 1.4,
        "NEUTRAL":  1.0,
        "UNKNOWN":  1.0,
    }
    _sl_mult = ADAPTIVE_SL_MULT.get(_regime, 1.0) if '_regime' in dir() else 1.0

    sl_raw = _safe(last.get("sl", 0))
    if sl_raw == 0:
        atr_val = _safe(last.get("atr", 0)) * _sl_mult
        if atr_val > 0:
            sl_raw = entry - atr_val if signal.startswith("BUY") else entry + atr_val
        else:
            sl_raw = entry * (1 - 0.02 * _sl_mult) if signal.startswith("BUY") else entry * (1 + 0.02 * _sl_mult)
    sl = round(sl_raw, 8)

    max_sl = entry * 0.03 * _sl_mult
    if signal.startswith("BUY") and (entry - sl) > max_sl:
        sl = round(entry - max_sl, 8)
    elif not signal.startswith("BUY") and (sl - entry) > max_sl:
        sl = round(entry + max_sl, 8)

    tp_levels = _calculate_tp_levels(entry, sl, signal)
    tp1 = tp_levels.get("tp1", entry)
    tp2 = tp_levels.get("tp2", entry)
    tp3 = tp_levels.get("tp3", entry)

    pos_size   = _calculate_position_size(entry, sl, RISK_PER_TRADE, ACCOUNT_BALANCE)
    macd_cross = _get_macd_cross(last, df.iloc[-2] if len(df) >= 2 else None)
    ema_trend  = _get_ema_trend(last)

    # Field tambahan untuk notif Telegram
    rr_ratio  = 0.0
    risk_dist = abs(entry - sl)
    if risk_dist > 0:
        avg_reward = (abs(tp1-entry) + abs(tp2-entry) + abs(tp3-entry)) / 3.0
        rr_ratio   = round(avg_reward / risk_dist, 2)

    trailing_stop = round(
        entry - 2.0 * _safe(last.get("atr", 0)) if signal.startswith("BUY")
        else entry + 2.0 * _safe(last.get("atr", 0)), 8
    )

    vol_r     = _safe(last.get("vol_ratio", 0))
    vol_label = ("🔥 Very High" if vol_r >= 2.0 else
                 "📈 High"      if vol_r >= 1.5 else
                 "Normal"       if vol_r >= 1.0 else
                 "📉 Low (Dry-Up)")

    bb_pct = _safe(last.get("bb_pct", -1))
    if bb_pct < 0 or bb_pct > 1:
        bb_pos = "N/A"
    elif bb_pct >= 0.95:
        bb_pos = "🔴 Near Upper"
    elif bb_pct <= 0.05:
        bb_pos = "🟢 Near Lower"
    elif bb_pct >= 0.5:
        bb_pos = "Mid-Upper"
    else:
        bb_pos = "Mid-Lower"

    # Candle pattern
    patterns = []
    if last.get("hammer"):        patterns.append("Hammer")
    if last.get("bull_engulf"):   patterns.append("Bull Engulf")
    if last.get("morning_star"):  patterns.append("Morning Star")
    if last.get("shooting_star"): patterns.append("Shooting Star")
    if last.get("bear_engulf"):   patterns.append("Bear Engulf")
    if last.get("evening_star"):  patterns.append("Evening Star")
    candle_pattern = ", ".join(patterns) if patterns else "None"

    # Win rate — gabungkan DB history + AI predictor
    win_rate = 0
    try:
        import sqlite3 as _sq
        _c = _sq.connect("signals.db")
        _r = _c.execute(
            "SELECT ROUND(100.0*SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END)/COUNT(*),1), COUNT(*) FROM performance WHERE symbol=?",
            (symbol,)
        ).fetchone()
        _c.close()
        db_wr    = _r[0] or 0 if _r else 0
        db_count = _r[1] or 0 if _r else 0
    except:
        db_wr = 0; db_count = 0

    if db_count >= 10:
        # Cukup data — pakai DB history
        win_rate = db_wr
    else:
        # Kurang data — pakai AI predictor
        try:
            from win_rate_predictor import predict_win_rate
            features = {
                "rsi"          : _safe(last.get("rsi", 50)),
                "adx"          : _safe(last.get("adx", 0)),
                "bb_pct"       : _safe(last.get("bb_pct", 0.5)),
                "vol_ratio"    : _safe(last.get("vol_ratio", 1)),
                "stoch_k"      : _safe(last.get("stoch_k", 50)),
                "macd_hist"    : _safe(last.get("macd_hist", 0)),
                "squeeze_score": _safe(last.get("squeeze_score", 0)),
            }
            pred = predict_win_rate(symbol, timeframe, signal, features, df_cached=df)
            if not pred.get("is_default"):
                win_rate = pred.get("win_rate_pct", 0)
        except:
            pass

    resistance = round(_safe(last.get("resistance", 0)), 8)
    support    = round(_safe(last.get("support",    0)), 8)
    pivot      = round(
        (_safe(last.get("high",0)) + _safe(last.get("low",0)) + _safe(last.get("close",0))) / 3, 8
    )

    return {
        "symbol"             : symbol,
        "timeframe"          : timeframe,
        "signal"             : signal,
        "signal_type"        : signal,
        "confidence"         : round(confidence, 1),
        "entry"              : entry,
        "sl"                 : sl,
        "tp1"                : tp1,
        "tp2"                : tp2,
        "tp3"                : tp3,
        "pos_size"           : pos_size,
        "rsi"                : round(_safe(last.get("rsi", 0)), 2),
        "macd_hist"          : round(_safe(last.get("macd_hist", 0)), 6),
        "macd_cross"         : macd_cross,
        "vol_ratio"          : round(_safe(last.get("vol_ratio", 0)), 2),
        "stoch_k"            : round(_safe(last.get("stoch_k", 0)), 2),
        "adx"                : round(_safe(last.get("adx", 0)), 2),
        "squeeze_score"      : round(_safe(last.get("squeeze_score", 0)), 1),
        "ema_trend"          : ema_trend,
        "momentum_score"     : 0,
        "win_rate"           : 0,
        "fear_greed_value"   : 0,
        "fear_greed_label"   : "",
        "fear_greed_emoji"   : "",
        "btc_trend"          : "",
        "btc_trend_emoji"    : "",
        "funding_rate"       : "",
        "funding_rate_label" : "N/A",
        "funding_rate_emoji" : "❓",
        "regime"             : "NEUTRAL",
        "regime_emoji"       : "➡️",
        "regime_adx"         : round(_safe(last.get("adx", 0)), 2),
        "regime_advice"      : "",
        "score"              : round(confidence, 1),
        "win_rate"           : win_rate,
        "rr_ratio"           : rr_ratio,
        "trailing_stop"      : trailing_stop,
        "volume_label"       : vol_label,
        "volume_ratio"       : round(vol_r, 2),
        "bb_position"        : bb_pos,
        "candle_pattern"     : candle_pattern,
        "resistance"         : resistance,
        "support"            : support,
        "pivot"              : pivot,
    }

def scan_all_fast(symbols=None, timeframe="all", min_score=0):
    ctx = get_market_context()
    print(f"\n📊 Market Context: {ctx['summary']}")

    from risk_manager import print_risk_status
    print_risk_status()

    if symbols is None:
        try:
            new_listings    = get_new_listings()
            spike_pairs     = get_volume_spike_pairs(top_n=30)
            gainers, losers = get_top_gainers_losers(top_n=10)
            all_symbols     = fetch_symbols()
            combined = gainers + losers + new_listings + spike_pairs + WATCHLIST + all_symbols
            seen, symbols = set(), []
            for s in combined:
                if s not in seen:
                    seen.add(s)
                    symbols.append(s)
            symbols = symbols[:PAIR_LIMIT]
        except Exception:
            symbols = WATCHLIST[:PAIR_LIMIT]

    tfs       = TIMEFRAMES if timeframe == "all" else [timeframe]
    tasks     = [(sym, tf) for sym in symbols for tf in tfs]
    total     = len(tasks)
    results   = []
    blocked   = 0
    completed = 0

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
                        blocked += 1; continue
                    if sig.startswith("SELL") and not ctx["allow_sell"]:
                        blocked += 1; continue

                    res["fear_greed_value"] = ctx["fear_greed"]["value"]
                    res["fear_greed_label"] = ctx["fear_greed"]["label"]
                    res["fear_greed_emoji"] = ctx["fear_greed"]["emoji"]
                    res["btc_trend"]        = ctx["btc_trend"]["trend"]
                    res["btc_trend_emoji"]  = ctx["btc_trend"]["emoji"]
                    results.append(res)

            except Exception as e:
                logger.debug(f"[SKIP] {sym}/{tf}: {e}")
            finally:
                completed += 1
                if completed % 10 == 0 or completed == total:
                    print(f"   Progress: {completed}/{total} — sinyal: {len(results)} | blokir: {blocked}")

    logger.info(f"✅ Scan selesai — {len(results)} sinyal lolos | {blocked} diblokir")
    return results


def get_dynamic_threshold(ctx):
    from config import SIGNAL_THRESHOLD
    base = SIGNAL_THRESHOLD
    try:
        from database import get_realtime_winrate
        wr_data   = get_realtime_winrate()
        actual_wr = wr_data.get("win_rate", 0)
        total     = wr_data.get("total", 0)
        if total >= 10:
            if actual_wr >= 70: base -= 5
            elif actual_wr < 45: base += 5
    except Exception:
        pass

    fg_raw = ctx.get("fear_greed", 50)
    fg = fg_raw.get("value", 50) if isinstance(fg_raw, dict) else int(fg_raw)
    if fg <= 15: base -= 3
    elif fg >= 80: base += 5

    btc_raw = ctx.get("btc_trend", "")
    btc = btc_raw.get("trend", "") if isinstance(btc_raw, dict) else str(btc_raw)
    if "STRONG" in btc: base -= 3

    base = max(30, min(70, base))
    logger.info(f"[THRESHOLD] Dynamic: {base} (F&G={fg}, BTC={btc})")
    return base


def _correlation_filter(signals: list, max_same_direction: int = 5) -> list:
    """Batasi sinyal searah — hindari kirim 10 BUY sekaligus."""
    buy_count = sell_count = 0
    filtered  = []
    for s in signals:
        sig = s.get("signal", "")
        if sig.startswith("BUY"):
            if buy_count >= max_same_direction:
                continue
            buy_count += 1
        elif sig.startswith("SELL"):
            if sell_count >= max_same_direction:
                continue
            sell_count += 1
        filtered.append(s)
    return filtered


def get_top_signals(results, top_n=5, threshold=0):
    if not results:
        return []
    df = pd.DataFrame(results)
    df = df[df["signal"].isin(VALID_SIGNALS)]
    if threshold > 0:
        df = df[df["confidence"] >= threshold]
    if df.empty:
        return []
    df = df.sort_values("confidence", ascending=False)
    df = df.drop_duplicates(subset=["symbol", "timeframe"], keep="first")
    records = df.head(top_n * 2).to_dict("records")
    records = _correlation_filter(records, max_same_direction=3)
    return records[:top_n]

# Alias untuk kompatibilitas main.py
scan_all = scan_all_fast

def simple_correlation_filter(signals):
    filtered = []
    seen = set()

    for s in signals:
        base = s["symbol"][:3]  # simple grouping BTC/ETH/etc
        if base in seen:
            continue
        seen.add(base)
        filtered.append(s)

    return filtered

