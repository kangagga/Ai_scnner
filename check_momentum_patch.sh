#!/bin/bash
DB=~/ai-scanner/virtual_trading.db

echo "======================================================"
echo "📊 PERBANDINGAN AUTO vs MANUAL — PRE vs POST PATCH"
echo "   Patch: RSI overbought fix + blow-off top penalty"
echo "          + early momentum volume spike (2026-07-19)"
echo "======================================================"
echo ""

BASELINE_ID=$(sqlite3 $DB "SELECT last_trade_id_before_baseline FROM baseline_markers WHERE marker_name='post_momentum_patch_2026-07-19' ORDER BY id DESC LIMIT 1;")

echo "Baseline: trade ID > $BASELINE_ID dianggap POST-PATCH"
echo ""

echo "--- PRE-PATCH (semua trade sampai ID $BASELINE_ID, exclude ERROR_OLD_DATA) ---"
sqlite3 -header -column $DB "
SELECT
    CASE WHEN signal LIKE '%MANUAL%' THEN 'MANUAL' ELSE 'AUTO' END as tipe,
    COUNT(*) as total_closed,
    SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as win,
    SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as loss,
    ROUND(100.0 * SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) / COUNT(*), 1) as winrate_pct,
    ROUND(SUM(pnl_usdt), 2) as net_pnl_usd
FROM virtual_trades
WHERE closed = 1 AND result != 'ERROR_OLD_DATA' AND id <= $BASELINE_ID
GROUP BY tipe;
"

echo ""
echo "--- POST-PATCH (trade ID > $BASELINE_ID) ---"
sqlite3 -header -column $DB "
SELECT
    CASE WHEN signal LIKE '%MANUAL%' THEN 'MANUAL' ELSE 'AUTO' END as tipe,
    COUNT(*) as total_closed,
    SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as win,
    SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as loss,
    ROUND(100.0 * SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) / COUNT(*), 1) as winrate_pct,
    ROUND(SUM(pnl_usdt), 2) as net_pnl_usd
FROM virtual_trades
WHERE closed = 1 AND id > $BASELINE_ID
GROUP BY tipe;
"

echo ""
echo "--- TP1 speed (POST-PATCH only) ---"
sqlite3 -header -column $DB "
SELECT
    CASE WHEN t.signal LIKE '%MANUAL%' THEN 'MANUAL' ELSE 'AUTO' END as tipe,
    COUNT(*) as jumlah_tp1_hit,
    ROUND(AVG((julianday(p.closed_at) - julianday(t.timestamp)) * 24), 2) as avg_jam_ke_tp1
FROM virtual_trade_partials p
JOIN virtual_trades t ON p.trade_id = t.id
WHERE p.tp_level = 'TP1' AND t.id > $BASELINE_ID
GROUP BY tipe;
"

echo ""
echo "--- Posisi masih OPEN saat ini (POST-PATCH) ---"
sqlite3 -header -column $DB "
SELECT id, symbol, signal, timestamp,
    ROUND((julianday('now') - julianday(timestamp)) * 24, 1) as jam_terbuka
FROM virtual_trades
WHERE closed = 0 AND id > $BASELINE_ID
ORDER BY timestamp ASC;
"
echo ""
echo "======================================================"
echo "Catatan: target minimal 15-20 trade AUTO post-patch"
echo "sebelum kesimpulan bisa dianggap cukup meyakinkan."
echo "======================================================"
