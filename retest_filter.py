"""
retest_filter.py — Retest Filter
Institutional AI v9 | SMC Layer
Pastikan entry HANYA saat retest, bukan breakout pertama.
"""
import numpy as np
import pandas as pd
from smart_zone_engine import detect_fvg, detect_zones


def is_retest(df: pd.DataFrame, signal: str, tolerance: float = 0.02) -> dict:
    """
    Cek apakah harga sedang retest zona/FVG.
    
    Urutan valid:
    Breakout → Retrace → Retest FVG/Zone → Konfirmasi → Entry
    
    Returns:
        dict: {
            "valid"   : bool,
            "type"    : "FVG" | "DEMAND" | "SUPPLY" | "NONE",
            "score"   : 0-15,
            "reason"  : str
        }
    """
    if df is None or len(df) < 10:
        return {"valid": False, "type": "NONE", "score": 0, "reason": "Data tidak cukup"}

    current_price = df["close"].iloc[-1]
    prev_price    = df["close"].iloc[-2]
    zones         = detect_zones(df)
    fvg           = detect_fvg(df)

    # ── Cek retest FVG ──
    if signal.startswith("BUY"):
        # Harga harus sudah breakout ke atas lalu retrace ke FVG bullish
        for gap in fvg["bullish"]:
            in_zone = gap["low"] <= current_price <= gap["high"] * (1 + tolerance)
            was_above = prev_price > gap["high"]  # sebelumnya di atas FVG
            if in_zone:
                # Konfirmasi candle: close harus di atas open (bullish candle)
                is_confirm = df["close"].iloc[-1] > df["open"].iloc[-1]
                if is_confirm:
                    return {
                        "valid" : True,
                        "type"  : "FVG",
                        "score" : 15,
                        "reason": f"Retest Bullish FVG di {gap['mid']:.6f}"
                    }
                return {
                    "valid" : False,
                    "type"  : "FVG",
                    "score" : 8,
                    "reason": "Dalam FVG tapi belum konfirmasi candle bullish"
                }

        # Cek retest Demand Zone
        for zone in zones["demand"]:
            in_zone = zone["low"] <= current_price <= zone["high"] * (1 + tolerance)
            if in_zone:
                is_confirm = df["close"].iloc[-1] > df["open"].iloc[-1]
                if is_confirm:
                    return {
                        "valid" : True,
                        "type"  : "DEMAND",
                        "score" : 12,
                        "reason": f"Retest Demand Zone di {zone['mid']:.6f}"
                    }
                return {
                    "valid" : False,
                    "type"  : "DEMAND",
                    "score" : 6,
                    "reason": "Dalam Demand Zone tapi belum konfirmasi"
                }

    elif signal.startswith("SELL"):
        # Cek retest FVG bearish
        for gap in fvg["bearish"]:
            in_zone = gap["low"] * (1 - tolerance) <= current_price <= gap["high"]
            if in_zone:
                is_confirm = df["close"].iloc[-1] < df["open"].iloc[-1]
                if is_confirm:
                    return {
                        "valid" : True,
                        "type"  : "FVG",
                        "score" : 15,
                        "reason": f"Retest Bearish FVG di {gap['mid']:.6f}"
                    }
                return {
                    "valid" : False,
                    "type"  : "FVG",
                    "score" : 8,
                    "reason": "Dalam FVG tapi belum konfirmasi candle bearish"
                }

        # Cek retest Supply Zone
        for zone in zones["supply"]:
            in_zone = zone["low"] * (1 - tolerance) <= current_price <= zone["high"]
            if in_zone:
                is_confirm = df["close"].iloc[-1] < df["open"].iloc[-1]
                if is_confirm:
                    return {
                        "valid" : True,
                        "type"  : "SUPPLY",
                        "score" : 12,
                        "reason": f"Retest Supply Zone di {zone['mid']:.6f}"
                    }
                return {
                    "valid" : False,
                    "type"  : "SUPPLY",
                    "score" : 6,
                    "reason": "Dalam Supply Zone tapi belum konfirmasi"
                }

    return {
        "valid" : False,
        "type"  : "NONE",
        "score" : 0,
        "reason": "Tidak dalam zona retest apapun"
    }


def get_retest_score(df: pd.DataFrame, signal: str) -> float:
    """Return score 0-15 untuk retest filter."""
    result = is_retest(df, signal)
    return result["score"]
