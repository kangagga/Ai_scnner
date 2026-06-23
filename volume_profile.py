"""
VWAP + Volume Profile + Buy/Sell Pressure
Dari recent trades Gate.io API
"""
import requests, time

_BASE  = "https://api.gateio.ws/api/v4"
_CACHE = {}
_TTL   = 60  # detik

def _fetch_trades(symbol: str, limit: int = 500) -> list:
    key = f"trades_{symbol}"
    now = time.time()
    if key in _CACHE and now - _CACHE[key]["ts"] < _TTL:
        return _CACHE[key]["data"]
    try:
        r = requests.get(f"{_BASE}/spot/trades",
                         params={"currency_pair": symbol, "limit": limit},
                         timeout=5)
        if r.status_code == 200:
            data = r.json()
            _CACHE[key] = {"ts": now, "data": data}
            return data
    except Exception:
        pass
    return []

def get_volume_profile(symbol: str) -> dict:
    """
    Return dict:
      vwap              : Volume Weighted Average Price
      price_vs_vwap     : % harga terakhir vs VWAP (+above, -below)
      buy_volume        : total volume transaksi buy
      sell_volume       : total volume transaksi sell
      buy_sell_ratio    : buy_vol / sell_vol
      buy_pressure      : 'STRONG'/'MODERATE'/'WEAK'
      poc_price         : Price Of Control (harga dengan volume terbanyak)
      poc_vs_price      : % POC vs harga terakhir
      large_trade_bias  : bias dari transaksi besar ('BUY'/'SELL'/'NEUTRAL')
      vp_score_adj      : score adjustment -8 s/d +8
    """
    result = {
        "vwap"            : 0.0,
        "price_vs_vwap"   : 0.0,
        "buy_volume"      : 0.0,
        "sell_volume"     : 0.0,
        "buy_sell_ratio"  : 1.0,
        "buy_pressure"    : "NEUTRAL",
        "poc_price"       : 0.0,
        "poc_vs_price"    : 0.0,
        "large_trade_bias": "NEUTRAL",
        "vp_score_adj"    : 0,
    }

    trades = _fetch_trades(symbol, limit=500)
    if not trades:
        return result

    # Parse
    prices  = []
    amounts = []
    sides   = []
    for t in trades:
        try:
            prices.append(float(t["price"]))
            amounts.append(float(t["amount"]))
            sides.append(t["side"])
        except Exception:
            continue

    if not prices:
        return result

    # ── VWAP ──
    pv  = sum(p * a for p, a in zip(prices, amounts))
    vol = sum(amounts)
    vwap = pv / vol if vol > 0 else prices[0]
    result["vwap"] = round(vwap, 6)

    last_price = prices[0]  # trades diurutkan terbaru dulu
    result["price_vs_vwap"] = round((last_price - vwap) / vwap * 100, 3)

    # ── Buy/Sell Volume ──
    buy_vol  = sum(a for a, s in zip(amounts, sides) if s == "buy")
    sell_vol = sum(a for a, s in zip(amounts, sides) if s == "sell")
    result["buy_volume"]  = round(buy_vol, 4)
    result["sell_volume"] = round(sell_vol, 4)

    ratio = buy_vol / sell_vol if sell_vol > 0 else 2.0
    result["buy_sell_ratio"] = round(ratio, 3)

    if ratio >= 1.5:
        result["buy_pressure"] = "STRONG"
    elif ratio >= 1.1:
        result["buy_pressure"] = "MODERATE"
    elif ratio <= 0.67:
        result["buy_pressure"] = "WEAK"
    else:
        result["buy_pressure"] = "NEUTRAL"

    # ── POC (Price Of Control) ──
    # Bagi harga ke 20 bucket, cari yang volume terbanyak
    if len(prices) >= 10:
        min_p, max_p = min(prices), max(prices)
        rng = max_p - min_p
        if rng > 0:
            buckets = {}
            n_buckets = 20
            for p, a in zip(prices, amounts):
                idx = min(int((p - min_p) / rng * n_buckets), n_buckets - 1)
                buckets[idx] = buckets.get(idx, 0) + a
            poc_idx  = max(buckets, key=buckets.get)
            poc_price = min_p + (poc_idx + 0.5) * rng / n_buckets
            result["poc_price"]    = round(poc_price, 6)
            result["poc_vs_price"] = round((last_price - poc_price) / poc_price * 100, 3)

    # ── Large Trade Bias (top 10% volume trades) ──
    threshold = sorted(amounts, reverse=True)[max(1, len(amounts)//10)]
    large_buy  = sum(a for a, s in zip(amounts, sides) if s == "buy"  and a >= threshold)
    large_sell = sum(a for a, s in zip(amounts, sides) if s == "sell" and a >= threshold)
    if large_buy > large_sell * 1.3:
        result["large_trade_bias"] = "BUY"
    elif large_sell > large_buy * 1.3:
        result["large_trade_bias"] = "SELL"
    else:
        result["large_trade_bias"] = "NEUTRAL"

    # ── Score Adjustment ──
    result["vp_score_adj"] = _calc_vp_adj(result)
    return result


def _calc_vp_adj(vp: dict) -> int:
    adj = 0
    # Akan dipakai oleh scanner — signal belum diketahui di sini
    # Adjustment murni berdasarkan kondisi market (positif = bullish bias)

    ratio = vp["buy_sell_ratio"]
    if ratio >= 1.5:   adj += 4
    elif ratio >= 1.2: adj += 2
    elif ratio <= 0.67: adj -= 4
    elif ratio <= 0.83: adj -= 2

    pvwap = vp["price_vs_vwap"]
    if pvwap > 0.3:    adj += 2   # harga di atas VWAP
    elif pvwap < -0.3: adj -= 2   # harga di bawah VWAP

    if vp["large_trade_bias"] == "BUY":  adj += 2
    if vp["large_trade_bias"] == "SELL": adj -= 2

    return max(-8, min(8, adj))


def vp_score_adjustment(vp: dict, signal: str) -> int:
    """Konversi VP score ke adjustment sesuai arah sinyal"""
    base = vp.get("vp_score_adj", 0)
    is_buy  = signal.startswith("BUY")
    is_sell = signal.startswith("SELL")
    # Jika sinyal searah dengan bias VP → bonus, berlawanan → penalty
    if is_buy:  return base        # positif = konfirmasi BUY
    if is_sell: return -base       # balik tanda untuk SELL
    return 0
