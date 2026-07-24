# ============================================================
#  telegram_sender.py  –  Kirim sinyal ke Telegram dengan Cooldown
# ============================================================
import logging
import time
import requests
from datetime import datetime, timedelta, timezone
from config import BOT_TOKEN, CHAT_ID, SIGNAL_THRESHOLD

logger = logging.getLogger(__name__)
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Cooldown per simbol (agar tidak spam sinyal sama)
COOLDOWN_MINUTES = 30
_LAST_SIGNALS_FILE = "last_signals.json"

def _load_last_signals():
    try:
        import json
        with open(_LAST_SIGNALS_FILE) as f:
            raw = json.load(f)
        result = {}
        for k, v in raw.items():
            result[k] = {
                "signal": v["signal"], "score": v["score"],
                "time": datetime.fromisoformat(v["time"]),
            }
        return result
    except Exception:
        return {}

def _save_last_signals():
    try:
        import json
        raw = {k: {"signal": v["signal"], "score": v["score"], "time": v["time"].isoformat()}
               for k, v in LAST_SIGNALS.items()}
        with open(_LAST_SIGNALS_FILE, "w") as f:
            json.dump(raw, f)
    except Exception as e:
        logger.warning(f"Gagal simpan last_signals: {e}")

LAST_SIGNALS = _load_last_signals()

# Emoji yang benar (bukan karakter aneh)
SIGNAL_EMOJI = {
    "STRONG BUY":  "🟢🟢", "BUY":       "🟢",
    "WEAK BUY":    "🔼",   "NEUTRAL":   "⚪",
    "WEAK SELL":   "🔽",   "SELL":      "🔴",
    "STRONG SELL": "🔴🔴",
}
TF_LABEL = {"1h": "1 Jam", "4h": "4 Jam", "1d": "Daily"}


def should_send_signal(symbol: str, signal: str, score: int) -> bool:
    """Cek apakah sinyal ini boleh dikirim (cooldown 30 menit)"""
    now = datetime.now(timezone(timedelta(hours=7)))
    key = symbol

    if key not in LAST_SIGNALS:
        # Belum pernah kirim, boleh kirim
        LAST_SIGNALS[key] = {
            "signal": signal,
            "score": score,
            "time": now
        }
        _save_last_signals()
        return True

    last = LAST_SIGNALS[key]
    # Jika sinyal berubah (misal dari BUY jadi SELL) -> boleh kirim
    if last["signal"] != signal:
        LAST_SIGNALS[key] = {"signal": signal, "score": score, "time": now}
        _save_last_signals()
        return True

    # Jika sinyal sama, cek cooldown
    if now - last["time"] > timedelta(minutes=COOLDOWN_MINUTES):
        LAST_SIGNALS[key] = {"signal": signal, "score": score, "time": now}
        _save_last_signals()
        return True

    # Masih dalam cooldown
    logger.debug(f"Cooldown {symbol} ({signal}) - skip kirim")
    return False


# ══════════════════════════════════════════════════════════
# [UI MENU 2026-07-10] Reply Keyboard untuk navigasi tombol
# ══════════════════════════════════════════════════════════
MAIN_MENU_KEYBOARD = {
    "keyboard": [
        ["📊 Status", "📡 Live Positions"],
        ["🔍 Analyze Pair", "🎯 Execute Manual"],
        ["⭐ Watchlist", "📈 Pair Status"],
        ["📊 Win Rate Pair", "📉 Sinyal Terakhir"],
        ["🔄 Scan Manual", "⚠️ Reset Streak"],
        ["❓ Bantuan"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}

WATCHLIST_PAIRS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]

WATCHLIST_KEYBOARD = {
    "keyboard": [
        ["BTCUSDT", "ETHUSDT"],
        ["BNBUSDT", "SOLUSDT"],
        ["XRPUSDT", "ADAUSDT"],
        ["⬅️ Kembali"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}

def _direction_keyboard(symbol: str) -> dict:
    return {
        "keyboard": [
            [f"🟢 BUY {symbol}", f"🔴 SELL {symbol}"],
            ["⬅️ Kembali"],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }

def _chart_buttons(symbol: str) -> list:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    tv_symbol = f"{base}USDT"
    tradingview_url = f"https://www.tradingview.com/symbols/{tv_symbol}/"
    coingecko_url = f"https://www.coingecko.com/en/search?query={base}"
    return [[
        {"text": "📈 TradingView", "url": tradingview_url},
        {"text": "🦎 CoinGecko", "url": coingecko_url},
    ]]

def _send_with_url_button(text: str, buttons: list) -> bool:
    if not BOT_TOKEN or BOT_TOKEN == "ISI_BOT_TOKEN":
        logger.warning("Bot token belum diisi di config.py")
        return False
    try:
        payload = {
            "chat_id": CHAT_ID, "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": {"inline_keyboard": buttons},
        }
        resp = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=15)
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram: {data.get('description')}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False

# State sederhana untuk menu yang butuh input lanjutan (misal nama pair)
_pending_action: dict = {}  # chat_id -> "analyze" | "execute"

def _send_with_keyboard(text: str, keyboard: dict = None) -> bool:
    if not BOT_TOKEN or BOT_TOKEN == "ISI_BOT_TOKEN":
        logger.warning("Bot token belum diisi di config.py")
        return False
    try:
        payload = {
            "chat_id": CHAT_ID, "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            payload["reply_markup"] = keyboard
        resp = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=15)
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram: {data.get('description')}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def _send(text: str) -> bool:
    if not BOT_TOKEN or BOT_TOKEN == "ISI_BOT_TOKEN":
        logger.warning("Bot token belum diisi di config.py")
        return False
    try:
        resp = requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text,
                  "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram: {data.get('description')}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def _chunks(text: str, limit=4000) -> list:
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur:
        chunks.append(cur)
    return chunks


def fmt_price(val) -> str:
    """Format harga agar mudah dibaca."""
    try:
        v = float(val)
        if v == 0:
            return "N/A"
        if v >= 1000:
            return f"{v:,.2f}"
        elif v >= 1:
            return f"{v:.4f}"
        elif v >= 0.0001:
            return f"{v:.6f}"
        else:
            # Tampilkan desimal signifikan
            return f"{v:.8f}".rstrip('0')
    except:
        return str(val)


def _fmt_smc(s: dict) -> str:
    """Tampilkan SMC block di pesan Telegram jika tersedia"""
    report = s.get("smc_report", "")
    bonus  = s.get("smc_bonus", 0)
    raw    = s.get("score_raw", s.get("score", 0))
    if not report or bonus == 0:
        return ""
    sign = f"+{bonus}" if bonus > 0 else str(bonus)
    ob_b = s.get("ob_bonus", 0)
    vp_b = s.get("vp_bonus", 0)
    ob_s = f"{ob_b:+}(OB)" if ob_b != 0 else ""
    vp_s  = f"{vp_b:+}(VP)"  if vp_b  != 0 else ""
    liq_b = s.get("liq_adj", 0)
    liq_s = f"{liq_b:+}(LQ)" if liq_b != 0 else ""
    trail = f"{raw} {sign}"
    if ob_s:  trail += f" {ob_s}"
    if vp_s:  trail += f" {vp_s}"
    if liq_s: trail += f" {liq_s}"
    trail += f" → <b>{s.get('score',0)}</b>"
    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{report}"
        f"📐 Score   : {trail}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
def get_alert_level(s: dict) -> str:
    """Hitung alert level berdasarkan score final + SMC + win rate.
    Satu sumber kebenaran — dipakai oleh format_signal() dan main.py (gating entry)."""
    score = s.get("score", 0)
    wr    = s.get("win_rate", 0)

    smc_score = s.get("smc_data", {}).get("score", 0)
    smc_valid = s.get("smc_data", {}).get("valid", False)
    # Jika SMC data tersedia → pakai SMC filter, jika tidak → pakai score saja
    smc_available = smc_score > 0 or smc_valid

    if smc_available:
        if not smc_valid:
            # Hard veto: SMC invalid (doji/melawan trend kuat) → maksimal WATCHLIST,
            # tidak peduli seberapa tinggi score_final atau smc_score.
            if score >= 45:
                return "👀 WATCHLIST — PANTAU SAJA"
            else:
                return "💤 MONITOR — JANGAN ENTRY"
        if score >= 65 and smc_score >= 70 and smc_valid and (wr >= 50 or wr == 0):
            return "🚀 EKSEKUSI — ENTRY SEKARANG"
        elif score >= 55 and smc_score >= 50 and smc_valid and (wr >= 40 or wr == 0):
            return "⚡ SIAP ENTRY — KONFIRMASI DULU"
        elif score >= 45:
            return "👀 WATCHLIST — PANTAU SAJA"
        else:
            return "💤 MONITOR — JANGAN ENTRY"
    else:
        # Tanpa SMC: EKSEKUSI tetap wajib wr asli (tidak ada bypass wr==0,
        # karena tanpa SMC sinyal cuma punya satu lapis konfirmasi — score saja).
        if score >= 65 and wr >= 45:
            return "🚀 EKSEKUSI — ENTRY SEKARANG"
        # SIAP ENTRY: boleh bypass wr==0 (data belum cukup), tapi threshold
        # score dinaikkan ke 60 (dari 55) sebagai kompensasi keamanan.
        elif score >= 60 and (wr >= 35 or wr == 0):
            return "⚡ SIAP ENTRY — KONFIRMASI DULU"
        elif score >= 45:
            return "👀 WATCHLIST — PANTAU SAJA"
        else:
            return "💤 MONITOR — JANGAN ENTRY"


def format_signal(s: dict) -> str:
    """Format sinyal dengan aman (semua key pakai .get)"""
    emoji = SIGNAL_EMOJI.get(s.get("signal", "NEUTRAL"), "⚪")
    tf = TF_LABEL.get(s.get("timeframe", "1h"), s.get("timeframe", "1h"))
    now = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m %H:%M")
    score = s.get("score", 0)
    conf  = s.get("confidence", 0)
    wr    = s.get("win_rate", 0)

    # Alert level berdasarkan score final + SMC + win rate (DRY — lihat get_alert_level())
    alert_level = get_alert_level(s)

    # FIX: tandai sinyal yang ternyata duplicate (posisi sudah terbuka, tidak dieksekusi)
    if s.get("is_duplicate"):
        alert_level = "⚠️ SKIPPED - DUPLICATE"

    bar = "█" * int(score / 10) + "░" * (10 - int(score / 10))

    rsi_val = s.get("rsi", 50)
    rsi_s = (f"🔴OB({rsi_val})" if rsi_val > 70
             else f"🟢OS({rsi_val})" if rsi_val < 30
             else f"({rsi_val})")

    win_rate = s.get("win_rate", 0)  # <- ini solusi error sebelumnya
    data_quality   = s.get("data_quality", None)
    similar_cases  = s.get("similar_cases", 0)
    is_default     = s.get("is_default", True)
    if is_default or data_quality is None:
        wr_quality_tag = "⚪(no data)"
    elif data_quality == "HIGH":
        wr_quality_tag = f"🟢(n={similar_cases})"
    elif data_quality == "MEDIUM":
        wr_quality_tag = f"🟡(n={similar_cases})"
    else:
        wr_quality_tag = f"🔴(n={similar_cases}, sample kecil)"

    return (
        f"{'━'*30}\n"
        f"{emoji} <b>{s.get('symbol', '???')}</b> | {tf} | {now}\n"
        f"{'━'*30}\n"
        f"⚠️ Level   : <b>{alert_level}</b>\n"
        f"🌍 Regime  : {s.get('regime_emoji', '➡️')} <b>{s.get('regime', 'UNKNOWN')}</b> | ADX:{s.get('regime_adx', 0)} | {s.get('regime_advice', '')}\n"
        f"📊 Sinyal  : <b>{s.get('signal', 'NEUTRAL')}</b>\n"
        f"🎯 Score   : {score}/100  [{bar}]\n"
        f"📈 WinRate : <b>{win_rate}%</b> {wr_quality_tag}\n\n"
        f"💰 Entry   : <code>{fmt_price(s.get('entry', 0))}</code>\n"
        f"🛑 SL      : <code>{fmt_price(s.get('sl', 0))}</code>\n"
        f"✅ TP1     : <code>{fmt_price(s.get('tp1', 0))}</code> (50% close)\n"
        f"✅ TP2     : <code>{fmt_price(s.get('tp2', 0))}</code> (30% close)\n"
        f"✅ TP3     : <code>{fmt_price(s.get('tp3', 0))}</code> (20% close)\n"
        f"🔄 Trailing: <code>{fmt_price(s.get('trailing_stop', 0))}</code>\n"
        f"⚖️  R:R    : 1:{s.get('rr_ratio', 0)}\n\n"
        f"🕯️ Pattern : {s.get('candle_pattern', 'None')}\n"
        f"📉 RSI     : {rsi_s}\n"
        f"⚡ MACD    : {s.get('macd_cross', 'N/A')} | Hist:{s.get('macd_hist', 'N/A')}\n"
        f"📐 EMA     : {s.get('ema_trend', 'N/A')}\n"
        f"📦 Volume  : {s.get('volume_label', 'N/A')} ({s.get('volume_ratio', 0)}x)\n"
        f"🎲 BB      : {s.get('bb_position', 'N/A')}\n"
        f"🔵 Stoch   : {s.get('stoch_k', 0)} ({s.get('stoch_zone', 'N/A')})\n"
        f"📖 OB      : {s.get('ob_pressure','N/A')} (imb={s.get('ob_imbalance',0):+.2f}) | spread={s.get('ob_spread_pct',0):.3f}%\n"
        f"💸 Funding : {s.get('funding_rate_ob',0):+.4f}% ({s.get('funding_signal','N/A')}) | OB adj={s.get('ob_bonus',0):+d}\n"
        f"📊 VWAP    : {s.get('vwap',0):,.2f} ({s.get('price_vs_vwap',0):+.3f}%) | POC={s.get('poc_price',0):,.2f}\n"
        f"⚖️  B/S     : {s.get('buy_sell_ratio',1):.2f} ({s.get('buy_pressure','N/A')}) | Large={s.get('large_trade_bias','N/A')} | VP adj={s.get('vp_bonus',0):+d}\n"
        f"💧 Liq     : ${s.get('liq_usd',0):,.0f} (score={s.get('liq_score',5)}/10) | slip={s.get('slippage_est',0):.3f}% | adj={s.get('liq_adj',0):+d}\n\n"
        f"{_fmt_smc(s)}"
        f"🏔️  Resist : <code>{s.get('resistance', 'N/A')}</code>\n"
        f"🛡️  Support: <code>{s.get('support', 'N/A')}</code>\n"
        f"📌 Pivot   : <code>{s.get('pivot', 'N/A')}</code>\n"
        f"{'━'*30}\n"
        f"🤖 <i>AI Signal Bot • Threshold {s.get('dynamic_threshold', SIGNAL_THRESHOLD)}</i>"
    )


def send_signal(signal: dict) -> bool:
    """Kirim 1 sinyal (tanpa cooldown)"""
    symbol = signal.get("symbol", "")
    if symbol:
        return _send_with_url_button(format_signal(signal), _chart_buttons(symbol))
    return _send(format_signal(signal))


def send_top_signals(signals: list, delay: float = 1.5) -> int:
    """Kirim top sinyal dengan cooldown per simbol"""
    if not signals:
        _send("📭 Tidak ada sinyal memenuhi threshold saat ini.")
        return 0

    # Filter sinyal yang boleh dikirim (cooldown)
    filtered = []
    for s in signals:
        if should_send_signal(s.get("symbol", ""), s.get("signal", ""), s.get("score", 0)):
            filtered.append(s)

    if not filtered:
        logger.info("Semua sinyal masih dalam cooldown, tidak ada yang dikirim.")
        return 0

    # Kirim header ringkasan
    now = datetime.now(timezone(timedelta(hours=7))).strftime("%A, %d %B %Y %H:%M WIB")
    buy = sum(1 for s in filtered if "BUY" in s.get("signal", ""))
    sell = sum(1 for s in filtered if "SELL" in s.get("signal", ""))
    
    # Hitung avg win_rate hanya dari sinyal yang punya key win_rate
    win_rates = [s.get("win_rate", 0) for s in filtered if "win_rate" in s]
    avg_wr = round(sum(win_rates) / len(win_rates), 1) if win_rates else 0

    _send(
        f"🤖 <b>AI CRYPTO SIGNAL BOT</b>\n"
        f"📅 {now}\n{'═'*28}\n"
        f"📊 Total Sinyal : <b>{len(filtered)}</b>\n"
        f"🟢 BUY          : <b>{buy}</b>\n"
        f"🔴 SELL         : <b>{sell}</b>\n"
        f"🎯 Avg WinRate  : <b>{avg_wr}%</b>\n"
        f"{'═'*28}\n⬇️  Detail sinyal:"
    )
    time.sleep(1)

    sent = 0
    for s in filtered:
        if send_signal(s):
            sent += 1
        time.sleep(delay)

    _send(
        f"✅ <b>{sent}/{len(filtered)} sinyal terkirim</b>\n"
        f"🤖 <i>Powered by Groq AI + Technical Analysis</i>"
    )
    return sent


def _get_auto_vs_manual_summary():
    """Return string ringkasan auto vs manual untuk disisipkan ke laporan harian."""
    try:
        import sqlite3
        conn = sqlite3.connect('virtual_trading.db')
        rows = conn.execute("""
            SELECT
                CASE WHEN signal LIKE '%MANUAL%' THEN 'MANUAL' ELSE 'AUTO' END AS trade_type,
                COUNT(*),
                SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END),
                ROUND(SUM(pnl_usdt), 2)
            FROM virtual_trades
            WHERE closed_at IS NOT NULL AND DATE(closed_at) = DATE('now')
            GROUP BY trade_type
        """).fetchall()
        conn.close()
        if not rows:
            return ""
        stats = {r[0]: r for r in rows}
        lines = "\n⚖️ <b>Auto vs Manual (hari ini)</b>\n"
        for label, icon in [("AUTO", "🤖"), ("MANUAL", "✋")]:
            if label in stats:
                _, total, wins, pnl = stats[label]
                wr = round(100 * wins / total, 1) if total else 0
                pnl_icon = "🟢" if pnl >= 0 else "🔴"
                lines += f"{icon} {label}: {total} trade | WR {wr}% | {pnl_icon} ${pnl:,.2f}\n"
        return lines
    except Exception:
        return ""


def send_daily_report(signals: list, ai_analysis: str) -> bool:
    now = datetime.now(timezone(timedelta(hours=7))).strftime("%A, %d %B %Y")
    if not signals:
        _send(f"📋 <b>Laporan Harian {now}</b>\n\n📭 Tidak ada sinyal aktif.")
        return True

    buy = sum(1 for s in signals if "BUY" in s.get("signal", ""))
    sell = sum(1 for s in signals if "SELL" in s.get("signal", ""))
    top3 = signals[:3]
    
    scores = [s.get("score", 0) for s in signals]
    avg_sc = round(sum(scores) / len(scores), 1) if scores else 0
    
    win_rates = [s.get("win_rate", 0) for s in signals if "win_rate" in s]
    avg_wr = round(sum(win_rates) / len(win_rates), 1) if win_rates else 0

    header = (
        f"📋 <b>LAPORAN HARIAN — {now}</b>\n{'═'*30}\n"
        f"📊 Total Sinyal : <b>{len(signals)}</b>\n"
        f"🟢 BUY          : <b>{buy}</b>\n"
        f"🔴 SELL         : <b>{sell}</b>\n"
        f"🎯 Avg Score    : <b>{avg_sc}/100</b>\n"
        f"📈 Avg WinRate  : <b>{avg_wr}%</b>\n"
        f"{'═'*30}\n🔥 <b>TOP 3 SINYAL:</b>\n"
    )
    for i, s in enumerate(top3, 1):
        emoji = SIGNAL_EMOJI.get(s.get("signal", "NEUTRAL"), "⚪")
        header += (
            f"\n{i}. {emoji} <b>{s.get('symbol', '???')}</b> [{s.get('timeframe', '1h')}]\n"
            f"   {s.get('signal', 'NEUTRAL')} | Score:{s.get('score', 0)} | WR:{s.get('win_rate', 0)}%\n"
            f"   Entry:{s.get('entry', 'N/A')} | TP2:{s.get('tp2', 'N/A')} | SL:{s.get('sl', 'N/A')}\n"
        )
    _send(header)
    time.sleep(1.5)

    # Tambah laporan performance aktual
    try:
        from database import get_realtime_winrate
        perf = get_realtime_winrate()
        if perf["total"] > 0:
            perf_msg = (
                f"📊 <b>PERFORMA AKTUAL BOT</b>\n{'─'*28}\n"
                f"Total Sinyal Selesai : <b>{perf['total']}</b>\n"
                f"Win Rate Aktual      : <b>{perf['win_rate']}%</b>\n"
                f"{'✅ Profitable!' if perf['win_rate'] >= 50 else '⚠️ Perlu evaluasi'}"
            )
            _send(perf_msg)
            time.sleep(1)
    except Exception:
        pass

    # Tambah ringkasan auto vs manual (hari ini)
    try:
        compare_msg = _get_auto_vs_manual_summary()
        if compare_msg:
            _send(compare_msg)
            time.sleep(1)
    except Exception:
        pass

    if ai_analysis:
        for chunk in _chunks(f"🧠 <b>ANALISA GEMINI AI</b>\n{'─'*28}\n{ai_analysis}"):
            _send(chunk)
            time.sleep(1)
    return True


def send_test_message() -> bool:
    return _send(
        f"✅ <b>AI Crypto Signal Bot Aktif!</b>\n\n"
        f"🤖 Terhubung ke Telegram.\n"
        f"⏰ {datetime.now(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"🔍 Memulai scan pasar crypto…"
    )

def send_alert(message: str) -> bool:
    """Kirim pesan teks sederhana ke Telegram (untuk exit monitor, dll)."""
    return _send(message)


# ──────────────────────────────────────────────
#  TELEGRAM COMMAND HANDLER
# ──────────────────────────────────────────────
_last_update_id = 0

def get_updates():
    global _last_update_id
    try:
        r = requests.get(
            f"{API_URL}/getUpdates",
            params={"offset": _last_update_id + 1, "timeout": 5},
            timeout=10
        )
        data = r.json()
        if data.get("ok"):
            return data.get("result", [])
    except Exception:
        pass
    return []

def handle_commands(scan_fn=None):
    """Proses command dari Telegram."""
    global _last_update_id
    updates = get_updates()
    if updates:
        logger.info(f"[CMD] {len(updates)} update diterima")
    for update in updates:
        _last_update_id = update["update_id"]
        msg = update.get("message", {})
        text_raw = msg.get("text", "").strip()
        chat_id = msg.get("chat", {}).get("id")

        if str(chat_id) != str(CHAT_ID):
            logger.warning(f"[CMD] Command dari chat_id tidak dikenal: {chat_id}, diabaikan")
            continue

        text = text_raw.lower()

        # [ALIAS] /b PAIR = BUY cepat, /s PAIR = SELL cepat
        if text.startswith("/b "):
            _alias_parts = text_raw.split(maxsplit=1)
            if len(_alias_parts) == 2:
                text_raw = f"/execute {_alias_parts[1]} BUY"
                text = text_raw.lower()
        elif text.startswith("/s "):
            _alias_parts = text_raw.split(maxsplit=1)
            if len(_alias_parts) == 2:
                text_raw = f"/execute {_alias_parts[1]} SELL"
                text = text_raw.lower()

        # [FIX 2026-07-10] Tombol menu ditangani SEBELUM filter startswith("/")
        if text == "/start" or text == "/menu":
            _pending_action.pop(chat_id, None)
            _send_with_keyboard(
                "🤖 <b>Selamat datang di AI Signal Bot</b>\n"
                "Pilih menu di bawah, atau ketik command manual seperti biasa.",
                MAIN_MENU_KEYBOARD
            )
            continue

        if chat_id in _pending_action:
            action = _pending_action.pop(chat_id)
            if action == "analyze":
                if not text.startswith("/analyze") and not text.startswith("/cek"):
                    text_raw = f"/analyze {text_raw}"
                text = text_raw.lower()
            elif action == "execute":
                if not text.startswith("/execute"):
                    text_raw = f"/execute {text_raw}"
                text = text_raw.lower()
            elif action.startswith("watchlist:"):
                _wl_symbol = action.split(":", 1)[1]
                if text_raw.startswith("🟢 BUY"):
                    text_raw = f"/execute {_wl_symbol} BUY"
                    text = text_raw.lower()
                elif text_raw.startswith("🔴 SELL"):
                    text_raw = f"/execute {_wl_symbol} SELL"
                    text = text_raw.lower()
                else:
                    _send_with_keyboard("🔙 Kembali ke menu utama.", MAIN_MENU_KEYBOARD)
                    continue

        if text_raw == "⭐ Watchlist":
            _send_with_keyboard("⭐ Pilih pair dari watchlist:", WATCHLIST_KEYBOARD)
            continue
        elif text_raw in WATCHLIST_PAIRS:
            _pending_action[chat_id] = f"watchlist:{text_raw}"
            _send_with_keyboard(f"📌 {text_raw} dipilih. Pilih arah:", _direction_keyboard(text_raw))
            continue
        elif text_raw == "⬅️ Kembali":
            _pending_action.pop(chat_id, None)
            _send_with_keyboard("🔙 Kembali ke menu utama.", MAIN_MENU_KEYBOARD)
            continue
        elif text_raw == "📊 Status":
            text = "/status"
        elif text_raw == "📡 Live Positions":
            text = "/live_positions"
        elif text_raw == "🔍 Analyze Pair":
            _pending_action[chat_id] = "analyze"
            _send("🔍 Ketik nama pair yang mau dianalisa, contoh: <code>BTCUSDT</code>")
            continue
        elif text_raw == "🎯 Execute Manual":
            _pending_action[chat_id] = "execute"
            _send("🎯 Ketik: <code>PAIR BUY</code> atau <code>PAIR SELL</code>\nContoh: <code>BTCUSDT BUY</code>")
            continue
        elif text_raw == "📈 Pair Status":
            text = "/pair_status"
        elif text_raw == "📊 Win Rate Pair":
            text = "/winrate_pair"
        elif text_raw == "📉 Sinyal Terakhir":
            text = "/sinyal"
        elif text_raw == "🔄 Scan Manual":
            text = "/scan"
        elif text_raw == "⚠️ Reset Streak":
            text = "/reset_streak"
        elif text_raw == "❓ Bantuan":
            text = "/help"

        if not text.startswith("/"):
            continue

        if text == "/status":
            from risk_manager import get_risk_status
            try:
                status = get_risk_status()
                _send(
                    f"📊 <b>STATUS BOT</b>\n{'═'*25}\n"
                    f"💰 Balance    : ${status.get('balance', 0):,.2f}\n"
                    f"📉 Drawdown   : {status.get('drawdown_pct', 0):.1f}%\n"
                    f"💹 Daily PnL  : ${status.get('daily_pnl', 0):,.2f}\n"
                    f"🔥 Heat       : {status.get('portfolio_heat', 0):.1f}%\n"
                    f"📋 Open Pos   : {status.get('open_positions', 0)}\n"
                    f"🔄 Total Trade: {status.get('total_trades', 0)}\n"
                    f"{'═'*25}\n🤖 AI Signal Bot"
                )
            except Exception as e:
                _send(f"❌ Error status: {e}")

        elif text == "/winrate":
            try:
                from database import get_realtime_winrate
                perf = get_realtime_winrate()
                _send(
                    f"📈 <b>PERFORMA BOT</b>\n{'═'*25}\n"
                    f"Total Selesai : <b>{perf['total']}</b>\n"
                    f"Win Rate      : <b>{perf['win_rate']}%</b>\n"
                    f"{'✅ Profitable!' if perf['win_rate'] >= 50 else '⚠️ Perlu evaluasi'}\n"
                    f"{'═'*25}\n🤖 AI Signal Bot"
                )
            except Exception as e:
                _send(f"❌ Error winrate: {e}")

        elif text == "/sinyal":
            try:
                from database import get_recent_signals
                sigs = get_recent_signals(limit=3)
                if not sigs:
                    _send("📭 Belum ada sinyal tersimpan.")
                else:
                    msg_text = "📋 <b>SINYAL TERAKHIR</b>\n" + "═"*25 + "\n"
                    for s in sigs:
                        msg_text += f"\n🪙 <b>{s[2]}</b> [{s[3]}] {s[4]}\n"
                        msg_text += f"   Entry: {s[8]} | WR: {s[7]}%\n"
                    _send(msg_text)
            except Exception as e:
                _send(f"❌ Error sinyal: {e}")

        elif text == "/scan":
            _send("🔍 Scan manual dimulai... tunggu ~25 menit.")
            if scan_fn:
                import threading
                threading.Thread(target=scan_fn, daemon=True).start()

        elif text == "/live_positions":
            try:
                import sqlite3
                from exit_monitor import get_current_price
                conn = sqlite3.connect('virtual_trading.db')
                rows = conn.execute("""
                    SELECT symbol, signal, entry, sl, tp1, timestamp
                    FROM virtual_trades
                    WHERE closed = 0
                """).fetchall()
                conn.close()

                if not rows:
                    _send("📭 Tidak ada posisi terbuka saat ini.")
                else:
                    profitable = []
                    losing = []

                    for symbol, signal, entry, sl, tp1, ts in rows:
                        try:
                            current = get_current_price(symbol)
                            if current is None or entry == 0:
                                continue
                            direction = "BUY" if signal.startswith("BUY") else "SELL"
                            if direction == "BUY":
                                pnl_pct = (current - entry) / entry * 100
                            else:
                                pnl_pct = (entry - current) / entry * 100

                            row_data = (symbol, signal, entry, current, pnl_pct, sl, tp1)
                            if pnl_pct > 0:
                                profitable.append(row_data)
                            else:
                                losing.append(row_data)
                        except Exception as _pe:
                            logger.debug(f"[LIVE_POS] Gagal ambil harga {symbol}: {_pe}")
                            continue

                    msg = "📡 <b>POSISI TERBUKA LIVE</b>\n" + "═"*25 + "\n"

                    if profitable:
                        msg += "\n✅ <b>PROFIT (unrealized)</b>\n"
                        for symbol, signal, entry, current, pnl_pct, sl, tp1 in profitable:
                            msg += f"  🪙 {symbol} | {signal}\n     Entry: {entry} → Now: {current}\n     PnL: +{pnl_pct:.2f}%\n"
                    else:
                        msg += "\n✅ <b>PROFIT</b>\n  (tidak ada)\n"

                    if losing:
                        msg += "\n⚠️ <b>RUGI (unrealized)</b>\n"
                        for symbol, signal, entry, current, pnl_pct, sl, tp1 in losing:
                            msg += f"  🪙 {symbol} | {signal}\n     Entry: {entry} → Now: {current}\n     PnL: {pnl_pct:.2f}%\n"
                    else:
                        msg += "\n⚠️ <b>RUGI</b>\n  (tidak ada)\n"

                    msg += "\n" + "═"*25
                    msg += f"\n📌 {len(profitable)} profit, {len(losing)} rugi dari {len(rows)} posisi"
                    msg += "\n🤖 AI Signal Bot"
                    _send(msg)
            except Exception as e:
                _send(f"❌ Error live_positions: {e}")

        elif text == "/pair_status":
            try:
                import sqlite3
                from datetime import datetime, timedelta
                conn = sqlite3.connect('virtual_trading.db')
                since = (datetime.now() - timedelta(days=30)).isoformat()
                rows = conn.execute("""
                    SELECT symbol, COUNT(*), SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END),
                           ROUND(AVG(pnl_pct), 2), ROUND(SUM(pnl_usdt), 2)
                    FROM virtual_trades
                    WHERE closed=1 AND result IN ('WIN','LOSS') AND timestamp >= ?
                    GROUP BY symbol
                    ORDER BY AVG(pnl_pct) DESC
                """, (since,)).fetchall()
                conn.close()
                if not rows:
                    _send("📭 Belum ada data trade sama sekali (30 hari terakhir).")
                else:
                    profitable = [r for r in rows if r[3] > 0]
                    losing     = [r for r in rows if r[3] <= 0]

                    msg = "📊 <b>STATUS PAIR (30 hari)</b>\n" + "═"*25 + "\n"

                    if profitable:
                        msg += "\n✅ <b>PROFIT</b>\n"
                        for symbol, total, wins, avg_pnl, total_usd in profitable:
                            wr = round(100 * wins / total, 1) if total > 0 else 0
                            msg += f"  {symbol}: +{avg_pnl}% avg | {total} trade | WR {wr}% | ${total_usd}\n"
                    else:
                        msg += "\n✅ <b>PROFIT</b>\n  (belum ada)\n"

                    if losing:
                        msg += "\n⚠️ <b>RUGI</b>\n"
                        for symbol, total, wins, avg_pnl, total_usd in losing:
                            wr = round(100 * wins / total, 1) if total > 0 else 0
                            msg += f"  {symbol}: {avg_pnl}% avg | {total} trade | WR {wr}% | ${total_usd}\n"
                    else:
                        msg += "\n⚠️ <b>RUGI</b>\n  (belum ada)\n"

                    msg += "\n" + "═"*25
                    msg += f"\n📌 {len(profitable)} pair profit, {len(losing)} pair rugi"
                    msg += "\n⚠️ Sample kecil (&lt;5 trade) belum tentu representatif"
                    msg += "\n🤖 AI Signal Bot"
                    _send(msg)
            except Exception as e:
                _send(f"❌ Error pair_status: {e}")

        elif text == "/positions":
            try:
                from risk_manager import get_risk_status
                status = get_risk_status()
                open_pos = status.get("open_positions", 0)
                import json
                with open('risk_state.json', 'r') as f:
                    rstate = json.load(f)
                pos_dict = rstate.get("open_positions", {})
                if not pos_dict:
                    _send("📭 Tidak ada posisi terbuka saat ini.")
                else:
                    msg = f"📋 <b>POSISI TERBUKA ({len(pos_dict)})</b>\n" + "═"*25 + "\n"
                    for key, risk_pct in pos_dict.items():
                        parts = key.split("_")
                        symbol = parts[0] if len(parts) > 0 else key
                        tf = parts[1] if len(parts) > 1 else "?"
                        sig = parts[2] if len(parts) > 2 else "?"
                        msg += f"\n🪙 <b>{symbol}</b> | {tf} | {sig}\n   Risk: {risk_pct}%\n"
                    msg += "\n" + "═"*25 + "\n🤖 AI Signal Bot"
                    _send(msg)
            except Exception as e:
                _send(f"❌ Error positions: {e}")

        elif text == "/winrate_pair":
            try:
                import sqlite3
                from datetime import datetime, timedelta
                conn = sqlite3.connect('virtual_trading.db')
                since = (datetime.now() - timedelta(days=30)).isoformat()
                rows = conn.execute("""
                    SELECT symbol, COUNT(*), SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END),
                           ROUND(AVG(pnl_pct), 2), MIN(pnl_pct)
                    FROM virtual_trades
                    WHERE closed=1 AND result IN ('WIN','LOSS') AND timestamp >= ?
                    GROUP BY symbol
                    ORDER BY AVG(pnl_pct) ASC
                """, (since,)).fetchall()
                conn.close()
                if not rows:
                    _send("📭 Belum ada data trade sama sekali (30 hari terakhir).")
                else:
                    msg = "📊 <b>WIN RATE PER PAIR (30 hari)</b>\n" + "═"*25 + "\n"
                    for symbol, total, wins, avg_pnl, worst_pnl in rows:
                        wr = round(100 * wins / total, 1) if total > 0 else 0
                        emoji = "✅" if avg_pnl > 0 else "⚠️"
                        note = " (sample kecil)" if total < 5 else ""
                        msg += f"\n{emoji} <b>{symbol}</b>: {wr}% WR | {total} trade{note}\n   Avg PnL: {avg_pnl}% | Worst: {worst_pnl}%\n"
                    msg += "\n" + "═"*25 + "\n🤖 AI Signal Bot"
                    _send(msg)
            except Exception as e:
                _send(f"❌ Error winrate_pair: {e}")

        elif text == "/statscompare":
            try:
                import sqlite3
                conn = sqlite3.connect('virtual_trading.db')
                rows = conn.execute("""
                    SELECT
                        CASE WHEN signal LIKE '%MANUAL%' THEN 'MANUAL' ELSE 'AUTO' END AS trade_type,
                        COUNT(*),
                        SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END),
                        ROUND(SUM(pnl_usdt), 2),
                        ROUND(AVG(pnl_usdt), 4)
                    FROM virtual_trades
                    WHERE closed_at IS NOT NULL
                    GROUP BY trade_type
                """).fetchall()
                conn.close()

                if not rows:
                    _send("📭 Belum ada trade closed untuk dibandingkan.")
                else:
                    stats = {r[0]: r for r in rows}
                    msg = "⚖️ <b>AUTO vs MANUAL</b>\n" + "═"*25 + "\n"

                    for label, icon in [("AUTO", "🤖"), ("MANUAL", "✋")]:
                        if label in stats:
                            _, total, wins, pnl, avg_pnl = stats[label]
                            wr = round(100 * wins / total, 1) if total else 0
                            pnl_icon = "🟢" if pnl >= 0 else "🔴"
                            msg += f"\n{icon} <b>{label}</b>\n"
                            msg += f"   Trades   : {total}\n"
                            msg += f"   Win Rate : {wr}%\n"
                            msg += f"   PnL      : {pnl_icon} ${pnl:,.2f}\n"
                            msg += f"   Avg/trade: ${avg_pnl:,.4f}\n"
                        else:
                            msg += f"\n{icon} <b>{label}</b>\n   (belum ada data)\n"

                    msg += "\n" + "═"*25 + "\n🤖 AI Signal Bot"
                    _send(msg)
            except Exception as e:
                _send(f"❌ Error statscompare: {e}")

        elif text == "/setup_stats" or text == "/sr_stats":
            try:
                import sqlite3
                conn = sqlite3.connect('virtual_trading.db')
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*), 
                           SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END),
                           ROUND(SUM(pnl_usdt), 2)
                    FROM virtual_trades
                    WHERE closed = 1 AND timestamp >= '2026-07-09'
                    AND signal LIKE '%SR%'
                """)
                row = cur.fetchone()
                conn.close()
                total, wins, total_pnl = row
                total = total or 0
                wins = wins or 0
                total_pnl = total_pnl or 0
                wr = round(100 * wins / total, 1) if total > 0 else 0
                emoji = "✅" if total_pnl >= 0 else "⚠️"
                msg = f"{emoji} <b>PERFORMA SETUP/REVERSAL</b>\n"
                msg += "═"*25 + "\n"
                msg += f"📅 Sejak    : 09 Jul 2026\n"
                msg += f"🔄 Total    : {total} trade\n"
                msg += f"✅ Menang   : {wins}\n"
                msg += f"📈 Win Rate : {wr}%\n"
                msg += f"💰 Total PnL: ${total_pnl}\n"
                msg += "═"*25 + "\n🤖 AI Signal Bot"
                _send(msg)
            except Exception as e:
                _send(f"❌ Error setup_stats: {e}")

        elif text.startswith("/execute"):
            parts = text_raw.split()
            if len(parts) < 3:
                _send("⚠️ Format: <code>/execute BTCUSDT BUY</code> atau <code>/execute BTCUSDT SELL</code>")
            else:
                symbol = parts[1].upper()
                if not symbol.endswith("USDT"):
                    symbol += "USDT"
                direction = parts[2].upper()
                if direction not in ("BUY", "SELL"):
                    _send("⚠️ Arah harus BUY atau SELL")
                else:
                    try:
                        from scanner import analyze_pair_manual
                        from virtual_trader import add_virtual_trade
                        r = analyze_pair_manual(symbol)
                        if r.get("error"):
                            _send(f"❌ {symbol}: {r['error']}")
                        else:
                            entry = r["price"]
                            atr = r["atr"]
                            if direction == "BUY":
                                sl  = entry - 1.5 * atr
                                tp1 = entry + 2.0 * atr
                                tp2 = entry + 3.5 * atr
                                tp3 = entry + 5.0 * atr
                            else:
                                sl  = entry + 1.5 * atr
                                tp1 = entry - 2.0 * atr
                                tp2 = entry - 3.5 * atr
                                tp3 = entry - 5.0 * atr

                            # [PATCH 2026-07-10] Risk Gate untuk /execute manual
                            liq_score = r.get("liq_score", 5)
                            slippage  = r.get("slippage_est", 0)
                            sr_pos    = r.get("sr_pos", 0.5)
                            sr_warning = ""
                            if direction == "BUY" and sr_pos > 0.85:
                                sr_warning = f"\n⚠️ SR Warning: entry dekat resistance (SR pos={sr_pos:.2f})"
                            elif direction == "SELL" and sr_pos < 0.15:
                                sr_warning = f"\n⚠️ SR Warning: entry dekat support (SR pos={sr_pos:.2f})"

                            if liq_score < 5 or slippage > 3.0:
                                _send(
                                    f"🚫 <b>ENTRY DIBATALKAN — LIQUIDITY BURUK</b>\n{'═'*25}\n"
                                    f"🪙 {symbol} | {direction}\n"
                                    f"💧 Liq Score : {liq_score}/10\n"
                                    f"📉 Slippage  : {slippage}%\n"
                                    f"{'═'*25}\n"
                                    f"Entry ditolak untuk lindungi kamu dari slippage besar."
                                )
                            else:
                                from risk_manager import check_risk_approval
                                risk_check = check_risk_approval(
                                    symbol=symbol, timeframe="1h",
                                    signal=f"{direction} (MANUAL)",
                                    entry=entry, sl=sl,
                                )
                                if not risk_check.get("approved"):
                                    reasons = "\n".join(risk_check.get("reasons", []))
                                    _send(
                                        f"🚫 <b>ENTRY DIBATALKAN — RISK BLOCK</b>\n{'═'*25}\n"
                                        f"🪙 {symbol} | {direction}\n"
                                        f"{reasons}\n"
                                        f"{'═'*25}\n"
                                        f"Balance: {risk_check.get('balance')} | DD: {risk_check.get('drawdown_pct')}% | Streak Loss: {risk_check.get('streak_loss')}"
                                    )
                                else:
                                    trade_signal = {
                                        "symbol": symbol,
                                        "timeframe": "1h",
                                        "signal": f"{direction} (MANUAL)",
                                        "entry": entry,
                                        "sl": sl,
                                        "tp1": tp1,
                                        "tp2": tp2,
                                        "tp3": tp3,
                                        "atr": atr,
                                        "regime": r["market_regime"],
                                        "score": r["confidence"],
                                        "score_final": r["confidence"],
                                    }
                                    add_virtual_trade(trade_signal)
                                    from exit_monitor import add_trade as exit_add_trade
                                    exit_add_trade(trade_signal)
                                    _send(
                                        f"✅ <b>MANUAL ENTRY DIBUKA</b>\n{'═'*25}\n"
                                        f"🪙 {symbol} | {direction}\n"
                                        f"💰 Entry : {entry}\n"
                                        f"🛑 SL    : {sl:.6f}\n"
                                        f"🎯 TP1   : {tp1:.6f}\n"
                                        f"🎯 TP2   : {tp2:.6f}\n"
                                        f"🎯 TP3   : {tp3:.6f}\n"
                                        f"📊 Regime: {r['market_regime']}\n"
                                        f"💧 Liq   : {liq_score}/10 | Slippage: {slippage}%"
                                        f"{sr_warning}\n"
                                        f"{'═'*25}\n"
                                        f"⚠️ Ini VIRTUAL trade (simulasi), bukan order real\n"
                                        f"🤖 AI Signal Bot"
                                    )
                    except Exception as e:
                        _send(f"❌ Error execute {symbol}: {e}")

        elif text.startswith("/analyze") or text.startswith("/cek"):
            parts = text_raw.split()
            if len(parts) < 2:
                _send("⚠️ Format: <code>/analyze BTCUSDT</code>")
            else:
                symbol = parts[1].upper()
                if not symbol.endswith("USDT"):
                    symbol += "USDT"
                _send(f"🔍 Menganalisa {symbol}...")
                try:
                    from scanner import analyze_pair_manual
                    r = analyze_pair_manual(symbol)
                    if r.get("error"):
                        _send(f"❌ {symbol}: {r['error']}")
                    else:
                        signal_emoji = "✅" if r["valid_signal"] else "⚪"
                        out = f"{signal_emoji} <b>ANALISA {symbol}</b>\n" + "═"*25 + "\n"
                        out += f"💲 Price      : {r['price']}\n"
                        out += f"📶 Signal     : <b>{r['signal']}</b>\n"
                        out += f"🎯 Confidence : {r['confidence']:.1f}\n"
                        out += f"📊 Regime     : {r['market_regime']}\n"
                        out += f"📈 ADX        : {r['adx']:.1f}\n"
                        out += f"📉 RSI        : {r['rsi']:.1f}\n"
                        out += f"〰️ MACD Hist  : {r['macd_hist']:.4f}\n"
                        out += f"⬆️ Trend Up   : {r['trend_up']} | ⬇️ Down: {r['trend_down']}\n"
                        out += f"🟢 Buy Score  : {r['buy_combined']:.1f}\n"
                        out += f"🔴 Sell Score : {r['sell_combined']:.1f}\n"
                        out += f"📦 RVol       : {r['rvol']:.2f}\n"
                        if r["valid_signal"]:
                            out += "─"*25 + "\n"
                            out += f"🛑 SL  : {r['sl']:.4f}\n"
                            out += f"🎯 TP1 : {r['tp1']:.4f}\n"
                            out += f"🎯 TP2 : {r['tp2']:.4f}\n"
                            out += f"⚖️ R:R : {r['rr_ratio']:.2f}\n"
                        if r["blacklisted"]:
                            out += "\n⚠️ Pair ini sedang di-blacklist"
                        if r["cooldown"]:
                            out += "\n⏳ Pair ini sedang cooldown"
                        out += "\n" + "═"*25 + "\n🤖 AI Signal Bot"
                        _send_with_url_button(out, _chart_buttons(symbol))
                except Exception as e:
                    _send(f"❌ Error analyze {symbol}: {e}")

        elif text == "/health":
            try:
                import sys
                sys.path.insert(0, '/home/userland/ai-scanner')
                from bot_auditor import audit_win_rate, audit_active_trades, audit_consecutive_loss, audit_log_errors, get_summary_today
                issues = audit_win_rate() + audit_active_trades() + audit_consecutive_loss() + audit_log_errors()
                status = "✅ SEHAT" if not issues else "⚠️ " + str(len(issues)) + " MASALAH"
                msg = "<b>🔍 CEK KESEHATAN BOT</b>\n"
                msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
                msg += "Status: " + status + "\n\n"
                if issues:
                    msg += "<b>Masalah:</b>\n"
                    for i in issues:
                        msg += "- " + i + "\n"
                else:
                    msg += "✅ Semua sistem normal\n"
                msg += "\n🤖 AI Signal Bot"
                _send(msg)
            except Exception as e:
                _send("❌ Health check error: " + str(e))

        elif text == "/virtual":
            try:
                import sys
                sys.path.insert(0, '/home/userland/ai-scanner')
                from virtual_trader import get_summary
                s = get_summary()
                emoji = "📈" if s["profit"] >= 0 else "📉"
                msg = emoji + " <b>Virtual Trading</b>\n"
                msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
                msg += "💰 Balance  : $" + str(round(s["balance"],2)) + "\n"
                msg += "📊 Profit   : $" + str(round(s["profit"],2)) + " (" + str(s["profit_pct"]) + "%)\n"
                msg += "🏔️  Peak     : $" + str(round(s["peak"],2)) + "\n"
                msg += "📉 Drawdown : " + str(s["drawdown"]) + "%\n"
                msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
                msg += "🎯 Total : " + str(s["total"]) + " trade\n"
                msg += "✅ Menang: " + str(s["wins"]) + " | ❌ Kalah: " + str(s["losses"]) + "\n"
                msg += "📈 Win Rate: " + str(s["wr"]) + "%\n"
                msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
                msg += "🤖 AI Signal Bot"
                _send(msg)
            except Exception as e:
                _send("❌ Virtual error: " + str(e))

        elif text == "/force_reset_heat":
            try:
                from risk_manager import reset_positions, get_risk_status
                reset_positions()
                status = get_risk_status()
                _send(
                    f"⚠️ <b>PORTFOLIO HEAT DI-RESET PAKSA</b>\n{'═'*25}\n"
                    f"Heat sekarang: {status.get('portfolio_heat', 0):.1f}%\n"
                    f"Balance: ${status.get('balance', 0):.2f}\n\n"
                    f"⚠️ Posisi lama TETAP terbuka di market — cuma catatan\n"
                    f"risk internal yang direset. Entry baru sekarang bisa\n"
                    f"masuk meski total eksposur sebenarnya di atas batas.\n"
                    f"{'═'*25}\n🤖 AI Signal Bot"
                )
            except Exception as e:
                _send(f"❌ Error force_reset_heat: {e}")

        elif text == "/reset_streak":
            try:
                import sys
                sys.path.insert(0, '/home/userland/ai-scanner')
                from risk_manager import reset_streak_loss
                old_streak = reset_streak_loss()
                _send(
                    f"✅ <b>STREAK LOSS DIRESET</b>\n{'═'*25}\n"
                    f"Sebelum : {old_streak} kali kalah beruntun\n"
                    f"Sesudah : 0\n"
                    f"Trading : ✅ Aktif kembali\n"
                    f"{'═'*25}\n🤖 AI Signal Bot"
                )
            except Exception as e:
                logger.error(f"[RESET_STREAK] Error tidak terduga: {e}")
                _send(f"❌ Error reset_streak: {e}")

        elif text == "/resume":
            try:
                import sys
                sys.path.insert(0, '/home/userland/ai-scanner')
                from risk_manager import resume_trading, get_risk_status
                resume_trading(manual=True)
                status = get_risk_status()
                msg = (
                    "<b>✅ TRADING DILANJUTKAN</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Balance: ${status.get('balance', 0):.2f}\n"
                    f"Streak Loss: {status.get('consecutive_loss', 0)}\n"
                    f"Drawdown: {status.get('drawdown_pct', 0):.1f}%\n\n"
                    "Bot akan mulai entry lagi di scan berikutnya.\n"
                    "🤖 AI Signal Bot"
                )
                _send(msg)
            except Exception as e:
                _send("❌ Resume error: " + str(e))

        elif text == "/help":
            _send(
                f"🤖 <b>COMMAND TERSEDIA</b>\n{'═'*25}\n"
                "/status  — Status bot & risk\n"
                "/winrate — Win rate aktual\n"
                "/sinyal  — 3 sinyal terakhir\n"
                "/scan    — Trigger scan manual\n"
                "/health  — Cek kesehatan bot\
"
                         "/virtual — Virtual balance\
"
                         "/resume  — Resume trading setelah halt\n"
                        "/help    — Daftar command"
            )
