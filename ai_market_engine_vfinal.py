# ============================================================
# AI ENGINE FINAL STABLE (NO DEPENDENCY ERROR)
# ============================================================

def generate_signal(
    symbol,
    price,
    df_d1,
    df_h4,
    ema_fast,
    ema_mid,
    ema_slow,
    sentiment_text=None
):

    # =========================
    # SIMPLE TREND CHECK
    # =========================
    trend = "BULLISH" if ema_fast > ema_slow else "BEARISH"

    if trend == "BEARISH":
        return None

    # =========================
    # SUPPORT / RESISTANCE SIMPLE
    # =========================
    support = float(df_h4["low"].tail(50).min())
    resistance = float(df_h4["high"].tail(50).max())
    pivot = (support + resistance) / 2

    # =========================
    # SCORE SYSTEM SIMPLE & SAFE
    # =========================
    score = 60

    if ema_fast > ema_mid > ema_slow:
        score += 20

    if price < resistance * 0.98:
        score += 10

    # =========================
    # FINAL RULE
    # =========================
    if score >= 80:
        return {
            "symbol": symbol,
            "signal": "BUY",
            "score": score,
            "support": support,
            "resistance": resistance,
            "pivot": pivot
        }

    return None
