"""
trend_filter.py — Multi Timeframe Trend Filter
Institutional AI v9 | SMC Layer
4H = trend utama | 1H = zona entry | 15m = trigger
"""
import numpy as np
import pandas as pd


def get_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def get_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Hitung ADX untuk filter kekuatan trend."""
    try:
        high  = df["high"]
        low   = df["low"]
        close = df["close"]

        plus_dm  = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0]   = 0
        minus_dm[minus_dm < 0] = 0

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr      = tr.ewm(span=period, adjust=False).mean()
        plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / (atr + 1e-9)
        minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / (atr + 1e-9)
        dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
        adx      = dx.ewm(span=period, adjust=False).mean()

        return round(float(adx.iloc[-1]), 2)
    except:
        return 0.0


def analyze_trend(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    """
    Analisa trend berdasarkan EMA50, EMA200, HH/HL, ADX.
    Returns dict lengkap trend info.
    """
    if df is None or len(df) < 200:
        return {
            "trend"    : "NEUTRAL",
            "strength" : "WEAK",
            "adx"      : 0,
            "ema50"    : 0,
            "ema200"   : 0,
            "score"    : 0,
            "bias"     : "NEUTRAL",
        }

    close  = df["close"]
    ema50  = get_ema(close, 50).iloc[-1]
    ema200 = get_ema(close, 200).iloc[-1]
    adx    = get_adx(df)
    price  = close.iloc[-1]

    # HH/HL detection
    highs = df["high"].values[-20:]
    lows  = df["low"].values[-20:]
    hh    = highs[-1] > highs[-5] > highs[-10]
    hl    = lows[-1]  > lows[-5]  > lows[-10]
    lh    = highs[-1] < highs[-5] < highs[-10]
    ll    = lows[-1]  < lows[-5]  < lows[-10]

    # Trend determination
    ema_bullish = price > ema50 > ema200
    ema_bearish = price < ema50 < ema200

    if ema_bullish and hh and hl:
        trend = "STRONG_BULLISH"
        score = 25
    elif ema_bullish or (hh and hl):
        trend = "BULLISH"
        score = 18
    elif ema_bearish and lh and ll:
        trend = "STRONG_BEARISH"
        score = 25
    elif ema_bearish or (lh and ll):
        trend = "BEARISH"
        score = 18
    else:
        trend = "NEUTRAL"
        score = 5

    # ADX filter
    if adx >= 25:
        strength = "STRONG"
    elif adx >= 15:
        strength = "MODERATE"
    else:
        strength = "WEAK"
        score    = max(score - 8, 0)  # penalty trend lemah

    # Bias untuk signal filter
    if "BULLISH" in trend:
        bias = "BUY"
    elif "BEARISH" in trend:
        bias = "SELL"
    else:
        bias = "NEUTRAL"

    return {
        "trend"    : trend,
        "strength" : strength,
        "adx"      : adx,
        "ema50"    : round(ema50, 8),
        "ema200"   : round(ema200, 8),
        "score"    : min(score, 25),
        "bias"     : bias,
    }


def is_trend_aligned(signal: str, trend_info: dict) -> bool:
    """Cek apakah sinyal selaras dengan trend."""
    bias = trend_info.get("bias", "NEUTRAL")
    if bias == "NEUTRAL":
        return True  # Sideways — boleh dua arah
    if signal.startswith("BUY") and bias == "BUY":
        return True
    if signal.startswith("SELL") and bias == "SELL":
        return True
    return False


def get_trend_score(df: pd.DataFrame, signal: str) -> float:
    """Return score 0-25 untuk trend alignment."""
    trend_info = analyze_trend(df)
    if not is_trend_aligned(signal, trend_info):
        return 0  # Melawan trend = 0
    return trend_info["score"]
