"""
Orderbook Imbalance + Spread + Liquidity Score
Dipanggil di _analyse_single sebelum SMC layer
"""
import requests, time, functools

_BASE = "https://api.gateio.ws/api/v4"
_CACHE = {}
_CACHE_TTL = 30  # detik

def _fetch_orderbook(symbol: str, depth: int = 20) -> dict:
    key = f"ob_{symbol}"
    now = time.time()
    if key in _CACHE and now - _CACHE[key]["ts"] < _CACHE_TTL:
        return _CACHE[key]["data"]
    try:
        r = requests.get(f"{_BASE}/spot/order_book",
                         params={"currency_pair": symbol, "limit": depth},
                         timeout=4)
        if r.status_code == 200:
            data = r.json()
            _CACHE[key] = {"ts": now, "data": data}
            return data
    except Exception:
        pass
    return {}

def _fetch_funding(symbol: str) -> float:
    """Ambil funding rate futures (jika tersedia)"""
    contract = symbol  # BTC_USDT format sama
    key = f"fr_{symbol}"
    now = time.time()
    if key in _CACHE and now - _CACHE[key]["ts"] < 300:  # cache 5 menit
        return _CACHE[key]["data"]
    try:
        r = requests.get(f"{_BASE}/futures/usdt/funding_rate",
                         params={"contract": contract, "limit": 1},
                         timeout=4)
        if r.status_code == 200:
            data = r.json()
            rate = float(data[0].get("r", 0)) if data else 0.0
            _CACHE[key] = {"ts": now, "data": rate}
            return rate
    except Exception:
        pass
    return 0.0

def get_orderbook_features(symbol: str) -> dict:
    """
    Return dict fitur orderbook:
      ob_imbalance    : -1.0 s/d +1.0 (positif = bid lebih kuat)
      ob_spread_pct   : spread dalam % dari mid price
      ob_liquidity    : total volume bid+ask top 20
      ob_bid_wall     : ada bid wall besar? (True/False)
      ob_ask_wall     : ada ask wall besar?
      ob_pressure     : 'BUY' / 'SELL' / 'NEUTRAL'
      funding_rate    : float (positif = long bias, negatif = short bias)
      funding_signal  : 'LONG_CROWDED'/'SHORT_CROWDED'/'NEUTRAL'
    """
    result = {
        "ob_imbalance"  : 0.0,
        "ob_spread_pct" : 0.0,
        "ob_liquidity"  : 0.0,
        "ob_bid_wall"   : False,
        "ob_ask_wall"   : False,
        "ob_pressure"   : "NEUTRAL",
        "funding_rate"  : 0.0,
        "funding_signal": "NEUTRAL",
    }

    ob = _fetch_orderbook(symbol, depth=20)
    if not ob:
        return result

    bids = ob.get("bids", [])
    asks = ob.get("asks", [])
    if not bids or not asks:
        return result

    # ── Bid/Ask volume ──
    bid_vol = sum(float(b[1]) for b in bids)
    ask_vol = sum(float(a[1]) for a in asks)
    total   = bid_vol + ask_vol

    if total > 0:
        result["ob_imbalance"] = round((bid_vol - ask_vol) / total, 3)

    # ── Spread ──
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    mid      = (best_bid + best_ask) / 2
    if mid > 0:
        result["ob_spread_pct"] = round((best_ask - best_bid) / mid * 100, 4)

    # ── Liquidity ──
    result["ob_liquidity"] = round(total, 2)

    # ── Wall detection (volume > 3x rata-rata) ──
    avg_bid = bid_vol / len(bids) if bids else 0
    avg_ask = ask_vol / len(asks) if asks else 0
    result["ob_bid_wall"] = any(float(b[1]) > avg_bid * 3 for b in bids[:5])
    result["ob_ask_wall"] = any(float(a[1]) > avg_ask * 3 for a in asks[:5])

    # ── Pressure label ──
    imb = result["ob_imbalance"]
    if imb >= 0.15:
        result["ob_pressure"] = "BUY"
    elif imb <= -0.15:
        result["ob_pressure"] = "SELL"
    else:
        result["ob_pressure"] = "NEUTRAL"

    # ── Funding Rate ──
    fr = _fetch_funding(symbol)
    result["funding_rate"] = round(fr * 100, 4)  # dalam %

    if fr > 0.0005:       # > 0.05% per 8 jam = long crowded
        result["funding_signal"] = "LONG_CROWDED"
    elif fr < -0.0005:    # < -0.05% = short crowded
        result["funding_signal"] = "SHORT_CROWDED"
    else:
        result["funding_signal"] = "NEUTRAL"

    return result


def ob_score_adjustment(ob_features: dict, signal: str) -> int:
    """
    Konversi orderbook features ke score adjustment untuk scanner
    Range: -10 s/d +10
    """
    adj   = 0
    imb   = ob_features.get("ob_imbalance", 0)
    press = ob_features.get("ob_pressure", "NEUTRAL")
    fund  = ob_features.get("funding_signal", "NEUTRAL")
    spread= ob_features.get("ob_spread_pct", 0)
    bid_w = ob_features.get("ob_bid_wall", False)
    ask_w = ob_features.get("ob_ask_wall", False)

    is_buy  = signal.startswith("BUY")
    is_sell = signal.startswith("SELL")

    # Imbalance confirmation
    if is_buy  and press == "BUY":   adj += 5
    if is_sell and press == "SELL":  adj += 5
    if is_buy  and press == "SELL":  adj -= 5
    if is_sell and press == "BUY":   adj -= 5

    # Funding rate (contrarian — long crowded = SELL lebih baik)
    if is_buy  and fund == "SHORT_CROWDED": adj += 3  # short squeeze potential
    if is_sell and fund == "LONG_CROWDED":  adj += 3  # long squeeze potential
    if is_buy  and fund == "LONG_CROWDED":  adj -= 3  # sudah terlalu banyak long
    if is_sell and fund == "SHORT_CROWDED": adj -= 3

    # Wall sebagai support/resistance
    if is_buy  and bid_w: adj += 2  # bid wall = support kuat
    if is_sell and ask_w: adj += 2  # ask wall = resistance kuat
    if is_buy  and ask_w: adj -= 2  # ask wall = hambatan naik

    # Spread penalty (illiquid)
    if spread > 0.1:  adj -= 3  # spread lebar = slippage besar
    if spread > 0.5:  adj -= 5  # sangat illiquid

    return max(-10, min(10, adj))
