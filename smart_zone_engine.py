"""
smart_zone_engine.py — Smart Money Zone Engine
Institutional AI v9 | SMC Layer
"""
import numpy as np
import pandas as pd
from zone_detector import detect_zones


def detect_fvg(df: pd.DataFrame) -> dict:
    """
    Fair Value Gap (FVG) Detection.
    Bullish FVG: high[i-2] < low[i]
    Bearish FVG: low[i-2] > high[i]
    """
    bullish_fvg = []
    bearish_fvg = []

    if df is None or len(df) < 3:
        return {"bullish": [], "bearish": []}

    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values

    for i in range(2, len(df)):
        # Bullish FVG: gap antara high candle i-2 dan low candle i
        if highs[i-2] < lows[i]:
            bullish_fvg.append({
                "index"  : i,
                "high"   : round(lows[i], 8),
                "low"    : round(highs[i-2], 8),
                "mid"    : round((lows[i] + highs[i-2]) / 2, 8),
                "filled" : False,
            })

        # Bearish FVG: gap antara low candle i-2 dan high candle i
        if lows[i-2] > highs[i]:
            bearish_fvg.append({
                "index"  : i,
                "high"   : round(lows[i-2], 8),
                "low"    : round(highs[i], 8),
                "mid"    : round((lows[i-2] + highs[i]) / 2, 8),
                "filled" : False,
            })

    # Filter FVG yang belum terisi
    current_price = closes[-1]
    bullish_fvg = [f for f in bullish_fvg
                   if not f["filled"] and current_price > f["low"] * 0.98]
    bearish_fvg = [f for f in bearish_fvg
                   if not f["filled"] and current_price < f["high"] * 1.02]

    # Sort terdekat
    bullish_fvg = sorted(bullish_fvg,
                         key=lambda x: abs(current_price - x["mid"]))[:3]
    bearish_fvg = sorted(bearish_fvg,
                         key=lambda x: abs(current_price - x["mid"]))[:3]

    return {"bullish": bullish_fvg, "bearish": bearish_fvg}


def detect_liquidity_sweep(df: pd.DataFrame, lookback: int = 20) -> dict:
    """
    Deteksi Liquidity Sweep (Stop Hunt).
    sweep_low  → potensi BUY
    sweep_high → potensi SELL
    """
    if df is None or len(df) < lookback + 2:
        return {"sweep_low": False, "sweep_high": False, "score": 0}

    recent    = df.iloc[-lookback-2:-2]
    last      = df.iloc[-1]
    prev      = df.iloc[-2]

    swing_low  = recent["low"].min()
    swing_high = recent["high"].max()

    sweep_low  = False
    sweep_high = False

    # Sweep low: harga tembus bawah swing low tapi close di atas
    if prev["low"] < swing_low and prev["close"] > swing_low:
        sweep_low = True

    # Sweep high: harga tembus atas swing high tapi close di bawah
    if prev["high"] > swing_high and prev["close"] < swing_high:
        sweep_high = True

    score = 10 if (sweep_low or sweep_high) else 0

    return {
        "sweep_low"  : sweep_low,
        "sweep_high" : sweep_high,
        "swing_low"  : round(swing_low, 8),
        "swing_high" : round(swing_high, 8),
        "score"      : score,
    }


def detect_market_structure(df: pd.DataFrame) -> dict:
    """
    Deteksi struktur market: HH/HL (bullish) atau LH/LL (bearish).
    """
    if df is None or len(df) < 10:
        return {"structure": "NEUTRAL", "score": 0}

    highs  = df["high"].values[-10:]
    lows   = df["low"].values[-10:]

    # Cek Higher High Higher Low
    hh = highs[-1] > highs[-3] > highs[-5]
    hl = lows[-1]  > lows[-3]  > lows[-5]

    # Cek Lower High Lower Low
    lh = highs[-1] < highs[-3] < highs[-5]
    ll = lows[-1]  < lows[-3]  < lows[-5]

    if hh and hl:
        return {"structure": "BULLISH", "score": 15}
    elif lh and ll:
        return {"structure": "BEARISH", "score": 15}
    elif hh or hl:
        return {"structure": "WEAK_BULLISH", "score": 8}
    elif lh or ll:
        return {"structure": "WEAK_BEARISH", "score": 8}
    else:
        return {"structure": "NEUTRAL", "score": 0}


def get_fvg_score(df: pd.DataFrame, signal: str) -> float:
    """Return score 0-20 untuk FVG proximity."""
    fvg = detect_fvg(df)
    current_price = df["close"].iloc[-1]

    if signal.startswith("BUY"):
        for gap in fvg["bullish"]:
            proximity = abs(current_price - gap["mid"]) / (current_price + 1e-9)
            if proximity < 0.015:
                return 20
            elif proximity < 0.03:
                return 12
        return 0

    elif signal.startswith("SELL"):
        for gap in fvg["bearish"]:
            proximity = abs(current_price - gap["mid"]) / (current_price + 1e-9)
            if proximity < 0.015:
                return 20
            elif proximity < 0.03:
                return 12
        return 0

    return 0


def get_smc_analysis(df: pd.DataFrame, signal: str) -> dict:
    """
    Full SMC analysis — gabungkan semua komponen.
    Returns dict lengkap untuk dipakai di scanner.
    """
    zones     = detect_zones(df)
    fvg       = detect_fvg(df)
    sweep     = detect_liquidity_sweep(df)
    structure = detect_market_structure(df)

    fvg_score  = get_fvg_score(df, signal)
    zone_score = 0

    current_price = df["close"].iloc[-1]

    if signal.startswith("BUY"):
        for zone in zones["demand"]:
            prox = abs(current_price - zone["mid"]) / (current_price + 1e-9)
            if prox < 0.02:
                zone_score = min(zone["strength"], 20)
                break
        bias_ok = structure["structure"] in ["BULLISH", "WEAK_BULLISH"]
    else:
        for zone in zones["supply"]:
            prox = abs(current_price - zone["mid"]) / (current_price + 1e-9)
            if prox < 0.02:
                zone_score = min(zone["strength"], 20)
                break
        bias_ok = structure["structure"] in ["BEARISH", "WEAK_BEARISH"]

    return {
        "zones"          : zones,
        "fvg"            : fvg,
        "sweep"          : sweep,
        "structure"      : structure,
        "fvg_score"      : fvg_score,
        "zone_score"     : zone_score,
        "liquidity_score": sweep["score"],
        "structure_score": structure["score"],
        "bias_ok"        : bias_ok,
    }
