#!/bin/bash
cd /home/userland/ai-scanner

PIDFILE="/tmp/ai_scanner.pid"

if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot sudah jalan (PID $OLD_PID). Exit."
        exit 1
    else
        rm -f "$PIDFILE"
    fi
fi

echo $$ > "$PIDFILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot started (PID $$)"

cleanup() {
    rm -f "$PIDFILE"
    exit 0
}
trap cleanup SIGTERM SIGINT

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting bot..."
    /home/userland/ai-scanner/venv/bin/python3 main.py
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot crashed/stopped. Restart in 10s..."
    sleep 10
done
