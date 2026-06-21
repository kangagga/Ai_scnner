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
LAST_SIGNALS = {}
COOLDOWN_MINUTES = 30

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
        return True

    last = LAST_SIGNALS[key]
    # Jika sinyal berubah (misal dari BUY jadi SELL) -> boleh kirim
    if last["signal"] != signal:
        LAST_SIGNALS[key] = {"signal": signal, "score": score, "time": now}
        return True

    # Jika sinyal sama, cek cooldown
    if now - last["time"] > timedelta(minutes=COOLDOWN_MINUTES):
        LAST_SIGNALS[key] = {"signal": signal, "score": score, "time": now}
        return True

    # Masih dalam cooldown
    logger.debug(f"Cooldown {symbol} ({signal}) - skip kirim")
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

def format_signal(s: dict) -> str:
    """Format sinyal dengan aman (semua key pakai .get)"""
    emoji = SIGNAL_EMOJI.get(s.get("signal", "NEUTRAL"), "⚪")
    tf = TF_LABEL.get(s.get("timeframe", "1h"), s.get("timeframe", "1h"))
    now = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m %H:%M")
    score = s.get("score", 0)
    conf  = s.get("confidence", 0)
    wr    = s.get("win_rate", 0)

    # Alert level berdasarkan confidence + win rate
    if conf >= 70 and wr >= 60:
        alert_level = "🔴 HIGH CONFIDENCE"
    elif conf >= 60 and wr >= 50:
        alert_level = "🟡 MEDIUM CONFIDENCE"
    else:
        alert_level = "🟢 WATCHLIST"

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
        f"🔵 Stoch   : {s.get('stoch_k', 0)} ({s.get('stoch_zone', 'N/A')})\n\n"
        f"🏔️  Resist : <code>{s.get('resistance', 'N/A')}</code>\n"
        f"🛡️  Support: <code>{s.get('support', 'N/A')}</code>\n"
        f"📌 Pivot   : <code>{s.get('pivot', 'N/A')}</code>\n"
        f"{'━'*30}\n"
        f"🤖 <i>AI Signal Bot • Threshold {s.get('dynamic_threshold', SIGNAL_THRESHOLD)}</i>"
    )


def send_signal(signal: dict) -> bool:
    """Kirim 1 sinyal (tanpa cooldown)"""
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
        text = msg.get("text", "").strip().lower()
        chat_id = msg.get("chat", {}).get("id")

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
                         "/help    — Daftar command"
            )
