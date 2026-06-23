"""
Input/Output validators — pastikan nilai tidak keluar range
Import di scanner.py dan modul lain yang butuh validasi
"""
import math
import logging

logger = logging.getLogger(__name__)

def clamp(value, min_val=0.0, max_val=100.0, name="value") -> float:
    """Pastikan nilai dalam range [min_val, max_val]"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        logger.debug(f"[VALID] {name} adalah None/NaN → default {min_val}")
        return min_val
    if math.isinf(value):
        logger.debug(f"[VALID] {name} adalah Inf → clamp ke {max_val}")
        return max_val
    if value < min_val:
        logger.debug(f"[VALID] {name}={value} < {min_val} → clamp")
        return float(min_val)
    if value > max_val:
        logger.debug(f"[VALID] {name}={value} > {max_val} → clamp")
        return float(max_val)
    return float(value)

def validate_score(score, name="score") -> float:
    """Score harus 0-100"""
    return clamp(score, 0.0, 100.0, name)

def validate_price(price, name="price") -> float:
    """Harga harus > 0"""
    if price is None or (isinstance(price, float) and math.isnan(price)):
        return 0.0
    return max(0.0, float(price))

def validate_pct(pct, name="pct") -> float:
    """Persentase wajar -100 s/d +1000"""
    return clamp(pct, -100.0, 1000.0, name)

def validate_signal_dict(s: dict) -> dict:
    """
    Validasi semua field penting di signal dict
    Return signal dict yang sudah dibersihkan
    """
    numeric_fields = {
        "score"        : (0, 100),
        "score_raw"    : (0, 100),
        "smc_bonus"    : (-10, 15),
        "ob_bonus"     : (-10, 10),
        "vp_bonus"     : (-8, 8),
        "liq_adj"      : (-5, 3),
        "confidence"   : (0, 100),
        "win_rate"     : (0, 100),
        "rr_ratio"     : (0, 20),
        "ob_imbalance" : (-1, 1),
        "ob_spread_pct": (0, 10),
        "liq_score"    : (0, 10),
    }
    cleaned = dict(s)
    for field, (lo, hi) in numeric_fields.items():
        if field in cleaned:
            try:
                val = float(cleaned[field])
                cleaned[field] = clamp(val, lo, hi, field)
            except (TypeError, ValueError):
                cleaned[field] = lo
    return cleaned

def validate_trade_params(entry, sl, tp1, signal) -> tuple:
    """
    Validasi parameter trade — return (valid, reason)
    """
    if entry <= 0:
        return False, f"Entry tidak valid: {entry}"
    if sl <= 0:
        return False, f"SL tidak valid: {sl}"
    if tp1 <= 0:
        return False, f"TP1 tidak valid: {tp1}"

    if signal.startswith("BUY"):
        if sl >= entry:
            return False, f"BUY: SL({sl}) >= Entry({entry})"
        if tp1 <= entry:
            return False, f"BUY: TP1({tp1}) <= Entry({entry})"
    elif signal.startswith("SELL"):
        if sl <= entry:
            return False, f"SELL: SL({sl}) <= Entry({entry})"
        if tp1 >= entry:
            return False, f"SELL: TP1({tp1}) >= Entry({entry})"

    # RR minimum 1:1
    risk   = abs(entry - sl)
    reward = abs(tp1 - entry)
    if risk > 0 and reward / risk < 0.5:
        return False, f"RR terlalu rendah: {reward/risk:.2f}"

    return True, "OK"
