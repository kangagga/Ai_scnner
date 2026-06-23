"""
divergence_detector.py — RSI & MACD Divergence Detector
Institutional AI v9 | SMC Layer
RSI/MACD hanya sebagai konfirmasi divergence, bukan overbought/oversold langsung.
"""
import numpy as np
import pandas as pd


def get_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta  = close.diff()
    gain   = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
    loss   = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
    rs     = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def get_macd(close: pd.Series, fast=12, slow=26, signal=9) -> dict:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd     = ema_fast - ema_slow
    sig_line = macd.ewm(span=signal, adjust=False).mean()
    hist     = macd - sig_line
    return {"macd": macd, "signal": sig_line, "hist": hist}


def detect_divergence(df: pd.DataFrame, lookback: int = 14) -> dict:
    """
    Deteksi divergence RSI dan MACD.
    
    Bullish Divergence: harga LL tapi RSI/MACD HL → potensi reversal naik
    Bearish Divergence: harga HH tapi RSI/MACD LH → potensi reversal turun
    
    Returns:
        dict: {
            "rsi_bullish"  : bool,
            "rsi_bearish"  : bool,
            "macd_bullish" : bool,
            "macd_bearish" : bool,
            "score"        : 0-10,
            "reason"       : str
        }
    """
    if df is None or len(df) < lookback + 5:
        return {
            "rsi_bullish" : False, "rsi_bearish" : False,
            "macd_bullish": False, "macd_bearish": False,
            "score": 0, "reason": "Data tidak cukup"
        }

    close   = df["close"]
    rsi     = get_rsi(close)
    macd_d  = get_macd(close)
    hist    = macd_d["hist"]

    # Ambil window lookback
    price_window = close.values[-lookback:]
    rsi_window   = rsi.values[-lookback:]
    hist_window  = hist.values[-lookback:]

    # Cari swing points
    price_low1  = np.min(price_window[:lookback//2])
    price_low2  = np.min(price_window[lookback//2:])
    price_high1 = np.max(price_window[:lookback//2])
    price_high2 = np.max(price_window[lookback//2:])

    rsi_low1  = np.min(rsi_window[:lookback//2])
    rsi_low2  = np.min(rsi_window[lookback//2:])
    rsi_high1 = np.max(rsi_window[:lookback//2])
    rsi_high2 = np.max(rsi_window[lookback//2:])

    hist_low1  = np.min(hist_window[:lookback//2])
    hist_low2  = np.min(hist_window[lookback//2:])
    hist_high1 = np.max(hist_window[:lookback//2])
    hist_high2 = np.max(hist_window[lookback//2:])

    # Divergence detection
    rsi_bullish  = (price_low2  < price_low1)  and (rsi_low2  > rsi_low1)
    rsi_bearish  = (price_high2 > price_high1) and (rsi_high2 < rsi_high1)
    macd_bullish = (price_low2  < price_low1)  and (hist_low2 > hist_low1)
    macd_bearish = (price_high2 > price_high1) and (hist_high2 < hist_high1)

    # Score
    score  = 0
    reason = []

    if rsi_bullish:
        score += 5
        reason.append("RSI Bullish Divergence")
    if macd_bullish:
        score += 5
        reason.append("MACD Bullish Divergence")
    if rsi_bearish:
        score += 5
        reason.append("RSI Bearish Divergence")
    if macd_bearish:
        score += 5
        reason.append("MACD Bearish Divergence")

    score = min(score, 10)

    return {
        "rsi_bullish" : rsi_bullish,
        "rsi_bearish" : rsi_bearish,
        "macd_bullish": macd_bullish,
        "macd_bearish": macd_bearish,
        "score"       : score,
        "reason"      : ", ".join(reason) if reason else "Tidak ada divergence"
    }


def get_divergence_score(df: pd.DataFrame, signal: str) -> float:
    """
    Return score 0-10 untuk divergence konfirmasi.
    BUY butuh bullish divergence.
    SELL butuh bearish divergence.
    """
    div = detect_divergence(df)

    if signal.startswith("BUY"):
        if div["rsi_bullish"] and div["macd_bullish"]:
            return 10  # Konfirmasi kuat
        elif div["rsi_bullish"] or div["macd_bullish"]:
            return 5   # Konfirmasi parsial
        return 0

    elif signal.startswith("SELL"):
        if div["rsi_bearish"] and div["macd_bearish"]:
            return 10
        elif div["rsi_bearish"] or div["macd_bearish"]:
            return 5
        return 0

    return 0
