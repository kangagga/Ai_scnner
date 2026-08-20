# ai_analyst.py - Gemini AI [SWITCH 2026-08-20] pindah dari Groq ke Gemini
import logging
import time
import requests
from datetime import datetime
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)
GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
MAX_RETRIES = 3
RETRY_DELAY = 10

def _call_llm(prompt: str, max_tokens: int = 2048) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "ISI_GEMINI_API_KEY":
        return "Gemini API key belum dikonfigurasi."
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingBudget": 0}},
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=30)
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return "Gemini tidak mengembalikan hasil (kemungkinan diblok safety filter)."
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return "Gemini tidak mengembalikan teks."
            return parts[0].get("text", "").strip()
        except Exception as e:
            if attempt == MAX_RETRIES:
                return f"Gemini error: {e}"
            time.sleep(RETRY_DELAY * attempt)
    return "Gemini tidak merespons."

# [COMPAT] alias supaya bot_auditor.py & code_auditor_llm.py yang masih
# import _call_groq tidak perlu diubah -- backend-nya sekarang Gemini.
_call_groq = _call_llm

def analyse_market_sentiment(top_signals: list) -> str:
    summary = "\n".join([f"- {s.get('symbol','?')} [{s.get('timeframe','?')}]: {s.get('signal','?')} Score:{s.get('score',0)} RSI:{s.get('rsi',0)}" for s in top_signals[:20]])
    today = datetime.now().strftime("%A, %d %B %Y")
    prompt = f"Kamu analis crypto senior. Tanggal: {today}\nSinyal:\n{summary}\n\nBuat laporan analisa lengkap Bahasa Indonesia dengan: kondisi pasar, top sinyal, manajemen risiko, rekomendasi final. Gunakan emoji."
    return _call_groq(prompt, max_tokens=2048)

def analyse_single_signal(signal: dict) -> str:
    prompt = f"Analisa sinyal crypto (Bahasa Indonesia):\nPair:{signal.get('symbol')} TF:{signal.get('timeframe')} Signal:{signal.get('signal')} Score:{signal.get('score')} Entry:{signal.get('entry')} SL:{signal.get('sl')} TP2:{signal.get('tp2')} RSI:{signal.get('rsi')}\nBerikan: validitas, entry optimal, strategi exit, risiko, EKSEKUSI/TUNGGU/SKIP"
    return _call_groq(prompt, max_tokens=800)

def analyse_trade_postmortem(trade: dict) -> str:
    """Analisa singkat kenapa trade ini menang/kalah, untuk pembelajaran pola."""
    result = "WIN" if trade.get("pnl_pct", 0) > 0 else "LOSS" if trade.get("pnl_pct", 0) < 0 else "BREAKEVEN"
    prompt = (
        f"Analisa post-mortem trade crypto (Bahasa Indonesia, singkat max 4 kalimat):\n"
        f"Pair:{trade.get('symbol')} TF:{trade.get('timeframe')} Signal:{trade.get('signal')} "
        f"Entry:{trade.get('entry')} SL:{trade.get('sl')} ExitPrice:{trade.get('exit_price')} "
        f"PnL:{trade.get('pnl_pct')}% Hasil:{result}\n"
        f"Jelaskan singkat: kemungkinan penyebab utama hasil ini (exhaustion/slippage/momentum/false signal), "
        f"dan satu pelajaran konkret untuk sinyal serupa ke depan."
    )
    return _call_groq(prompt, max_tokens=300)


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
