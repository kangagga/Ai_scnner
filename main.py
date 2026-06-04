#!/usr/bin/env python3
# ============================================================
#  main.py  –  AI Crypto Signal Bot  (+ Live Dashboard API)
# ============================================================

import logging
import time
import schedule
from datetime import datetime, timezone

from config          import SCAN_INTERVAL, SIGNAL_THRESHOLD, MIN_SCORE, MAX_SIGNALS_PER_DAY, \
                            DAILY_REPORT_HOUR, DAILY_REPORT_MINUTE
from scanner         import scan_all, scan_all_fast, get_top_signals, get_dynamic_threshold
from ai_analyst      import analyse_market_sentiment, filter_signals_ai
from market_context  import get_market_context
from telegram_sender import send_top_signals, send_daily_report, send_test_message, send_alert, handle_commands, \
                            LAST_SIGNALS, COOLDOWN_MINUTES
from email_reporter  import send_email_report

# ── Import API server ──────────────────────────────────────
from database import save_signal
from exit_monitor import add_trade, start_exit_monitor
from api_server import start_api, update_signals, add_log, \
                        update_cooldowns, set_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("signal_bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("main")

_last_signals: list = []
_daily_signal_count: int = 0
_daily_reset_date = datetime.now().date()


def _build_cooldown_info() -> dict:
    """
    Ambil sisa cooldown per simbol dari LAST_SIGNALS (telegram_sender).
    Return: {symbol: sisa_menit (int)}
    """
    from datetime import datetime, timedelta
    now  = datetime.now(timezone.utc)
    result = {}
    for sym, data in LAST_SIGNALS.items():
        elapsed  = (now - data["time"]).total_seconds() / 60.0
        remaining = round(COOLDOWN_MINUTES - elapsed)
        if remaining > 0:
            result[sym] = remaining
    return result


def job_scan():
    global _last_signals
    now_str = datetime.now().strftime("%H:%M:%S")
    logger.info(f"🔍 Scan dimulai — {now_str}")
    add_log("🔍", f"Scan dimulai — {now_str}")

    try:
        all_sig = scan_all_fast(min_score=MIN_SCORE)
        dyn_threshold = get_dynamic_threshold(get_market_context())
        top_sig = get_top_signals(all_sig, threshold=dyn_threshold)

        _last_signals = top_sig

        # ── Update dashboard ───────────────────────────────
        update_signals(top_sig)
        update_cooldowns(_build_cooldown_info())

        # Reset counter tiap hari baru
        global _daily_signal_count, _daily_reset_date
        today = datetime.now().date()
        if _daily_reset_date != today:
            _daily_signal_count = 0
            _daily_reset_date = today

        if top_sig:
            top_sig = filter_signals_ai(top_sig, get_market_context())
        if top_sig:
            # Cek max sinyal per hari
            sisa = MAX_SIGNALS_PER_DAY - _daily_signal_count
            if sisa <= 0:
                logger.warning(f"⚠️ Max sinyal harian ({MAX_SIGNALS_PER_DAY}) tercapai, skip.")
                top_sig = []
            else:
                top_sig = top_sig[:sisa]
                _daily_signal_count += len(top_sig)
                logger.info(f"📊 Sinyal hari ini: {_daily_signal_count}/{MAX_SIGNALS_PER_DAY}")

        if top_sig:
            logger.info(f"📡 Kirim {len(top_sig)} sinyal ke Telegram")
            add_log("📡", f"{len(top_sig)} sinyal dikirim ke Telegram")
            send_top_signals(top_sig)
            for s in top_sig:
                save_signal(s)
                add_trade(s)
        else:
            logger.info(f"Tidak ada sinyal ≥{SIGNAL_THRESHOLD}, skip Telegram.")
            add_log("📭", f"Tidak ada sinyal ≥{SIGNAL_THRESHOLD}")

    except Exception as e:
        logger.error(f"Scan error: {e}", exc_info=True)
        add_log("❌", f"Scan error: {e}")
        try:
            send_alert(f"⚠️ <b>BOT ERROR</b>\n\nScan error:\n<code>{str(e)[:200]}</code>\n\n🤖 AI Signal Bot")
        except Exception:
            pass


def job_daily_report():
    global _last_signals
    logger.info("📋 Membuat laporan harian…")
    add_log("📋", "Membuat laporan harian…")

    try:
        if not _last_signals:
            all_sig       = scan_all_fast(min_score=MIN_SCORE)
            _last_signals = get_top_signals(all_sig, threshold=dyn_threshold)
            update_signals(_last_signals)

        ai_text = analyse_market_sentiment(_last_signals) if _last_signals else ""
        send_daily_report(_last_signals, ai_text)
        send_email_report(_last_signals, ai_text)
        logger.info("✅ Laporan harian selesai dikirim")
        add_log("✅", "Laporan harian selesai dikirim")

    except Exception as e:
        logger.error(f"Daily report error: {e}", exc_info=True)
        add_log("❌", f"Daily report error: {e}")
        try:
            send_alert(f"⚠️ <b>BOT ERROR</b>\n\nDaily report error:\n<code>{str(e)[:200]}</code>\n\n🤖 AI Signal Bot")
        except Exception:
            pass


def main():
    logger.info("🤖 AI Crypto Signal Bot starting…")
    logger.info(f"   Interval scan   : {SCAN_INTERVAL}s")
    logger.info(f"   Min score       : {MIN_SCORE}")
    logger.info(f"   Signal threshold: {SIGNAL_THRESHOLD}")

    daily_time = f"{DAILY_REPORT_HOUR:02d}:{DAILY_REPORT_MINUTE:02d}"
    logger.info(f"   Daily report    : {daily_time} WIB")

    # ── Simpan config ke dashboard ─────────────────────────
    set_config({
        "scan_interval" : SCAN_INTERVAL,
        "min_score"     : MIN_SCORE,
        "threshold"     : SIGNAL_THRESHOLD,
        "cooldown_min"  : COOLDOWN_MINUTES,
        "daily_report"  : f"{daily_time} WIB",
        "timeframes"    : ["1h", "4h", "1d"],
    })

    # ── Start Flask API (background thread) ────────────────
    start_api(host="0.0.0.0", port=5000)
    start_exit_monitor(lambda msg: send_alert(msg))
    logger.info("🌐 Buka dashboard: http://localhost:5000  (atau http://<IP>:5000)")
    add_log("🌐", "Dashboard API aktif di port 5000")

    # ── Kirim test message & scan pertama ──────────────────
    send_test_message()
    add_log("✅", "Bot aktif, Telegram terhubung")

    # ── Schedule ───────────────────────────────────────────
    schedule.every(SCAN_INTERVAL).seconds.do(job_scan)
    schedule.every().day.at(daily_time).do(job_daily_report)

    logger.info("🔄 Bot berjalan. Ctrl+C untuk stop.")
    try:
        # Jalankan command handler di thread terpisah
        import threading
        import telegram_sender as _ts
        import requests as _req
        # Reset ke update terbaru supaya tidak proses pesan lama
        try:
            _r = _req.get(f"https://api.telegram.org/bot{__import__('config').BOT_TOKEN}/getUpdates", params={"limit": 1, "offset": -1})
            _res = _r.json().get("result", [])
            if _res:
                _ts._last_update_id = _res[-1]["update_id"]
        except Exception:
            pass

        def _cmd_loop():
            while True:
                try:
                    handle_commands(scan_fn=job_scan)
                except Exception:
                    pass
                time.sleep(5)
        threading.Thread(target=_cmd_loop, daemon=True).start()

        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Bot dihentikan.")


if __name__ == "__main__":
    main()
