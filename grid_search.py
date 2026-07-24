from backtester import run_backtest
import pandas as pd

PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "LTCUSDT", "BCHUSDT"]
CONFIDENCE_LEVELS = [30, 40, 50, 60, 70]
DAYS = 90
TIMEFRAME = "1h"

results = []

for min_conf in CONFIDENCE_LEVELS:
    print(f"\n=== Testing min_confidence = {min_conf} ===")
    agg_total = 0
    agg_wins = 0
    agg_pnl = 0.0
    pairs_tested = 0
    pairs_profitable = 0

    for pair in PAIRS:
        r = run_backtest(pair, timeframe=TIMEFRAME, days=DAYS, min_confidence=min_conf)
        if r is None or r["total"] == 0:
            print(f"  {pair}: no trades")
            continue
        pairs_tested += 1
        if r["total_pnl"] > 0:
            pairs_profitable += 1
        agg_total += r["total"]
        agg_wins += r["wins"]
        agg_pnl += r["total_pnl"]
        print(f"  {pair}: trades={r['total']} WR={r['win_rate']}% PnL={r['total_pnl']}% PF={r['profit_factor']}")

    overall_wr = round(100 * agg_wins / agg_total, 1) if agg_total > 0 else 0
    results.append({
        "min_confidence": min_conf,
        "pairs_tested": pairs_tested,
        "pairs_profitable": pairs_profitable,
        "total_trades": agg_total,
        "overall_win_rate": overall_wr,
        "total_pnl_sum": round(agg_pnl, 2),
    })

print("\n\n" + "="*70)
print("RINGKASAN GRID SEARCH")
print("="*70)
df_summary = pd.DataFrame(results)
print(df_summary.to_string(index=False))
df_summary.to_csv("grid_search_results.csv", index=False)
print("\n✅ Hasil lengkap disimpan ke grid_search_results.csv")
