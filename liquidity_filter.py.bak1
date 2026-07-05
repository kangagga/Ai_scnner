"""
Liquidity Filter — cek apakah pair layak untuk entry
Berdasarkan: USD liquidity, spread, dan slippage estimate
"""
import requests, time

_BASE  = "https://api.gateio.ws/api/v4"
_CACHE = {}
_TTL   = 120  # 2 menit

from config import MIN_LIQUIDITY_USD, MAX_SPREAD_PCT, MIN_DAILY_VOL_USD

def _get_price(symbol: str) -> float:
    key = f"price_{symbol}"
    now = time.time()
    if key in _CACHE and now - _CACHE[key]["ts"] < _TTL:
        return _CACHE[key]["data"]
    try:
        r = requests.get(f"{_BASE}/spot/tickers",
                         params={"currency_pair": symbol}, timeout=4)
        if r.status_code == 200:
            data = r.json()[0]
            price = float(data.get("last", 0))
            vol24 = float(data.get("quote_volume", 0))  # sudah dalam USDT
            _CACHE[key] = {"ts": now, "data": price}
            _CACHE[f"vol24_{symbol}"] = {"ts": now, "data": vol24}
            return price
    except Exception:
        pass
    return 0.0

def _get_vol24(symbol: str) -> float:
    key = f"vol24_{symbol}"
    now = time.time()
    if key in _CACHE and now - _CACHE[key]["ts"] < _TTL:
        return _CACHE[key]["data"]
    _get_price(symbol)  # trigger fetch sekaligus
    return _CACHE.get(key, {}).get("data", 0.0)

def check_liquidity(symbol: str, ob_features: dict) -> dict:
    """
    Return dict:
      is_liquid       : bool — layak trade atau tidak
      liq_usd         : float — total liquidity dalam USD
      vol24_usd       : float — volume 24h dalam USD
      spread_pct      : float — spread %
      slippage_est    : float — estimasi slippage untuk order $1000
      reject_reason   : str — alasan ditolak (kosong jika liquid)
      liq_score       : int — 0-10 (makin tinggi makin liquid)
    """
    result = {
        "is_liquid"    : True,
        "liq_usd"      : 0.0,
        "vol24_usd"    : 0.0,
        "spread_pct"   : 0.0,
        "slippage_est" : 0.0,
        "reject_reason": "",
        "liq_score"    : 5,
    }

    spread = ob_features.get("ob_spread_pct", 0)
    liq    = ob_features.get("ob_liquidity", 0)
    # Gate.io butuh format SOL_USDT bukan SOLUSDT
    symbol_gate = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    price  = _get_price(symbol_gate)
    vol24  = _get_vol24(symbol_gate)

    liq_usd = liq * price if price > 0 else 0
    result["liq_usd"]    = round(liq_usd, 2)
    result["vol24_usd"]  = round(vol24, 2)
    result["spread_pct"] = spread

    # Estimasi slippage untuk order $1000
    if liq_usd > 0:
        result["slippage_est"] = round(1000 / liq_usd * 100, 4)

    # ── Cek kelayakan ──
    reasons = []
    if liq_usd < MIN_LIQUIDITY_USD:
        reasons.append(f"liq ${liq_usd:.0f} < ${MIN_LIQUIDITY_USD:.0f}")
    if spread > MAX_SPREAD_PCT:
        reasons.append(f"spread {spread:.3f}% > {MAX_SPREAD_PCT}%")
    if vol24 < MIN_DAILY_VOL_USD:
        reasons.append(f"vol24h ${vol24:.0f} < ${MIN_DAILY_VOL_USD:.0f}")

    if reasons:
        result["is_liquid"]     = False
        result["reject_reason"] = " | ".join(reasons)

    # ── Liquidity Score 0-10 ──
    score = 5
    if liq_usd >= 1_000_000:  score = 10
    elif liq_usd >= 500_000:  score = 9
    elif liq_usd >= 200_000:  score = 8
    elif liq_usd >= 100_000:  score = 7
    elif liq_usd >= 50_000:   score = 6
    elif liq_usd >= 10_000:   score = 5
    elif liq_usd >= 5_000:    score = 3
    else:                     score = 1

    if spread > 0.2:  score -= 2
    if spread > 0.1:  score -= 1
    result["liq_score"] = max(0, min(10, score))

    return result


def liquidity_score_adj(liq_data: dict) -> int:
    """Score adjustment berdasarkan liquidity — range -5 s/d +3"""
    if not liq_data.get("is_liquid", True):
        return -10  # hard penalty pair illiquid

    score = liq_data.get("liq_score", 5)
    slip  = liq_data.get("slippage_est", 0)

    adj = 0
    if score >= 9:    adj += 3
    elif score >= 7:  adj += 1
    elif score <= 3:  adj -= 3
    elif score <= 4:  adj -= 1

    if slip > 1.0:  adj -= 2   # slippage > 1% sangat berbahaya
    if slip > 0.5:  adj -= 1

    return max(-5, min(3, adj))
