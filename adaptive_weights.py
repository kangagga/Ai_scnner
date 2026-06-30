"""
adaptive_weights.py — Adaptive Brain v1
Semua bobot scoring per regime ada di sini.
Mudah diubah tanpa menyentuh scanner.py.
"""

# ============================================================
# WEIGHT PROFILES PER REGIME
# Total bobot setiap regime = 1.0
# ============================================================

WEIGHT_PROFILES = {

    "TRENDING": {
        "trend_strength" : 0.40,
        "breakout"       : 0.25,
        "volume"         : 0.15,
        "momentum"       : 0.10,
        "volatility"     : 0.10,
    },

    "RANGING": {
        "support_resistance" : 0.40,
        "rsi"                : 0.20,
        "rejection_candle"   : 0.20,
        "volume"             : 0.20,
    },

    "VOLATILE": {
        "trend_strength"     : 0.20,
        "volume"             : 0.20,
        "momentum"           : 0.20,
        "support_resistance" : 0.20,
        "volatility"         : 0.20,
    },

    "NEUTRAL": {
        "trend_strength"     : 0.25,
        "support_resistance" : 0.25,
        "momentum"           : 0.20,
        "volume"             : 0.15,
        "volatility"         : 0.15,
    },
}

# ============================================================
# VOLATILE REGIME RULES
# ============================================================

VOLATILE_RULES = {
    "min_confidence"     : 70,     # confidence minimum lebih tinggi
    "position_size_mult" : 0.5,    # position size dikurangi 50%
    "sl_mult"            : 1.5,    # SL lebih lebar
    "tp_mult"            : 1.2,    # TP lebih konservatif
    "skip_if_below"      : 65,     # skip trade jika confidence < 65
}

# ============================================================
# CONFIDENCE THRESHOLD PER REGIME
# ============================================================

CONFIDENCE_THRESHOLD = {
    "TRENDING"  : 50,
    "RANGING"   : 48,
    "VOLATILE"  : 65,
    "NEUTRAL"   : 48,
}

# ============================================================
# ADAPTIVE WEIGHT ENGINE
# ============================================================

def get_weight_profile(regime: str) -> dict:
    """Return bobot scoring sesuai regime."""
    return WEIGHT_PROFILES.get(regime, WEIGHT_PROFILES["NEUTRAL"])


def compute_adaptive_score(components: dict, regime: str) -> tuple:
    """
    Hitung score berbobot sesuai regime.

    Parameters
    ----------
    components : dict
        Nilai tiap komponen (0-100), key sesuai WEIGHT_PROFILES.
        Contoh: {"trend_strength": 80, "volume": 60, ...}
    regime : str
        Regime aktif: TRENDING / RANGING / VOLATILE / NEUTRAL

    Returns
    -------
    (score: float, breakdown: dict, reason: str)
    """
    weights = get_weight_profile(regime)
    score   = 0.0
    breakdown = {}
    missing = []

    for key, weight in weights.items():
        val = components.get(key)
        if val is None:
            missing.append(key)
            val = 0.0
        contribution = round(val * weight, 2)
        breakdown[key] = {
            "value"        : round(val, 1),
            "weight"       : weight,
            "contribution" : contribution,
        }
        score += contribution

    score = round(min(100.0, max(0.0, score)), 1)
    reason = f"Regime={regime}"
    if missing:
        reason += f" | Missing: {', '.join(missing)}"

    return score, breakdown, reason


def compute_confidence(
    regime       : str,
    trend_score  : float,
    volume_score : float,
    volatility   : float,
    sr_score     : float,
    liquidity    : float,
    smc_score    : float = 0.0,
) -> tuple:
    """
    Hitung confidence score (0-100) dari berbagai faktor.

    Returns
    -------
    (confidence: float, reason: str)
    """
    weights = {
        "TRENDING" : {
            "trend"      : 0.35,
            "volume"     : 0.25,
            "sr"         : 0.15,
            "volatility" : 0.10,
            "liquidity"  : 0.10,
            "smc"        : 0.05,
        },
        "RANGING"  : {
            "sr"         : 0.35,
            "volume"     : 0.20,
            "trend"      : 0.15,
            "volatility" : 0.10,
            "liquidity"  : 0.10,
            "smc"        : 0.10,
        },
        "VOLATILE" : {
            "volatility" : 0.30,
            "volume"     : 0.25,
            "trend"      : 0.20,
            "sr"         : 0.15,
            "liquidity"  : 0.05,
            "smc"        : 0.05,
        },
        "NEUTRAL"  : {
            "trend"      : 0.25,
            "sr"         : 0.25,
            "volume"     : 0.20,
            "volatility" : 0.15,
            "liquidity"  : 0.10,
            "smc"        : 0.05,
        },
    }

    w = weights.get(regime, weights["NEUTRAL"])
    confidence = (
        trend_score  * w["trend"]      +
        volume_score * w["volume"]     +
        sr_score     * w["sr"]         +
        volatility   * w["volatility"] +
        liquidity    * w["liquidity"]  +
        smc_score    * w["smc"]
    )
    confidence = round(min(100.0, max(0.0, confidence)), 1)

    reasons = []
    if trend_score  < 40: reasons.append("trend lemah")
    if volume_score < 40: reasons.append("volume rendah")
    if volatility   > 80: reasons.append("volatilitas tinggi")
    if sr_score     < 30: reasons.append("SR tidak jelas")
    if liquidity    < 30: reasons.append("likuiditas rendah")

    reason = f"Confidence={confidence}"
    if reasons:
        reason += f" | Peringatan: {', '.join(reasons)}"

    return confidence, reason


def should_skip_volatile(confidence: float) -> bool:
    """Return True jika trade harus di-skip di regime VOLATILE."""
    return confidence < VOLATILE_RULES["skip_if_below"]


def get_position_size_multiplier(regime: str, confidence: float) -> float:
    """Return multiplier untuk position size berdasarkan regime dan confidence."""
    if regime == "VOLATILE":
        return VOLATILE_RULES["position_size_mult"]
    if confidence >= 80:
        return 1.0
    if confidence >= 65:
        return 0.75
    return 0.5


def get_sl_tp_multiplier(regime: str) -> tuple:
    """
    Return (sl_mult, tp_mult) sesuai regime.
    Default: sl=1.0, tp=1.0
    """
    if regime == "VOLATILE":
        return VOLATILE_RULES["sl_mult"], VOLATILE_RULES["tp_mult"]
    if regime == "TRENDING":
        return 1.2, 1.3   # trailing lebih lebar
    if regime == "RANGING":
        return 0.8, 0.9   # SL/TP lebih ketat di ranging
    return 1.0, 1.0


def extract_components_from_last(last: dict, df=None) -> dict:
    """
    Ekstrak komponen scoring dari baris terakhir DataFrame indikator.
    Return dict yang siap dipakai compute_adaptive_score().
    """
    import numpy as np

    def sf(v, default=0.0):
        try:
            val = float(v)
            return default if (np.isnan(val) or np.isinf(val)) else val
        except:
            return default

    rsi      = sf(last.get("rsi", 50))
    adx      = sf(last.get("adx", 0))
    vol_r    = sf(last.get("vol_ratio", 1))
    macd_h   = sf(last.get("macd_hist", 0))
    bb_pct   = sf(last.get("bb_pct", 0.5))
    sr_pos   = sf(last.get("sr_pos", 0.5))
    atr      = sf(last.get("atr", 0))
    close    = sf(last.get("close", 1), 1)
    obv_bull = bool(last.get("obv_bull", False))
    trend_up = bool(last.get("trend_up", False))
    trend_dn = bool(last.get("trend_down", False))
    squeeze  = sf(last.get("squeeze_score", 0))

    # Trend strength (0-100)
    trend_strength = min(100, adx * 2.5)
    if trend_up or trend_dn:
        trend_strength = min(100, trend_strength * 1.2)

    # Breakout (0-100)
    breakout = 0.0
    if sf(last.get("broke_resistance", 0)):
        breakout = min(100, 60 + vol_r * 20)
    elif squeeze > 70:
        breakout = squeeze * 0.8

    # Volume (0-100)
    volume = min(100, vol_r * 50)

    # Momentum (0-100)
    macd_norm = min(100, max(0, (macd_h / (close * 0.01 + 1e-9)) * 50 + 50))
    rsi_mom   = abs(rsi - 50) * 2
    momentum  = round((macd_norm * 0.6 + rsi_mom * 0.4), 1)

    # Volatility — tinggi = score tinggi (untuk context), bukan selalu bagus
    atr_pct    = (atr / close * 100) if close > 0 else 0
    volatility = min(100, atr_pct * 20)

    # Support/Resistance quality (0-100)
    sr_quality = round(abs(sr_pos - 0.5) * 200, 1)  # makin ekstrem = makin dekat SR

    # RSI quality (0-100) — makin jauh dari 50 = makin kuat sinyal
    rsi_score = round(abs(rsi - 50) * 2, 1)

    # Rejection candle (0-100)
    hammer    = bool(last.get("hammer", 0))
    engulf    = bool(last.get("bull_engulf", 0)) or bool(last.get("bear_engulf", 0))
    doji      = bool(last.get("doji", 0))
    rejection = 100 if engulf else (80 if hammer else (50 if doji else 0))

    return {
        "trend_strength"     : round(trend_strength, 1),
        "breakout"           : round(breakout, 1),
        "volume"             : round(volume, 1),
        "momentum"           : round(momentum, 1),
        "volatility"         : round(volatility, 1),
        "support_resistance" : round(sr_quality, 1),
        "rsi"                : round(rsi_score, 1),
        "rejection_candle"   : round(rejection, 1),
    }
