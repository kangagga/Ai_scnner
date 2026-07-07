#!/bin/bash

echo "========================================"
echo "🤖 AI Scanner - Exit & Trailing Monitor"
echo "========================================"

# 1. Ambil harga BTC saat ini (pakai API bebas blokir)
URL_TICKER="https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
CURRENT_PRICE=$(curl -s "$URL_TICKER" | jq -r '.price')

if [ -z "$CURRENT_PRICE" ] || [ "$CURRENT_PRICE" == "null" ]; then
    echo "❌ ERROR: Gagal mengambil harga terkini dari API."
    exit 1
fi

echo "Harga BTC saat ini: $CURRENT_PRICE"
echo "----------------------------------------"

# 2. Tarik data posisi yang masih terbuka (closed=0) dari database
OPEN_TRADES=$(sqlite3 virtual_trading.db "SELECT id, side, entry_price, sl_price, tp_price FROM virtual_trades WHERE closed=0;")

if [ -z "$OPEN_TRADES" ]; then
    echo "Tidak ada posisi yang sedang terbuka. Standby..."
    exit 0
fi

# 3. Proses setiap posisi yang terbuka
for TRADE in $OPEN_TRADES; do
    # Memisahkan data dari SQLite berdasarkan garis '|'
    IFS='|' read -r ID SIDE ENTRY SL TP <<< "$TRADE"
    
    echo "Memeriksa Trade ID: $ID ($SIDE) | Entry: $ENTRY | SL: $SL | TP: $TP"
    
    if [ "$SIDE" == "LONG" ]; then
        
        # --- BAGIAN A: CEK TRAILING STOP ---
        PROFIT_PCT=$(echo "scale=2; (($CURRENT_PRICE - $ENTRY) / $ENTRY) * 100" | bc -l)
        IS_ACTIVE=$(echo "$PROFIT_PCT > 1.0" | bc -l) # Trailing aktif jika profit > 1%
        
        if [ "$IS_ACTIVE" -eq 1 ]; then
            # Setel jarak Trailing Stop 1.5% dari harga tertinggi saat ini
            NEW_SL=$(echo "scale=2; $CURRENT_PRICE - ($CURRENT_PRICE * (1.5 / 100))" | bc -l)
            SL_NAIK=$(echo "$NEW_SL > $SL" | bc -l)
            
            if [ "$SL_NAIK" -eq 1 ]; then
                echo "  🔥 Trailing Stop! SL ditarik NAIK menjadi $NEW_SL"
                # Update SL baru ke database
                sqlite3 virtual_trading.db "UPDATE virtual_trades SET sl_price = $NEW_SL WHERE id = $ID;"
                SL=$NEW_SL # Perbarui variabel SL untuk pengecekan di bawah
            fi
        fi

        # --- BAGIAN B: CEK KONDISI EXIT (TP ATAU SL) ---
        HIT_TP=$(echo "$CURRENT_PRICE >= $TP" | bc -l)
        HIT_SL=$(echo "$CURRENT_PRICE <= $SL" | bc -l)
        
        if [ "$HIT_TP" -eq 1 ]; then
            echo "  🎉 WIN! Kena Take Profit di harga $CURRENT_PRICE"
            PNL_PCT=$(echo "scale=2; (($TP - $ENTRY) / $ENTRY) * 100" | bc -l)
            sqlite3 virtual_trading.db "UPDATE virtual_trades SET closed=1, result='WIN', pnl_pct=$PNL_PCT WHERE id=$ID;"
            
        elif [ "$HIT_SL" -eq 1 ]; then
            echo "  💀 CLOSED! Kena Stop Loss di harga $CURRENT_PRICE"
            PNL_PCT=$(echo "scale=2; (($SL - $ENTRY) / $ENTRY) * 100" | bc -l)
            
            # Cek apakah ini Stop Loss rugi, atau Stop Loss yang untung (karena Trailing)
            IS_PROFIT=$(echo "$PNL_PCT > 0" | bc -l)
            if [ "$IS_PROFIT" -eq 1 ]; then
                 RESULT="WIN_TRAILING"
                 echo "  ✅ Kena SL tapi tetap CUAN $PNL_PCT%!"
            else
                 RESULT="LOSS"
            fi
            
            sqlite3 virtual_trading.db "UPDATE virtual_trades SET closed=1, result='$RESULT', pnl_pct=$PNL_PCT WHERE id=$ID;"
        else
            echo "  ⏳ Posisi masih berjalan (Floating). Profit saat ini: $PROFIT_PCT%"
        fi
    fi
    echo "----------------------------------------"
done
