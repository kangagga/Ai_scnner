#!/usr/bin/env bash

BOT_DIR="$HOME/ai-scanner"

echo "========================================="
echo "      AI SCANNER SELF AUDIT V1"
echo "========================================="

cd "$BOT_DIR" || {
    echo "❌ Folder ai-scanner tidak ditemukan."
    exit 1
}

echo
echo "1. Cek File Penting"
for f in main.py scanner.py signal_engine.py adaptive_brain.py adaptive_brain_v6.py risk_manager.py indicators.py config.py
do
    if [ -f "$f" ]; then
        echo "✅ $f"
    else
        echo "❌ $f TIDAK ADA"
    fi
done

echo
echo "2. Cek Error Python"
python3 -m py_compile *.py 2>/tmp/audit_compile.log

if [ $? -eq 0 ]; then
    echo "✅ Tidak ada syntax error"
else
    echo "❌ Ada syntax error"
    cat /tmp/audit_compile.log
fi

echo
echo "3. Cek Log Terbaru"

find . -name "*.log" | while read f
do
    echo
    echo "----- $f -----"
    tail -20 "$f"
done

echo
echo "4. Cari Exception"

grep -Ri "Traceback\|ERROR\|Exception" . \
--include="*.log" \
--include="*.txt"

echo
echo "5. Cari Jumlah Signal"

grep -Ri "SIGNAL" . \
--include="*.log" \
| tail -20

echo
echo "6. Cari Filter"

grep -R "confidence" scanner.py signal_engine.py adaptive_brain*.py 2>/dev/null

grep -R "win_rate" scanner.py signal_engine.py adaptive_brain*.py 2>/dev/null

grep -R "score" scanner.py signal_engine.py adaptive_brain*.py 2>/dev/null

echo
echo "7. Cek Risk Manager"

grep -R "reject" risk_manager.py 2>/dev/null

grep -R "approve" risk_manager.py 2>/dev/null

echo
echo "8. Jumlah Pair"

grep -Ri "USDT" data_fetcher.py scanner.py 2>/dev/null | head

echo
echo "9. Cek Scanner"

grep -n "filtered_sig" main.py 2>/dev/null

grep -n "signals" scanner.py 2>/dev/null

echo
echo "10. Ringkasan"

echo "Jika:"
echo "- Banyak pair tetapi signal=0 -> filter terlalu ketat."
echo "- Banyak score tinggi tetapi tidak masuk -> risk manager."
echo "- Tidak ada pair -> data fetcher."
echo "- Ada exception -> bug kode."
echo "- Ada signal tapi Telegram kosong -> telegram bot."
echo "- Signal muncul sekali lalu berhenti -> loop scanner."

echo
echo "===== AUDIT SELESAI ====="
