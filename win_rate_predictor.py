# ============================================================
#  win_rate_predictor.py  – AI Win Rate Predictor
#  PERBAIKAN v2:
#  1. Tambah flag "is_default" agar bisa dibedakan dari prediksi nyata
#  2. Gunakan cache data dari scanner (tidak fetch ulang jika ada)
#  3. similar_cases = 0 → skip filter win rate di risk manager
#  4. Confidence level lebih informatif
#  5. Tambah "data_quality" score
# ============================================================
import logging
import numpy as np
import pandas as pd
from typing import Optional
from data_fetcher import fetch_ohlcv
from indicators   import institutional_ai_v4

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
#  Fitur yang dipakai untuk matching
# ------------------------------------------------------------------
FEATURE_COLS = [
    "rsi", "adx", "bb_pct", "vol_ratio",
    "stoch_k", "macd_hist", "squeeze_score",
]

FEATURE_WEIGHTS = {
    "rsi"          : 1.5,
    "adx"          : 1.2,
    "bb_pct"       : 1.3,
    "vol_ratio"    : 1.4,
    "stoch_k"      : 1.0,
    "macd_hist"    : 1.6,
    "squeeze_score": 1.5,
}

MIN_SIMILAR_CASES   = 8     # [FIX] diturunkan dari 10 → lebih toleran
SIMILARITY_TOP_N    = 30
SL_ATR_MULT         = 1.5
TP_ATR_MULT         = 2.0
MAX_FORWARD_CANDLES = 40

# Cache sederhana agar tidak fetch ulang untuk pair yang sama
_wr_cache: dict = {}
CACHE_MAX = 200  # maksimal entry cache


# ------------------------------------------------------------------
#  Normalisasi fitur
# ------------------------------------------------------------------
def _normalize_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in FEATURE_COLS:
        if col not in result.columns:
            result[col] = 0.0
            continue
        col_min = result[col].min()
        col_max = result[col].max()
        rng = col_max - col_min
        if rng > 0:
            result[col] = (result[col] - col_min) / rng
        else:
            result[col] = 0.5
    return result


# ------------------------------------------------------------------
#  Weighted euclidean distance
# ------------------------------------------------------------------
def _weighted_distance(row_a: pd.Series, row_b: pd.Series) -> float:
    total = 0.0
    for col in FEATURE_COLS:
        w    = FEATURE_WEIGHTS.get(col, 1.0)
        diff = float(row_a.get(col, 0)) - float(row_b.get(col, 0))
        total += w * (diff ** 2)
    return np.sqrt(total)


# ------------------------------------------------------------------
#  Simulasi hasil trade historis
# ------------------------------------------------------------------
def _simulate_outcome(df: pd.DataFrame, signal_idx: int,
                      signal: str, atr: float) -> Optional[str]:
    if signal_idx + 1 >= len(df):
        return None
    entry = float(df.iloc[signal_idx]["close"])
    if atr <= 0:
        return None

    if signal.startswith("BUY"):
        sl = entry - SL_ATR_MULT * atr
        tp = entry + TP_ATR_MULT * atr
    else:
        sl = entry + SL_ATR_MULT * atr
        tp = entry - TP_ATR_MULT * atr

    for j in range(signal_idx + 1, min(signal_idx + MAX_FORWARD_CANDLES, len(df))):
        high = float(df.iloc[j]["high"])
        low  = float(df.iloc[j]["low"])

        if signal.startswith("BUY"):
            if low <= sl:
                return "LOSS"
            if high >= tp:
                return "WIN"
        else:
            if high >= sl:
                return "LOSS"
            if low <= tp:
                return "WIN"

    final_price = float(df.iloc[min(signal_idx + MAX_FORWARD_CANDLES, len(df) - 1)]["close"])
    if signal.startswith("BUY"):
        return "WIN" if final_price > entry else "LOSS"
    else:
        return "WIN" if final_price < entry else "LOSS"


# ------------------------------------------------------------------
#  MAIN: Prediksi Win Rate
# ------------------------------------------------------------------
def predict_win_rate(
    symbol          : str,
    timeframe       : str,
    signal          : str,
    current_features: dict,
    df_cached       : Optional[pd.DataFrame] = None,  # [FIX] terima df dari scanner
) -> dict:
    """
    Prediksi probabilitas menang berdasarkan pattern matching historis.

    Return dict dengan key tambahan:
      - is_default    : True jika tidak ada data cukup (prediksi tidak valid)
      - data_quality  : "HIGH" / "MEDIUM" / "LOW" / "NONE"
      - similar_cases : 0 jika tidak ada data (gunakan ini di risk manager)
    """
    try:
        # [FIX] Gunakan df dari scanner jika ada, hindari fetch ulang
        cache_key = f"{symbol}_{timeframe}"
        if df_cached is not None and len(df_cached) >= 200:
            df = df_cached.copy()
        elif cache_key in _wr_cache:
            df = _wr_cache[cache_key].copy()
        else:
            df = fetch_ohlcv(symbol, timeframe, limit=500)
            if df is not None and len(df) >= 200:
                # Simpan ke cache
                if len(_wr_cache) >= CACHE_MAX:
                    # Hapus entry pertama jika cache penuh
                    _wr_cache.pop(next(iter(_wr_cache)))
                _wr_cache[cache_key] = df.copy()

        if df is None or len(df) < 200:
            return _default_prediction("Data tidak cukup")

        # Cast & hitung indikator
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna().reset_index(drop=True)
        df = institutional_ai_v4(df)

        if "squeeze_score" not in df.columns:
            df["squeeze_score"] = 0.0

        df_norm = _normalize_features(df)

        # Normalisasi current features
        current = pd.Series({col: float(current_features.get(col, 0)) for col in FEATURE_COLS})
        for col in FEATURE_COLS:
            if col not in df.columns:
                continue
            col_min = df[col].min()
            col_max = df[col].max()
            rng = col_max - col_min
            if rng > 0:
                current[col] = (current[col] - col_min) / rng
            else:
                current[col] = 0.5
            current[col] = float(np.clip(current[col], 0, 1))

        # Cari kasus mirip di historis
        lookback_end = len(df) - 50
        if lookback_end < 100:
            return _default_prediction("Data historis tidak cukup")

        distances = []
        for i in range(50, lookback_end):
            row_norm = df_norm.iloc[i]
            dist     = _weighted_distance(current, row_norm)
            distances.append((i, dist))

        distances.sort(key=lambda x: x[1])
        top_similar = distances[:SIMILARITY_TOP_N]

        if len(top_similar) < MIN_SIMILAR_CASES:
            return _default_prediction("Tidak cukup kasus mirip")

        # Simulasi outcome
        wins   = 0
        losses = 0
        pnls   = []

        for idx, dist in top_similar:
            atr_val = float(df.iloc[idx].get("atr", 0))
            outcome = _simulate_outcome(df, idx, signal, atr_val)
            if outcome is None:
                continue

            entry = float(df.iloc[idx]["close"])
            atr_v = float(df.iloc[idx].get("atr", entry * 0.01))

            if outcome == "WIN":
                wins += 1
                pnl   = (TP_ATR_MULT * atr_v / entry) * 100
            else:
                losses += 1
                pnl    = -(SL_ATR_MULT * atr_v / entry) * 100
            pnls.append(pnl)

        total = wins + losses
        if total < MIN_SIMILAR_CASES:
            return _default_prediction("Simulasi outcome tidak cukup")

        win_rate = round(wins / total * 100, 1)
        avg_pnl  = round(np.mean(pnls), 2) if pnls else 0.0

        # [FIX] Data quality score
        if total >= 25:
            data_quality = "HIGH"
        elif total >= 15:
            data_quality = "MEDIUM"
        else:
            data_quality = "LOW"

        # Confidence level
        if total >= 25 and (win_rate >= 60 or win_rate <= 40):
            confidence = "HIGH"
        elif total >= 15:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Label & advice
        if win_rate >= 65:
            label  = "✅ Very Favorable"
            advice = "Sangat menguntungkan secara historis"
        elif win_rate >= 55:
            label  = "✅ Favorable"
            advice = "Cukup menguntungkan secara historis"
        elif win_rate >= 45:
            label  = "⚠️ Neutral"
            advice = "Historis 50-50, hati-hati"
        elif win_rate >= 35:
            label  = "🔴 Unfavorable"
            advice = "Historis lebih sering kalah, pertimbangkan skip"
        else:
            label  = "🔴 Very Unfavorable"
            advice = "Historis sangat buruk untuk kondisi ini, skip disarankan"

        return {
            "win_rate"      : win_rate,
            "confidence"    : confidence,
            "data_quality"  : data_quality,   # [FIX] tambahan
            "is_default"    : False,           # [FIX] tambahan
            "similar_cases" : total,
            "wins"          : wins,
            "losses"        : losses,
            "avg_pnl"       : avg_pnl,
            "label"         : label,
            "advice"        : f"{advice} ({wins}W/{losses}L dari {total} kasus mirip)",
        }

    except Exception as e:
        logger.warning(f"Win rate prediction error {symbol}/{timeframe}: {e}")
        return _default_prediction(f"Error: {e}")


def _default_prediction(reason: str = "") -> dict:
    """[FIX] Tambah is_default=True dan data_quality='NONE' agar bisa dideteksi."""
    return {
        "win_rate"      : 50.0,
        "confidence"    : "LOW",
        "data_quality"  : "NONE",   # [FIX]
        "is_default"    : True,     # [FIX] flag penting untuk risk manager
        "similar_cases" : 0,        # [FIX] 0 = tidak ada data valid
        "wins"          : 0,
        "losses"        : 0,
        "avg_pnl"       : 0.0,
        "label"         : "❓ No Data",
        "advice"        : reason or "Tidak cukup data historis",
    }
