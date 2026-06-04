# ai_analyst.py - Groq AI
import logging
import time
import requests
from datetime import datetime
from config import GROQ_API_KEY

logger = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 3
RETRY_DELAY = 10

def _call_groq(prompt: str, max_tokens: int = 2048) -> str:
    if not GROQ_API_KEY or GROQ_API_KEY == "ISI_GROQ_API":
        return "Groq API key belum dikonfigurasi."
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": 0.4}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * attempt)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == MAX_RETRIES:
                return f"Groq error: {e}"
            time.sleep(RETRY_DELAY * attempt)
    return "Groq tidak merespons."

def analyse_market_sentiment(top_signals: list) -> str:
    summary = "\n".join([f"- {s.get('symbol','?')} [{s.get('timeframe','?')}]: {s.get('signal','?')} Score:{s.get('score',0)} RSI:{s.get('rsi',0)}" for s in top_signals[:20]])
    today = datetime.now().strftime("%A, %d %B %Y")
    prompt = f"Kamu analis crypto senior. Tanggal: {today}\nSinyal:\n{summary}\n\nBuat laporan analisa lengkap Bahasa Indonesia dengan: kondisi pasar, top sinyal, manajemen risiko, rekomendasi final. Gunakan emoji."
    return _call_groq(prompt, max_tokens=2048)

def analyse_single_signal(signal: dict) -> str:
    prompt = f"Analisa sinyal crypto (Bahasa Indonesia):\nPair:{signal.get('symbol')} TF:{signal.get('timeframe')} Signal:{signal.get('signal')} Score:{signal.get('score')} Entry:{signal.get('entry')} SL:{signal.get('sl')} TP2:{signal.get('tp2')} RSI:{signal.get('rsi')}\nBerikan: validitas, entry optimal, strategi exit, risiko, EKSEKUSI/TUNGGU/SKIP"
    return _call_groq(prompt, max_tokens=800)

def filter_signals_ai(signals: list, market_ctx: dict = None) -> list:
    """Filter sinyal pakai Groq AI — buang yang SKIP."""
    if not signals:
        return []

    ctx_info = ""
    if market_ctx:
        btc = market_ctx.get("btc_trend", {})
        fg  = market_ctx.get("fear_greed", {})
        ctx_info = (
            f"\nKonteks Market:\n"
            f"- BTC: {btc.get('trend','N/A')} ({btc.get('strength','N/A')})\n"
            f"- Fear & Greed: {fg.get('value','N/A')} ({fg.get('label','N/A')})\n"
            f"- BUY: {'OK' if market_ctx.get('allow_buy') else 'BLOCKED'}\n"
        )

    summary = "\n".join([
        f"{i+1}. {s.get('symbol')} [{s.get('timeframe')}] {s.get('signal')} "
        f"conf={s.get('confidence')} wr={s.get('win_rate')}% rsi={s.get('rsi',0):.1f} "
        f"macd={s.get('macd_cross','N/A')} volume={s.get('vol_ratio',0):.1f}x "
        f"rr={s.get('rr_ratio','N/A')} candle={s.get('candle_pattern','None')} "
        f"sr_support={s.get('support','N/A')} sr_resist={s.get('resistance','N/A')} "
        f"entry={s.get('entry')} sl={s.get('sl')} tp1={s.get('tp1')}"
        for i, s in enumerate(signals)
    ])

    prompt = f"""Kamu risk manager crypto. Evaluasi sinyal berikut dan tentukan mana yang layak dieksekusi.
{ctx_info}
Sinyal:
{summary}

Untuk setiap sinyal, jawab HANYA dengan format:
1. EKSEKUSI
2. SKIP
3. EKSEKUSI
dst.

Kriteria SKIP:
- Win rate < 40%
- Confidence < 50
- RSI > 75 untuk SELL atau RSI < 25 untuk BUY (oversold/overbought ekstrem)
- R:R < 1.5
- MACD berlawanan arah sinyal (Bull Building tapi SELL, atau Bear Building tapi BUY)
- Volume Dry-Up tanpa konfirmasi momentum
- Sinyal SETUP dengan confidence rendah < 55
- PENGECUALIAN: Jika win rate >= 70% dan conf >= 60, SELALU EKSEKUSI apapun kondisinya

Kriteria EKSEKUSI:
- Win rate >= 50%
- Confidence >= 55
- MACD searah sinyal
- RSI tidak ekstrem (25-75)
- R:R >= 2.0
- Ada konfirmasi volume"""

    result = _call_groq(prompt, max_tokens=200)
    logger.info(f"AI Filter result: {result}")

    filtered = []
    lines = result.strip().split("\n")
    for i, s in enumerate(signals):
        if i < len(lines) and "SKIP" in lines[i].upper():
            logger.info(f"AI SKIP: {s.get('symbol')} {s.get('signal')}")
            continue
        filtered.append(s)

    logger.info(f"AI Filter: {len(signals)} → {len(filtered)} sinyal lolos")
    return filtered
