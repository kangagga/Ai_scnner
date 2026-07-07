#!/bin/bash
# Skrip pemindai sinyal Entry (Versi Pro: Support/Resist + ATR)

SYMBOL="BTCUSDT"
URL="https://data-api.binance.vision/api/v3/klines?symbol=${SYMBOL}&interval=1h&limit=200"

# 1. Ambil data
KLINES=$(curl -s "$URL")
CLOSES=$(echo "$KLINES" | jq -r '.[][4]')
CURRENT_CLOSE=$(echo "$CLOSES" | tail -n 1)

# 2. Hitung Indikator
EMA200=$(echo "$CLOSES" | awk 'BEGIN {a=2/201} {if(NR==1) e=$1; else e=($1*a)+(e*(1-a))} END {printf "%.2f", e}')
ATR=$(echo "$KLINES" | jq -r '.[-14:][] | (.[2]|tonumber)-(.[3]|tonumber)' | awk '{s+=$1} END {printf "%.2f", s/NR}')

# 3. Logika Tren
IS_UPTREND=$(echo "$CURRENT_CLOSE > $EMA200" | bc -l)

if [ "$IS_UPTREND" -eq 1 ]; then
    echo "✅ Peluang LONG terdeteksi di $SYMBOL!"
    
    # --- FILTER RESISTANCE (Mencegah beli di pucuk) ---
    RESIST=$(echo "$KLINES" | jq -r '.[-20:][] | .[2]|tonumber' | sort -n | tail -n 1)
    JARAK_KE_RESIST=$(echo "scale=4; ($RESIST - $CURRENT_CLOSE) / $CURRENT_CLOSE" | bc -l)
    IS_TOO_CLOSE=$(echo "$JARAK_KE_RESIST > -0.005 && $JARAK_KE_RESIST < 0.005" | bc -l)
    
    if [ "$IS_TOO_CLOSE" -eq 1 ]; then
        echo "🚫 Sinyal DIBATALKAN: Harga $CURRENT_CLOSE terlalu dekat dengan Resistance $RESIST."
    else
        # --- LOGIKA STOP LOSS (Bersembunyi di balik Support) ---
        SUPPORT=$(echo "$KLINES" | jq -r '.[-20:][] | .[3]|tonumber' | sort -n | head -n 1)
        SL=$(echo "$SUPPORT - (0.5 * $ATR)" | bc -l)
        
        # Hitung TP dengan rasio Risk:Reward 1:3
        JARAK_SL=$(echo "$CURRENT_CLOSE - $SL" | bc -l)
        TP=$(echo "$CURRENT_CLOSE + (3.0 * $JARAK_SL)" | bc -l)
        
        echo "  🏰 Resistance terdekat: $RESIST"
        echo "  🛡️ Support terdeteksi di: $SUPPORT"
        echo "  🛑 SL diletakkan aman di bawah Support: $SL"
        echo "  🎯 TP dipasang pada: $TP"
        
        # Eksekusi ke Database
        sqlite3 virtual_trading.db "INSERT INTO virtual_trades (timestamp, symbol, side, entry_price, sl_price, tp_price, closed) VALUES (datetime('now'), '$SYMBOL', 'LONG', $CURRENT_CLOSE, $SL, $TP, 0);"
        
        echo "📝 Posisi LONG baru saja dibuka di database."
    fi
else
    echo "❌ Belum ada sinyal valid untuk $SYMBOL."
fi
