"""
volume_filter.py — Volume Confirmation Filter
Institutional AI v9 | SMC Layer
Konfirmasi volume spike, impulsive candle, hindari doji.
"""
import numpy as np
import pandas as pd


def is_doji(df: pd.DataFrame, threshold: float = 0.1) -> bool:
    """Deteksi doji candle — body sangat kecil relatif terhadap range."""
    last  = df.iloc[-1]
    body  = abs(last["close"] - last["open"])
    rng   = last["high"] - last["low"]
    if rng == 0:
        return True
    return (body / rng) < threshold


def is_impulsive_candle(df: pd.DataFrame, multiplier: float = 1.5) -> bool:
    """
    Deteksi impulsive candle:
    - Body lebih besar dari rata-rata body 20 candle terakhir
    - Volume di atas rata-rata
    """
    if len(df) < 20:
        return False

    last      = df.iloc[-1]
    body      = abs(last["close"] - last["open"])
    avg_body  = np.mean(np.abs(
        df["close"].values[-20:-1] - df["open"].values[-20:-1]
    ))

    return body > avg_body * multiplier


def get_volume_ratio(df: pd.DataFrame, period: int = 20) -> float:
    """Rasio volume candle terakhir vs rata-rata."""
    if len(df) < period or "volume" not in df.columns:
        return 1.0
    avg_vol = np.mean(df["volume"].values[-period-1:-1])
    if avg_vol == 0:
        return 1.0
    return round(df["volume"].iloc[-1] / avg_vol, 2)


def analyze_volume(df: pd.DataFrame, signal: str) -> dict:
    """
    Analisa volume konfirmasi lengkap.
    
    Returns:
        dict: {
            "score"      : 0-10,
            "vol_ratio"  : float,
            "is_spike"   : bool,
            "is_impulse" : bool,
            "is_doji"    : bool,
            "reason"     : str
        }
    """
    if df is None or len(df) < 20:
        return {
            "score"     : 0,
            "vol_ratio" : 1.0,
            "is_spike"  : False,
            "is_impulse": False,
            "is_doji"   : False,
            "reason"    : "Data tidak cukup"
        }

    vol_ratio  = get_volume_ratio(df)
    is_spike   = vol_ratio >= 1.5
    is_impulse = is_impulsive_candle(df)
    doji       = is_doji(df)

    score  = 0
    reason = []

    # Doji = sinyal lemah, penalty
    if doji:
        return {
            "score"     : 0,
            "vol_ratio" : vol_ratio,
            "is_spike"  : is_spike,
            "is_impulse": is_impulse,
            "is_doji"   : True,
            "reason"    : "❌ Doji candle — sinyal tidak valid"
        }

    # Volume spike
    if is_spike:
        score += 5
        reason.append(f"Volume spike {vol_ratio:.1f}x")

    # Impulsive candle
    if is_impulse:
        score += 3
        reason.append("Impulsive candle")

    # Arah candle selaras signal
    last = df.iloc[-1]
    if signal.startswith("BUY") and last["close"] > last["open"]:
        score += 2
        reason.append("Bullish candle konfirmasi")
    elif signal.startswith("SELL") and last["close"] < last["open"]:
        score += 2
        reason.append("Bearish candle konfirmasi")

    score = min(score, 10)

    return {
        "score"     : score,
        "vol_ratio" : vol_ratio,
        "is_spike"  : is_spike,
        "is_impulse": is_impulse,
        "is_doji"   : doji,
        "reason"    : ", ".join(reason) if reason else "Volume normal"
    }


def get_volume_score(df: pd.DataFrame, signal: str) -> float:
    """Return score 0-10 untuk volume konfirmasi."""
    result = analyze_volume(df, signal)
    return result["score"]
