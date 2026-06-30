"""
scanner_refactored.py — orchestrator tipis
Logic detail ada di scanner/fetcher.py, scanner/signals.py, scanner/cooldown.py
"""

# ── Adaptive Brain v1 ──
try:
    from adaptive_weights import (
        compute_adaptive_score, compute_confidence,
        extract_components_from_last, get_weight_profile,
        get_position_size_multiplier, get_sl_tp_multiplier,
        should_skip_volatile, CONFIDENCE_THRESHOLD
    )
    ADAPTIVE_AVAILABLE = True
except ImportError as _ae:
    ADAPTIVE_AVAILABLE = False

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from scanner.fetcher  import fetch_with_retry, cast_df, safe_float, apply_rate_limit, get_indicator_cache, set_indicator_cache
from scanner.signals  import calculate_tp_levels, calculate_position_size, get_macd_cross, get_ema_trend, get_volume_label, get_bb_position, get_candle_patterns, calculate_rr_ratio, calculate_trailing_stop
from scanner.cooldown import is_duplicate
from smc_trade_counter import get_smc_counter

try:
    from orderbook_features import get_orderbook_features, ob_score_adjustment
    OB_AVAILABLE = True
except ImportError:
    OB_AVAILABLE = False
try:
    from volume_profile import get_volume_profile, vp_score_adjustment
    VP_AVAILABLE = True
except ImportError:
    VP_AVAILABLE = False
try:
    from liquidity_filter import check_liquidity, liquidity_score_adj
    LIQ_AVAILABLE = True
except ImportError:
    LIQ_AVAILABLE = False
try:
    from smc_scorer import smc_confidence, format_smc_report
    SMC_AVAILABLE = True
except ImportError:
    SMC_AVAILABLE = False

from validators     import validate_signal_dict, validate_trade_params
from config         import WATCHLIST, TIMEFRAMES, PAIR_LIMIT, SIGNAL_THRESHOLD, ACCOUNT_BALANCE, RISK_PER_TRADE
from data_fetcher   import fetch_symbols, get_new_listings, get_volume_spike_pairs, get_top_gainers_losers
from blacklist      import is_blacklisted, get_blacklist, is_in_cooldown
from indicators     import institutional_ai_v4
from market_context import get_market_context, is_btc_dump
from risk_manager   import check_risk_approval, get_risk_status

logger = logging.getLogger(__name__)

MAX_WORKERS      = 10
TASK_TIMEOUT_SEC = 90

VALID_SIGNALS = {"BUY (SETUP)", "SELL (SETUP)", "BUY (REVERSAL)", "SELL (REVERSAL)"}

MIN_CONF = {
    "BUY": 45, "SELL": 15,
    "BUY (SETUP)": 40, "SELL (SETUP)": 20,
    "BUY (REVERSAL)": 50,
}

ADAPTIVE_MULT = {
    "TRENDING": {"BUY": 1.15, "SELL": 1.15},
    "BREAKOUT": {"BUY": 1.25, "SELL": 1.10},
    "RANGING":  {"BUY": 0.85, "SELL": 0.85},
    "VOLATILE": {"BUY": 0.70, "SELL": 0.70},
    "NEUTRAL":  {"BUY": 1.00, "SELL": 1.00},
    "UNKNOWN":  {"BUY": 0.85, "SELL": 0.85},
}

ADAPTIVE_SL_MULT = {
    "TRENDING": 1.0, "BREAKOUT": 1.1,
    "RANGING":  0.8, "VOLATILE": 1.4,
    "NEUTRAL":  1.0, "UNKNOWN":  1.0,
}


def _get_win_rate(symbol, timeframe, signal, last, df) -> float:
    try:
        import sqlite3
        con = sqlite3.connect("signals.db")
        row = con.execute(
            "SELECT ROUND(100.0*SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END)/COUNT(*),1), COUNT(*) "
            "FROM performance WHERE symbol=?", (symbol,)
        ).fetchone()
        con.close()
        db_wr, db_count = (row[0] or 0, row[1] or 0) if row else (0, 0)
    except Exception:
        db_wr, db_count = 0, 0
    if db_count >= 10:
        return db_wr
    try:
        from win_rate_predictor import predict_win_rate
        features = {k: safe_float(last.get(k, 0)) for k in
                    ["rsi","adx","bb_pct","vol_ratio","stoch_k","macd_hist","squeeze_score"]}
        pred = predict_win_rate(symbol, timeframe, signal, features, df_cached=df)
        if not pred.get("is_default"):
            return pred.get("win_rate_pct", 0)
    except Exception:
        pass
    return 0


def _analyse_single(symbol: str, timeframe: str, min_score: float = 0) -> Optional[dict]:
    # Filter leveraged token permanen
    import re
    if re.search(r'(3L|5L|3S|5S|BULL|BEAR|UP|DOWN|HEDGE)USDT$', symbol, re.IGNORECASE):
        return None
    try:
        if is_blacklisted(symbol) or is_in_cooldown(symbol):
            return None

        apply_rate_limit()

        df = fetch_with_retry(symbol, timeframe, limit=300)
        if df is None or len(df) < 100:
            return None
        df = cast_df(df)

        _ind_key = f"{symbol}_{timeframe}_{df.index[-1]}"
        cached   = get_indicator_cache(_ind_key)
        if cached is not None:
            df = cached
        else:
            df = institutional_ai_v4(df)
            set_indicator_cache(_ind_key, df)

        last       = df.iloc[-1]
        signal     = str(last.get("signal", "NO TRADE"))
        confidence = safe_float(last.get("confidence", 0))

        # ── FALLBACK: hanya BUY REVERSAL saat extreme oversold ──
        if signal not in VALID_SIGNALS:
            try:
                from market_context import get_market_context
                _ctx = get_market_context()
                _fg  = _ctx.get("fear_greed", {}).get("value", 50)

                rsi   = safe_float(last.get("rsi", 50))
                macd_h = safe_float(last.get("macd_hist", 0))
                vol_r  = safe_float(last.get("vol_ratio", 1))

                # BUY REVERSAL: extreme fear + RSI oversold + volume spike + MACD mulai naik
                if _fg <= 15 and rsi <= 28 and vol_r >= 2.0 and macd_h > 0:
                    signal     = "BUY (REVERSAL)"
                    confidence = round(30 + (30 - rsi), 1)
                    logger.info(f"[FALLBACK] {symbol}/{timeframe} BUY REVERSAL — RSI={rsi} conf={confidence}")

            except Exception as _fe:
                logger.debug(f"[FALLBACK] {symbol}: {_fe}")

        if signal not in VALID_SIGNALS:
            return None

        _regime = "NEUTRAL"
        regime  = {}
        reg     = "NEUTRAL"
        try:
            from market_context import detect_market_regime
            _reg_info  = detect_market_regime(symbol, timeframe)
            _regime    = _reg_info.get("regime", "NEUTRAL")
            _direction = "BUY" if signal.startswith("BUY") else "SELL"
            _mult      = ADAPTIVE_MULT.get(_regime, {}).get(_direction, 1.0)
            confidence = round(confidence * _mult, 1)
        except Exception as e:
            logger.debug(f"[ADAPTIVE] {symbol}: {e}")

        if confidence < MIN_CONF.get(signal, 35) or confidence < min_score:
            return None

        try:
            from market_context import detect_market_regime
            regime = detect_market_regime(symbol, timeframe)
            reg    = regime.get("regime", "NEUTRAL")

            # Market-aware threshold: SELL lebih mudah lolos saat downtrend
            is_sell = signal.startswith("SELL")
            is_buy  = signal.startswith("BUY")

            # BTC context dari market_context
            from market_context import get_market_context
            _ctx     = get_market_context()
            _btc     = _ctx.get("btc_trend", {}).get("trend", "").upper()
            _fg      = _ctx.get("fear_greed", {}).get("value", 50)
            _is_down = "DOWN" in _btc
            _is_fear = _fg <= 25

            if _is_down and is_sell:
                # Downtrend = SELL peluang bagus, turunkan threshold
                regime_min = 12
                logger.info(f"[REGIME] {symbol} SELL downtrend — threshold diturunkan ke {regime_min}")
            elif _is_down and is_buy:
                # Downtrend = BUY sangat selektif
                regime_min = 65
                logger.info(f"[REGIME] {symbol} BUY saat downtrend — threshold dinaikkan ke {regime_min}")
            elif _is_fear and is_sell:
                # Extreme fear = SELL peluang
                regime_min = 15
            else:
                regime_min = {"TRENDING":30,"BREAKOUT":35,"NEUTRAL":35,"RANGING":45,"VOLATILE":50}.get(reg, 35)

            if confidence < regime_min:
                logger.debug(f"[REGIME] {symbol} conf={confidence} < min={regime_min} ({reg}), skip")
                return None

            # Blok BUY jika downtrend kuat
            if _is_down and "STRONG" in _btc and is_buy and confidence < 70:
                logger.info(f"[REGIME] {symbol} BUY diblok — BTC STRONG DOWNTREND")
                return None

        except Exception as e:
            logger.debug(f"[REGIME] {symbol}: {e}")

        if is_duplicate(symbol, timeframe, signal, confidence):
            return None

        try:
            from data_fetcher import get_realtime_price
            rt    = get_realtime_price(symbol)
            entry = round(rt, 8) if rt and rt > 0 else round(safe_float(last["close"]), 8)
        except Exception:
            entry = round(safe_float(last["close"]), 8)

        _sl_mult = ADAPTIVE_SL_MULT.get(_regime, 1.0)
        sl_raw   = safe_float(last.get("sl", 0))
        if sl_raw == 0:
            atr_val = safe_float(last.get("atr", 0)) * _sl_mult
            if atr_val > 0:
                sl_raw = entry - atr_val if signal.startswith("BUY") else entry + atr_val
            else:
                sl_raw = (entry*(1-0.02*_sl_mult) if signal.startswith("BUY")
                          else entry*(1+0.02*_sl_mult))
        sl = round(sl_raw, 8)
        max_sl = entry * 0.03 * _sl_mult
        if signal.startswith("BUY")      and (entry-sl) > max_sl: sl = round(entry-max_sl, 8)
        if not signal.startswith("BUY") and (sl-entry) > max_sl:  sl = round(entry+max_sl, 8)

        try:
            if timeframe == "1h" and signal.startswith(("BUY","SELL")):
                df_4h = fetch_with_retry(symbol, "4h", limit=100)
                if df_4h is not None and len(df_4h) >= 30:
                    df_4h    = cast_df(df_4h)
                    last_4h  = institutional_ai_v4(df_4h).iloc[-1]
                    c4h, o4h = safe_float(last_4h.get("close",0)), safe_float(last_4h.get("open",0))
                    r4h, s4h = safe_float(last_4h.get("resistance",0)), safe_float(last_4h.get("support",0))
                    penalty  = 0
                    if signal.startswith("BUY")  and c4h<o4h and r4h>0 and abs(c4h-r4h)/c4h<0.01: penalty=15
                    if signal.startswith("SELL") and c4h>o4h and s4h>0 and abs(c4h-s4h)/c4h<0.01: penalty=15
                    if penalty:
                        confidence = max(0, confidence - penalty)
                        logger.info(f"[4H_FILTER] {symbol} penalty -{penalty} conf={confidence}")
        except Exception as e:
            logger.debug(f"[4H_FILTER] {symbol}: {e}")

        smc_bonus, smc_data, smc_report = 0, {}, ""
        if SMC_AVAILABLE:
            try:
                smc_data   = smc_confidence(df, signal=signal)
                smc_bonus  = smc_data.get("score_adjustment", 0)
                smc_report = format_smc_report(smc_data, symbol, signal)
            except Exception as e:
                smc_report = f"SMC error: {e}"

        ob_features, ob_bonus = {}, 0
        if OB_AVAILABLE:
            try:
                ob_features = get_orderbook_features(symbol)
                ob_bonus    = ob_score_adjustment(ob_features, signal)
            except Exception:
                pass

        vp_data, vp_bonus = {}, 0
        if VP_AVAILABLE:
            try:
                vp_data  = get_volume_profile(symbol)
                vp_bonus = vp_score_adjustment(vp_data, signal)
            except Exception:
                pass

        liq_data, liq_adj = {}, 0
        if LIQ_AVAILABLE and ob_features:
            try:
                liq_data = check_liquidity(symbol, ob_features)
                liq_adj  = liquidity_score_adj(liq_data)
                if not liq_data.get("is_liquid", True):
                    logger.debug(f"[LIQ] {symbol} ditolak")
                    return None
            except Exception:
                pass

        # ── Adaptive Brain v1 ──
        if ADAPTIVE_AVAILABLE:
            try:
                _last_dict = last.to_dict() if hasattr(last, "to_dict") else dict(last)
                _components = extract_components_from_last(_last_dict)
                _adap_score, _adap_breakdown, _adap_reason = compute_adaptive_score(_components, _regime)
                _adap_conf, _adap_conf_reason = compute_confidence(
                    regime       = _regime,
                    trend_score  = _components.get("trend_strength", 50),
                    volume_score = _components.get("volume", 50),
                    volatility   = _components.get("volatility", 50),
                    sr_score     = _components.get("support_resistance", 50),
                    liquidity    = min(100, liq_data.get("liq_score", 5) * 10) if liq_data else 50,
                    smc_score    = smc_data.get("score", 0) if smc_data else 0,
                )
                _conf_threshold = CONFIDENCE_THRESHOLD.get(_regime, 55)
                if _adap_conf < _conf_threshold:
                    logger.info(f"[ADAPTIVE] {symbol} SKIP — conf={_adap_conf} < threshold={_conf_threshold} regime={_regime}")
                    return None
                if _regime == "VOLATILE" and should_skip_volatile(_adap_conf):
                    logger.info(f"[ADAPTIVE] {symbol} SKIP VOLATILE — conf={_adap_conf}")
                    return None
                _sl_mult, _tp_mult = get_sl_tp_multiplier(_regime)
                confidence_final = min(100.0, round(
                    (_adap_score * 0.5) + (confidence + smc_bonus + ob_bonus + vp_bonus + liq_adj) * 0.5, 1
                ))
                logger.info(
                    f"[ADAPTIVE] {symbol} | Regime={_regime} | AdapScore={_adap_score} | "
                    f"Conf={_adap_conf} | Threshold={_conf_threshold} | Reason={_adap_reason}"
                )
            except Exception as _ae:
                logger.debug(f"[ADAPTIVE] {symbol} error: {_ae}")
                confidence_final = min(100.0, round(confidence + smc_bonus + ob_bonus + vp_bonus + liq_adj, 1))
        else:
            confidence_final = min(100.0, round(confidence + smc_bonus + ob_bonus + vp_bonus + liq_adj, 1))

        _xgb_prob = 0.5
        try:
            from xgb_trainer import XGBTrainer
            tp1_tmp = entry + abs(entry-sl)*1.5
            _xgb_ok, _xgb_prob, _xgb_reason = XGBTrainer().should_entry(
                signal=signal, timeframe=timeframe,
                entry=entry, sl=sl, tp1=tp1_tmp, min_win_prob=0.52,
            )
            if not _xgb_ok:
                logger.info(f"[XGB] {symbol} SKIP — {_xgb_reason}")
                return None
        except Exception as e:
            logger.debug(f"[XGB] {symbol}: {e}")

        try:
            from dynamic_penalty import get_dynamic_penalty, get_pair_penalty
            dp, dp_r = get_dynamic_penalty(signal, hour=datetime.utcnow().hour, regime=reg)
            pp, pp_r = get_pair_penalty(symbol)
            total_pen = dp + pp
            if total_pen:
                confidence_final = max(0, round(confidence_final + total_pen, 1))
                logger.info(f"[PENALTY] {symbol} {total_pen} → conf={confidence_final}")
            if confidence_final < 45:
                return None
        except Exception as e:
            logger.debug(f"[PENALTY] {symbol}: {e}")

        tp_levels = calculate_tp_levels(
            entry, sl, signal,
            atr=safe_float(last.get("atr", 0)),
            regime=regime.get("regime","NEUTRAL") if isinstance(regime,dict) else "NEUTRAL",
            smc_score=smc_data.get("score", 0) if smc_data else 0,
        )
        tp1 = tp_levels.get("tp1", entry)
        tp2 = tp_levels.get("tp2", entry)
        tp3 = tp_levels.get("tp3", entry)

        # Filter RR minimum dan SL minimum
        _sl_dist_pct = abs(entry - sl) / entry * 100 if entry else 0
        _rr = abs(tp1 - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
        if _rr < 1.5:
            logger.debug(f"[RR_FILTER] {symbol}: RR={_rr:.2f} < 1.5 — skip")
            return None
        if _sl_dist_pct < 0.8:
            logger.debug(f"[SL_FILTER] {symbol}: SL={_sl_dist_pct:.2f}% terlalu dekat — skip")
            return None

        _valid, _vreason = validate_trade_params(entry, sl, tp1, signal)
        if not _valid:
            logger.warning(f"[VALID] {symbol} ditolak: {_vreason}")
            return None

        pos_size = calculate_position_size(entry, sl, RISK_PER_TRADE, ACCOUNT_BALANCE)
        rr_ratio = calculate_rr_ratio(entry, sl, tp1, tp2, tp3)
        trailing = calculate_trailing_stop(entry, safe_float(last.get("atr",0)), signal)
        win_rate = _get_win_rate(symbol, timeframe, signal, last, df)

        get_smc_counter().record_trade(
            symbol=symbol, timeframe=timeframe, signal_type=signal,
            smc_score=smc_data.get("score",0) if smc_data else 0,
            has_smc=SMC_AVAILABLE and bool(smc_data),
        )

        return validate_signal_dict({
            "symbol"           : symbol,
            "timeframe"        : timeframe,
            "signal"           : signal,
            "signal_type"      : signal,
            "confidence"       : round(confidence, 1),
            "confidence_final" : confidence_final,
            "entry"            : entry,
            "sl"               : sl,
            "tp1"              : tp1,
            "tp2"              : tp2,
            "tp3"              : tp3,
            "pos_size"         : pos_size,
            "rsi"              : round(safe_float(last.get("rsi",0)), 2),
            "macd_hist"        : round(safe_float(last.get("macd_hist",0)), 6),
            "macd_cross"       : get_macd_cross(last, df.iloc[-2].to_dict() if len(df)>=2 else None),
            "vol_ratio"        : round(safe_float(last.get("vol_ratio",0)), 2),
            "vol_label"        : get_volume_label(safe_float(last.get("vol_ratio",0))),
            "ema_trend"        : get_ema_trend(last),
            "bb_pos"           : get_bb_position(safe_float(last.get("bb_pct",-1))),
            "candle_pattern"   : get_candle_patterns(last),
            "rr_ratio"         : rr_ratio,
            "trailing_stop"    : trailing,
            "win_rate"         : win_rate,
            "xgb_prob"         : round(_xgb_prob, 3),
            "smc_report"       : smc_report,
            "smc_score"        : smc_data.get("score",0) if smc_data else 0,
            "score"            : confidence_final,
            "score_raw"        : round(confidence, 1),
            "score_final"      : confidence_final,
            "regime"           : _regime,
            "resistance"       : round(safe_float(last.get("resistance",0)), 8),
            "support"          : round(safe_float(last.get("support",0)), 8),
            "pivot"            : round((safe_float(last.get("high",0))+safe_float(last.get("low",0))+safe_float(last.get("close",0)))/3, 8),
        })

    except Exception as e:
        logger.error(f"[ANALYSE] {symbol}/{timeframe} error: {e}", exc_info=True)
        return None


def scan_all_fast(symbols=None, timeframes=None, min_score=0) -> List[dict]:
    if is_btc_dump():
        logger.warning("[SCAN] BTC DUMP — scan dibatalkan")
        return []

    ctx = get_market_context()
    if not ctx.get("allow_buy") and not ctx.get("allow_sell"):
        logger.warning("[SCAN] Market context blok semua sinyal")
        return []

    if symbols is None:
        try:
            symbols = fetch_symbols()[:PAIR_LIMIT]
        except Exception:
            symbols = WATCHLIST or []

    tfs   = timeframes or TIMEFRAMES or ["1h","4h"]
    tasks = [(s,t) for s in symbols for t in tfs if not is_blacklisted(s)]
    total, completed, blocked = len(tasks), 0, 0
    results: List[dict] = []

    logger.info(f"[SCAN] {len(symbols)} pair × {len(tfs)} TF = {total} tasks")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_analyse_single, s, t, min_score): (s,t) for s,t in tasks}
        for fut in as_completed(futures, timeout=TASK_TIMEOUT_SEC*len(tasks)):
            s, t = futures[fut]
            try:
                res = fut.result(timeout=TASK_TIMEOUT_SEC)
                if res:
                    sig = res["signal"]
                    if sig.startswith("BUY")  and not ctx.get("allow_buy"):  blocked+=1; continue
                    if sig.startswith("SELL") and not ctx.get("allow_sell"): blocked+=1; continue
                    res["fear_greed_value"] = ctx.get("fear_greed",{}).get("value","N/A")
                    res["fear_greed_label"] = ctx.get("fear_greed",{}).get("label","N/A")
                    res["fear_greed_emoji"] = ctx.get("fear_greed",{}).get("emoji","")
                    res["btc_trend"]        = ctx.get("btc_trend", {}).get("trend","N/A")
                    res["btc_trend_emoji"]  = ctx.get("btc_trend", {}).get("emoji","")
                    results.append(res)
            except Exception as e:
                logger.debug(f"[SKIP] {s}/{t}: {e}")
            finally:
                completed += 1
                if completed % 10 == 0 or completed == total:
                    print(f"   Progress: {completed}/{total} — sinyal: {len(results)} | blokir: {blocked}")

    logger.info(f"✅ Scan selesai — {len(results)} sinyal | {blocked} diblok")
    return results


def get_dynamic_threshold(ctx, signal_type=None) -> float:
    base = SIGNAL_THRESHOLD
    try:
        from database import get_realtime_winrate
        wr = get_realtime_winrate()
        awr, tot = wr.get("win_rate",0), wr.get("total",0)
        if tot >= 10:
            if awr>=70: base-=5
            elif awr>=60: base-=2
            elif awr<45: base+=8
            elif awr<55: base+=4
    except Exception:
        pass
    fg_raw = ctx.get("fear_greed",50)
    fg     = fg_raw.get("value",50) if isinstance(fg_raw,dict) else int(fg_raw)
    if fg<=15: base+=5
    elif fg<=25: base+=3
    elif fg>=80: base+=5
    elif fg>=60: base-=2
    btc_raw = ctx.get("btc_trend","")
    btc     = btc_raw.get("trend","") if isinstance(btc_raw,dict) else str(btc_raw)
    B       = btc.upper()
    if "DUMP" in B or "CRASH" in B:      base = 999
    elif "STRONG" in B and "DOWN" in B:  base = 999 if signal_type and "BUY" in str(signal_type).upper() else base-5
    elif "DOWN" in B:                    base = base+20 if signal_type and "BUY" in str(signal_type).upper() else base-3
    elif "SIDEWAYS" in B or "WEAK" in B: base += 8
    elif "STRONG" in B and "UP" in B:    base -= 8
    elif "UP" in B:                      base -= 3
    base = max(30, min(95, base))
    logger.info(f"[THRESHOLD] {base} (F&G={fg} BTC={btc} sig={signal_type})")
    return base


def _correlation_filter(signals, max_same_direction=5) -> list:
    buy_count = sell_count = 0
    filtered  = []
    for s in signals:
        sig = s.get("signal","")
        if sig.startswith("BUY"):
            if buy_count >= max_same_direction: continue
            buy_count += 1
        elif sig.startswith("SELL"):
            if sell_count >= max_same_direction: continue
            sell_count += 1
        filtered.append(s)
    return filtered


def get_top_signals(results, top_n=5, threshold=0) -> list:
    if not results: return []
    df = pd.DataFrame(results)
    df = df[df["signal"].isin(VALID_SIGNALS)]
    if threshold > 0: df = df[df["confidence"] >= threshold]
    if df.empty: return []
    sort_col = "confidence_final" if "confidence_final" in df.columns else "confidence"
    df = df.sort_values(sort_col, ascending=False)
    df = df.drop_duplicates(subset=["symbol","timeframe"], keep="first")
    records = df.head(top_n*2).to_dict("records")
    records = _correlation_filter(records, max_same_direction=3)
    return records[:top_n]


def simple_correlation_filter(signals) -> list:
    filtered, seen = [], set()
    for s in signals:
        base = s["symbol"][:3]
        if base in seen: continue
        seen.add(base)
        filtered.append(s)
    return filtered


scan_all = scan_all_fast
