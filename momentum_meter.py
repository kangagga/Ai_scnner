def _f(s, k, d=0.0):
    try:
        v = s.get(k, d)
        return float(v) if v is not None else d
    except Exception:
        return d

def get_momentum_meter(s: dict) -> dict:
    sig = str(s.get("signal", "")).upper()
    buy = "BUY" in sig
    sell = "SELL" in sig
    d = 1 if buy else (-1 if sell else 0)
    vol = _f(s, "volume_ratio") or _f(s, "vol_ratio")
    adx = _f(s, "adx") or _f(s, "regime_adx")
    mh = _f(s, "macd_hist"); mh0 = _f(s, "macd_hist_prev")
    rsi = _f(s, "rsi"); rsi0 = _f(s, "rsi_prev")
    adx0 = _f(s, "adx_prev"); vol0 = _f(s, "vol_ratio_prev")
    trend = str(s.get("ema_trend", "")).upper()

    pts = 0.0
    pts += 25 * max(0.0, min(1.0, (vol - 1.0) / 2.0))
    pts += 20 * max(0.0, min(1.0, (adx - 18.0) / 22.0))
    if d and mh * d > 0:
        pts += 10
        if abs(mh) > abs(mh0) or mh0 * d <= 0:
            pts += 10
    if d == 1:
        pts += 15 if 55 <= rsi <= 70 else (7 if 50 <= rsi < 55 or 70 < rsi <= 78 else 0)
        pts += 10 if "BULL" in trend else 0
    elif d == -1:
        pts += 15 if 30 <= rsi <= 45 else (7 if 22 <= rsi < 30 or 45 < rsi <= 50 else 0)
        pts += 10 if "BEAR" in trend else 0
    if d and rsi0 and (rsi - rsi0) * d > 0:
        pts += 10
    level = int(round(max(0, min(100, pts))))

    have_prev = bool(mh0 or adx0 or vol0)
    up = dn = 0
    spike = False
    if have_prev and d:
        if abs(mh) > abs(mh0) and mh * d > 0: up += 1
        elif abs(mh) < abs(mh0): dn += 1
        if adx > adx0: up += 1
        elif adx < adx0: dn += 1
        if vol > vol0: up += 1
        elif vol < vol0: dn += 1
        spike = (vol0 > 0 and vol >= 1.8 * vol0 and vol >= 1.5) or \
                (mh0 and abs(mh) >= 2.0 * abs(mh0) and mh * d > 0)
    if up >= 2 and up > dn:
        tr_emoji, tr_label = "🔼", "MENGUAT"
    elif dn >= 2 and dn > up:
        tr_emoji, tr_label = "🔽", "MELEMAH"
    else:
        tr_emoji, tr_label = "▶", "STABIL"

    if level >= 80: lv = "SANGAT KUAT"
    elif level >= 60: lv = "KUAT"
    elif level >= 40: lv = "SEDANG"
    else: lv = "LEMAH"
    bar = "█" * (level // 10) + "░" * (10 - level // 10)
    return {"momentum_level": level, "momentum_level_label": lv,
            "momentum_trend": tr_label, "momentum_trend_emoji": tr_emoji,
            "momentum_spike": bool(spike), "momentum_bar": bar}
