"""
scanner/signals.py — TP, SL, labels, patterns
"""
import logging
from typing import Dict
import numpy as np

logger = logging.getLogger(__name__)


def _safe(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        return default if (np.isnan(v) or np.isinf(v)) else v
    except Exception:
        return default


def calculate_tp_levels(entry, sl, signal, atr=0, regime="NEUTRAL", smc_score=0) -> Dict:
    tp = {}
    risk = abs(entry - sl)
    if risk <= 0:
        return tp
    REGIME_MULT = {
        "TRENDING": (2.0, 3.5, 5.5),
        "BREAKOUT": (1.8, 3.0, 5.0),
        "NEUTRAL":  (1.5, 2.5, 4.0),
        "RANGING":  (1.2, 2.0, 3.0),
        "VOLATILE": (1.0, 1.8, 2.8),
    }
    m1, m2, m3 = REGIME_MULT.get(regime, (1.5, 2.5, 4.0))
    if smc_score >= 80:
        m1 += 0.3; m2 += 0.5; m3 += 0.8
    elif smc_score >= 60:
        m1 += 0.1; m2 += 0.2; m3 += 0.4
    if atr > 0:
        min_tp1 = atr * 0.8
        if risk * m1 < min_tp1:
            scale = min_tp1 / (risk * m1)
            m1 *= scale; m2 *= scale; m3 *= scale
    if signal.startswith("BUY"):
        tp["tp1"] = round(entry + risk * m1, 8)
        tp["tp2"] = round(entry + risk * m2, 8)
        tp["tp3"] = round(entry + risk * m3, 8)
    else:
        tp["tp1"] = round(entry - risk * m1, 8)
        tp["tp2"] = round(entry - risk * m2, 8)
        tp["tp3"] = round(entry - risk * m3, 8)
    tp["mult"] = (round(m1,2), round(m2,2), round(m3,2))
    return tp


def calculate_position_size(entry, sl, risk_pct, balance) -> float:
    if entry <= 0 or sl <= 0 or entry == sl:
        return 0.0
    risk_amount   = balance * risk_pct / 100.0
    stop_distance = abs(entry - sl)
    return round(risk_amount / stop_distance, 6) if stop_distance > 0 else 0.0


def get_macd_cross(last: dict, prev: dict = None) -> str:
    try:
        hist = _safe(last.get("macd_hist", 0))
        if prev is not None:
            ph = _safe(prev.get("macd_hist", 0))
            if ph <= 0 and hist > 0: return "🟢 Bull Cross"
            if ph >= 0 and hist < 0: return "🔴 Bear Cross"
        return "🟢 Bullish" if hist > 0 else ("🔴 Bearish" if hist < 0 else "Flat")
    except Exception:
        return "N/A"


def get_ema_trend(last: dict) -> str:
    try:
        e9,e20,e50,e200 = (_safe(last.get(k,0)) for k in ["ema9","ema20","ema50","ema200"])
        if e9>e20>e50>e200: return "🟢 Bullish Stack"
        if e9<e20<e50<e200: return "🔴 Bearish Stack"
        if e50>e200: return "🔼 Above EMA200"
        if e50<e200: return "🔽 Below EMA200"
        return "Sideways"
    except Exception:
        return "N/A"


def get_volume_label(vol_ratio: float) -> str:
    if vol_ratio >= 2.0: return "🔥 Very High"
    if vol_ratio >= 1.5: return "📈 High"
    if vol_ratio >= 1.0: return "Normal"
    return "📉 Low (Dry-Up)"


def get_bb_position(bb_pct: float) -> str:
    if bb_pct < 0 or bb_pct > 1: return "N/A"
    if bb_pct >= 0.95: return "🔴 Near Upper"
    if bb_pct <= 0.05: return "🟢 Near Lower"
    if bb_pct >= 0.5:  return "Mid-Upper"
    return "Mid-Lower"


def get_candle_patterns(last: dict) -> str:
    patterns = []
    if last.get("hammer"):        patterns.append("Hammer")
    if last.get("bull_engulf"):   patterns.append("Bull Engulf")
    if last.get("morning_star"):  patterns.append("Morning Star")
    if last.get("shooting_star"): patterns.append("Shooting Star")
    if last.get("bear_engulf"):   patterns.append("Bear Engulf")
    if last.get("evening_star"):  patterns.append("Evening Star")
    return ", ".join(patterns) if patterns else "None"


def calculate_rr_ratio(entry, sl, tp1, tp2, tp3) -> float:
    risk_dist = abs(entry - sl)
    if risk_dist <= 0:
        return 0.0
    avg_reward = (abs(tp1-entry) + abs(tp2-entry) + abs(tp3-entry)) / 3.0
    return round(avg_reward / risk_dist, 2)


def calculate_trailing_stop(entry, atr, signal) -> float:
    if signal.startswith("BUY"):
        return round(entry - 2.0 * atr, 8)
    return round(entry + 2.0 * atr, 8)
