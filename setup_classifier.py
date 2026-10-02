def get_setup_label(s: dict) -> dict:
    score = s.get("score", 0) or 0
    rr = s.get("rr_ratio", 0) or 0
    vol = s.get("volume_ratio", 0) or 0
    adx = s.get("regime_adx") or s.get("adx") or 0
    rsi = s.get("rsi", 50) or 50
    hist = s.get("macd_hist", 0) or 0
    reg = str(s.get("regime", "")).upper()
    ema = str(s.get("ema_trend", ""))
    sig = str(s.get("signal", "")).upper()
    up = "Bullish" in ema or "Above" in ema
    dn = "Bearish" in ema or "Below" in ema
    try:
        e200 = float(s.get("ema200", 0) or 0)
        px = float(s.get("entry", 0) or 0)
    except (TypeError, ValueError):
        e200 = px = 0
    if e200 > 0 and px > 0:
        up = px > e200
        dn = px < e200
    sup = 0
    weak = 0
    flag = False
    if adx >= 25 or "BREAKOUT" in reg or "STRONG" in reg:
        sup += 1
    if vol >= 1.5:
        sup += 1
    if 0 < vol < 1.0:
        weak += 1
    if "BUY" in sig:
        sup += up
        sup += hist > 0
        sup += 52 <= rsi <= 72
        if dn:
            weak += 1
            flag = True
        if hist < 0:
            weak += 1
            flag = True
        if rsi < 45:
            weak += 1
        if rsi > 75:
            flag = True
    elif "SELL" in sig:
        sup += dn
        sup += hist < 0
        sup += 28 <= rsi <= 48
        if up:
            weak += 1
            flag = True
        if hist > 0:
            weak += 1
            flag = True
        if rsi > 55:
            weak += 1
        if rsi < 25:
            flag = True
    if not (s.get("is_default", True) or s.get("data_quality") is None):
        if (s.get("win_rate", 0) or 0) < 50:
            flag = True
    if score < 55 or rr < 1.5 or (0 < adx < 18) or weak >= 2:
        return {"setup_emoji": "🔴", "setup_label": "LEMAH"}
    if score >= 80 and rr >= 2.0 and sup >= 3 and weak == 0 and not flag:
        return {"setup_emoji": "🌟", "setup_label": "POTENSIAL TINGGI"}
    if score >= 70 and rr >= 2.0 and sup >= 3 and weak == 0:
        return {"setup_emoji": "🟢", "setup_label": "KUAT"}
    return {"setup_emoji": "🟡", "setup_label": "CUKUP"}
