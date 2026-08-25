#!/bin/bash
# ============================================================
# watchdog.sh - Auto-restart ai-scanner bot kalau crash/mati
# ============================================================
# Cara pakai:
#   Jalankan sekali: setsid nohup bash watchdog.sh > watchdog_runner.log 2>&1 &
#   Cek jalan: ps aux | grep watchdog.sh
#   Stop: pkill -f watchdog.sh
# ============================================================

cd /home/userland/ai-scanner || exit 1

WATCHDOG_LOG="watchdog.log"
CHECK_INTERVAL=30   # detik antar pengecekan
WD_LOCK="watchdog.lock"

# Cegah watchdog dobel jalan (pola sama seperti bot.lock di main.py)
if [ -f "$WD_LOCK" ]; then
    OLD_PID=$(cat "$WD_LOCK")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "❌ Watchdog sudah jalan dengan PID $OLD_PID. Keluar."
        exit 1
    fi
fi
echo $$ > "$WD_LOCK"
trap 'rm -f "$WD_LOCK"' EXIT

echo "$(date '+%Y-%m-%d %H:%M:%S') - Watchdog dimulai (PID $$)" >> "$WATCHDOG_LOG"

while true; do
    if ! pgrep -f "python3 main.py" > /dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - main.py TIDAK JALAN, restart otomatis..." >> "$WATCHDOG_LOG"

        setsid nohup python3 main.py > signal_bot.log 2>&1 &

        sleep 5

        # Kirim notifikasi Telegram soal restart (best-effort, tidak boleh
        # menghentikan watchdog kalau gagal kirim)
        python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from telegram_sender import _send
    _send('⚠️ <b>BOT AUTO-RESTART</b>\n\nBot terdeteksi berhenti dan sudah dijalankan ulang otomatis oleh watchdog.\nSilakan cek log (watchdog.log, signal_bot.log) jika ini terjadi berulang kali.')
    print('Notifikasi restart terkirim.')
except Exception as e:
    print(f'Gagal kirim notifikasi restart: {e}')
" >> "$WATCHDOG_LOG" 2>&1
    fi
    sleep "$CHECK_INTERVAL"
done
