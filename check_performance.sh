#!/bin/bash
DB="/home/userland/ai-scanner/virtual_trading.db"

echo "=================================================="
echo "  PERFORMA BOT SEJAK BASELINE"
echo "=================================================="

sqlite3 "$DB" "
SELECT
  bm.marker_name AS 'Baseline',
  bm.created_at AS 'Dibuat',
  bm.last_trade_id_before_baseline AS 'Mulai dari ID'
FROM baseline_markers bm
ORDER BY bm.id DESC LIMIT 1;
"

echo "--------------------------------------------------"
echo "RINGKASAN TOTAL (AUTO + MANUAL):"

sqlite3 -header -column "$DB" "
SELECT
  COUNT(*) AS total_trade,
  SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) AS losses,
  ROUND(SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END)*100.0/NULLIF(COUNT(*),0),1) AS winrate_pct,
  ROUND(SUM(pnl_usdt),2) AS net_pnl_usdt
FROM virtual_trades
WHERE closed=1 AND result IN ('WIN','LOSS')
  AND id > (SELECT last_trade_id_before_baseline FROM baseline_markers ORDER BY id DESC LIMIT 1);
"

echo "--------------------------------------------------"
echo "BREAKDOWN AUTO vs MANUAL:"

sqlite3 -header -column "$DB" "
SELECT
  CASE WHEN signal LIKE '%MANUAL%' THEN 'MANUAL' ELSE 'AUTO' END as tipe,
  COUNT(*) as total,
  SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins,
  SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
  ROUND(SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) as winrate_pct,
  ROUND(SUM(pnl_usdt),2) as net_pnl_usdt,
  ROUND(AVG(pnl_usdt),3) as avg_pnl_per_trade
FROM virtual_trades
WHERE closed=1 AND result IN ('WIN','LOSS')
  AND id > (SELECT last_trade_id_before_baseline FROM baseline_markers ORDER BY id DESC LIMIT 1)
GROUP BY tipe;
"

echo "--------------------------------------------------"
echo "Posisi terbuka saat ini:"

sqlite3 -header -column "$DB" "
SELECT id, symbol, signal, entry, timestamp
FROM virtual_trades
WHERE closed=0
ORDER BY id DESC;
"

echo "=================================================="
echo "Target evaluasi solid: min. 30 trade closed per tipe (AUTO & MANUAL)"
echo "=================================================="
