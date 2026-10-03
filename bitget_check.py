import time
import requests

_CACHE = {}
_URL = "https://api.bitget.com/api/v2/mix/market/merge-depth?productType=USDT-FUTURES&limit=50&symbol="


def _walk(levels, usd):
    got = cost = 0.0
    for p, q in levels:
        p = float(p)
        q = float(q)
        take = min(q * p, usd - cost)
        cost += take
        got += take / p
        if cost >= usd:
            break
    if got and cost >= usd * 0.999:
        return cost / got
    return None


def get_bitget_futures(symbol, side="BUY"):
    key = (symbol, side)
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < 300:
        return _CACHE[key][1]
    try:
        d = requests.get(_URL + symbol, timeout=5).json()
    except Exception:
        return None
    code = d.get("code")
    if code == "40034":
        res = {"listed": False}
    elif code == "00000":
        a = d["data"]["asks"]
        b = d["data"]["bids"]
        a0 = float(a[0][0])
        b0 = float(b[0][0])
        sp = (a0 - b0) / ((a0 + b0) / 2) * 100
        lv, ref = (a, a0) if side == "BUY" else (b, b0)
        w = _walk(lv, 1000)
        sl = abs(w / ref - 1) * 100 if w else None
        res = {"listed": True, "spread": round(sp, 4), "slip": None if sl is None else round(sl, 4)}
    else:
        return None
    _CACHE[key] = (now, res)
    return res


def get_bitget_line(s):
    sig = str(s.get("signal", "")).upper()
    side = "SELL" if "SELL" in sig else "BUY"
    r = get_bitget_futures(s.get("symbol", ""), side)
    if r is None:
        return "🏦 Bitget : ❓ data tidak tersedia\n"
    if not r["listed"]:
        return "🏦 Bitget : ❌ Tidak listing di futures\n"
    if r["slip"] is None:
        return "🏦 Bitget : 🔴 order book tipis (<$1000)\n"
    if r["slip"] < 0.5 and r["spread"] <= 0.10:
        e = "✅"
    elif r["slip"] <= 1.0 and r["spread"] <= 0.25:
        e = "⚠️"
    else:
        e = "🔴"
    return f"🏦 Bitget : {e} spread {r['spread']}% | slip $1000 {r['slip']}%\n"
