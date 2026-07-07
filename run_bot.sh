#!/bin/bash
while true; do
    echo "========================================"
    echo "[$(date)] MEMULAI SIKLUS BOT"
    echo "========================================"
    
    echo "1. Menjalankan AI Entry (Mencari Peluang)..."
    ./ai-entry.sh >> entry_monitor.log 2>&1
    
    echo "2. Menjalankan AI Exit (Memantau Posisi)..."
    ./ai-exit.sh >> exit_monitor.log 2>&1
    
    echo "Siklus selesai. Standby 5 menit..."
    sleep 300
done
