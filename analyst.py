# ============================================================
#  ai_analyst.py  –  Analisa sentimen via Groq AI (FIXED)
#  Groq: gratis, cepat, 14400 req/hari
# ============================================================
import logging
import time
import requests
from datetime import datetime
from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

MAX_RETRIES = 3
RETRY_DELAY = 10


def _call_groq(prompt: str, max_tokens: int = 2048) -> str:
    if not GROQ_API_KEY or GROQ_API_KEY == "ISI_GROQ_API":
        return "⚠️ Groq API key belum dikonfigurasi."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.4,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                GROQ_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if resp.status_code == 429:
                wait = RETRY_DELAY * attempt
                logger.warning(f"Groq rate limit (429) — tunggu {wait}s, retry {attempt}/{MAX_RETRIES}")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        except requests.exceptions.HTTPError as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                logger.warning(f"Groq HTTP error: {e} — retry {attempt}/{MAX_RETRIES} dalam {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"Groq gagal setelah {MAX_RETRIES} retry: {e}")
                return "❌ Groq AI tidak tersedia saat ini. Coba lagi nanti."

        except Exception as e:
            logger.error(f"Groq error: {e}")
            return f"❌ Gagal menghubungi Groq AI: {e}"

    return "❌ Groq AI tidak merespons setelah beberapa percobaan."


def analyse_market_sentiment(top_signals: list) -> str:
    summary = "\n".join([
        f"- {s.get('symbol','?')} [{s.get('timeframe','?')}]: {s.get('signal','?')} | "
        f"Score:{s.get('score',0)} | RSI:{s.get('rsi',0)} | "
        f"MACD:{s.get('macd_cross','N/A')} | "
        f"EMA:{s.get('ema_trend','N/A')} | "
        f"Vol:{s.get('volume_label','N/A')} | "
        f"WinRate:{s.get('win_rate',0)}%"
        for s in top_signals[:20]
    ])
    today = datetime.now().strftime("%A, %d %B %Y")

    prompt = f"""Kamu adalah analis crypto profesional senior dengan pengalaman 15+ tahun.

Tanggal: {today}

SINYAL CRYPTO TERATAS (score ≥85):
{summary}

Buat laporan analisa LENGKAP dalam Bahasa Indonesia:

## 1. 📊 KONDISI PASAR CRYPTO HARI INI
- Sentimen pasar (risk-on / risk-off)
- Dominasi BTC & kondisi altcoin season
- Level Fear & Greed estimasi

## 2. 🔥 TOP 5 SINYAL TERPILIH
Untuk tiap sinyal: alasan entry, konfluensi teknikal, level kunci, outlook.

## 3. 📰 SENTIMEN & BERITA KRIPTO
- Event/berita kripto yang kemungkinan berpengaruh hari ini
- Sentimen komunitas & institusional

## 4. ⚠️ MANAJEMEN RISIKO
- Rekomendasi ukuran posisi
- Maks drawdown
- Pair yang perlu dihindari hari ini

## 5. 📈 STATISTIK WIN RATE
- Estimasi win rate portfolio sinyal ini
- Expected value per trade
- Rata-rata R:R

## 6. 🎯 REKOMENDASI FINAL
- 3 sinyal terbaik untuk dieksekusi
- Waktu entry optimal
- Catatan khusus hari ini

Gunakan emoji, jelas, actionable."""

    logger.info("Mengirim ke Groq AI…")
    return _call_groq(prompt, max_tokens=2048)


def analyse_single_signal(signal: dict) -> str:
    prompt = f"""Analisa sinyal crypto ini secara mendalam (Bahasa Indonesia):

Pair     : {signal.get('symbol','?')}
Timeframe: {signal.get('timeframe','?')}
Signal   : {signal.get('signal','?')}
Score    : {signal.get('score',0)}/100
Entry    : {signal.get('entry','?')}
SL       : {signal.get('sl','?')}
TP1/2/3  : {signal.get('tp1','?')} / {signal.get('tp2','?')} / {signal.get('tp3','N/A')}
R:R      : {signal.get('rr_ratio','?')}

Indikator:
RSI:{signal.get('rsi','?')} | MACD:{signal.get('macd_cross','N/A')} (hist:{signal.get('macd_hist','N/A')})
EMA:{signal.get('ema_trend','N/A')} | BB:{signal.get('bb_position','N/A')} | Stoch:{signal.get('stoch_k','?')} ({signal.get('stoch_zone','N/A')})
Volume:{signal.get('volume_label','N/A')} ({signal.get('volume_ratio','?')}x)
Support:{signal.get('support','?')} | Resist:{signal.get('resistance','?')}

Berikan:
1. Validitas sinyal & konfluensi indikator
2. Level entry optimal
3. Strategi exit detail
4. Risiko utama
5. Rekomendasi: EKSEKUSI / TUNGGU / SKIP"""

    return _call_groq(prompt, max_tokens=800)
