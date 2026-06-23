"""
zone_detector.py — Supply & Demand Zone Detector
Institutional AI v9 | SMC Layer
"""
import numpy as np
import pandas as pd


def detect_zones(df: pd.DataFrame, lookback: int = 20) -> dict:
    """
    Deteksi zona Supply & Demand otomatis.
    Returns: dict dengan 'demand' dan 'supply' zones
    """
    if df is None or len(df) < lookback:
        return {"demand": [], "supply": []}

    demand_zones = []
    supply_zones = []

    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    vols   = df["volume"].values if "volume" in df.columns else np.ones(len(df))

    for i in range(2, len(df) - 2):
        # ── DEMAND ZONE ──
        # Pola: candle turun kuat → candle naik impulsif
        is_bearish_before = closes[i-1] < df["open"].values[i-1]
        is_bullish_after  = closes[i+1] > df["open"].values[i+1]
        body_size_after   = abs(closes[i+1] - df["open"].values[i+1])
        avg_body          = np.mean(np.abs(closes[max(0,i-10):i] - df["open"].values[max(0,i-10):i]))

        if (is_bearish_before and is_bullish_after and
                body_size_after > avg_body * 1.2 and
                lows[i] < lows[i-1]):

            zone_high = max(highs[i-1], highs[i])
            zone_low  = lows[i]
            vol_score = min(vols[i] / (np.mean(vols[max(0,i-10):i]) + 1e-9), 3.0)

            demand_zones.append({
                "index"    : i,
                "high"     : round(zone_high, 8),
                "low"      : round(zone_low, 8),
                "mid"      : round((zone_high + zone_low) / 2, 8),
                "vol_score": round(vol_score, 2),
                "retests"  : 0,
                "strength" : 0,
            })

        # ── SUPPLY ZONE ──
        # Pola: candle naik kuat → candle turun impulsif
        is_bullish_before = closes[i-1] > df["open"].values[i-1]
        is_bearish_after  = closes[i+1] < df["open"].values[i+1]
        body_size_after_s = abs(closes[i+1] - df["open"].values[i+1])

        if (is_bullish_before and is_bearish_after and
                body_size_after_s > avg_body * 1.2 and
                highs[i] > highs[i-1]):

            zone_high = highs[i]
            zone_low  = min(lows[i-1], lows[i])
            vol_score = min(vols[i] / (np.mean(vols[max(0,i-10):i]) + 1e-9), 3.0)

            supply_zones.append({
                "index"    : i,
                "high"     : round(zone_high, 8),
                "low"      : round(zone_low, 8),
                "mid"      : round((zone_high + zone_low) / 2, 8),
                "vol_score": round(vol_score, 2),
                "retests"  : 0,
                "strength" : 0,
            })

    # Hitung retest & strength
    current_price = closes[-1]
    demand_zones  = _score_zones(demand_zones, closes, zone_type="demand")
    supply_zones  = _score_zones(supply_zones, closes, zone_type="supply")

    # Filter zona yang masih relevan (harga belum menembus jauh)
    demand_zones = [z for z in demand_zones if current_price > z["low"] * 0.95]
    supply_zones = [z for z in supply_zones if current_price < z["high"] * 1.05]

    # Sort: demand terdekat di atas, supply terdekat di bawah
    demand_zones = sorted(demand_zones, key=lambda z: abs(current_price - z["mid"]))
    supply_zones = sorted(supply_zones, key=lambda z: abs(current_price - z["mid"]))

    return {
        "demand": demand_zones[:3],  # top 3 terdekat
        "supply": supply_zones[:3],
    }


def _score_zones(zones: list, closes: np.ndarray, zone_type: str) -> list:
    """Hitung retest count dan strength score per zona."""
    for zone in zones:
        retest_count = 0
        for price in closes[zone["index"]+1:]:
            if zone["low"] <= price <= zone["high"]:
                retest_count += 1
        zone["retests"]  = retest_count
        # Strength: vol_score (0-3) + retest bonus + zone type bonus
        zone["strength"] = round(
            min(zone["vol_score"] * 5, 15) +
            min(retest_count * 3, 10) +
            (5 if zone_type == "demand" else 5),
            1
        )
    return zones


def get_zone_score(df: pd.DataFrame, signal: str) -> float:
    """
    Return score 0-20 untuk Supply/Demand zone.
    Dipakai di confidence scoring SMC.
    """
    zones = detect_zones(df)
    current_price = df["close"].iloc[-1]

    if signal.startswith("BUY"):
        relevant = zones["demand"]
        for zone in relevant:
            proximity = abs(current_price - zone["mid"]) / (current_price + 1e-9)
            if proximity < 0.02:  # harga dalam 2% dari zona demand
                return min(zone["strength"], 20)
        return 5  # ada zona tapi tidak dekat

    elif signal.startswith("SELL"):
        relevant = zones["supply"]
        for zone in relevant:
            proximity = abs(current_price - zone["mid"]) / (current_price + 1e-9)
            if proximity < 0.02:  # harga dalam 2% dari zona supply
                return min(zone["strength"], 20)
        return 5

    return 0
