"""
debug_setup.py — Analisa kenapa sinyal SETUP jarang muncul.

Cara pakai (jalankan di folder ai-scanner, dengan venv aktif):
    python3 debug_setup.py

Script ini akan:
1. Ambil OHLCV untuk semua pair di WATCHLIST (timeframe 1h, limit 300)
2. Jalankan institutional_ai_v4 (fungsi yang sama dipakai scanner.py)
3. Untuk SETIAP baris candle, hitung syarat mana dari buy_setup_cond / sell_setup_cond
   yang gagal (True/False per kondisi)
4. Rekap: dari total candle yang di-cek, berapa % gagal di kondisi apa
   -> ini nunjukin kondisi mana yang paling sering jadi penghambat
"""

import sys
import pandas as pd
import numpy as np

sys.path.insert(0, ".")

from config import WATCHLIST
from data_fetcher import fetch_ohlcv
from indicators import institutional_ai_v4

TIMEFRAME = "1h"
LIMIT = 300
MAX_PAIRS = 40  # batasi biar nggak kelamaan / kena rate limit

fail_counts = {}
total_candles = 0
near_miss_1 = 0   # candle yang cuma gagal di TEPAT 1 kondisi (paling dekat lolos)
setup_hits = 0

def check_conditions(row):
    """Re-implementasi kondisi buy_setup_cond dari indicators.py secara per-baris,
    supaya kita bisa lihat kondisi mana yang gagal untuk tiap baris."""
    conds = {}
    try:
        conds["squeeze_score>40"]   = row.get("squeeze_score", 0) > 30
        conds["vol_dry_up"]         = bool(row.get("vol_dry_up", False))
        conds["setup_buy_score>=35"] = row.get("setup_buy_score", 0) >= 35 if "setup_buy_score" in row else None
        conds["trend_up_weak"]      = bool(row.get("trend_up_weak", False))
        conds["rsi_30_70"]          = 30 < row.get("rsi", -1) < 70
        conds["adx<30"]             = row.get("adx", 999) < 30
        conds["macd_hist>0"]        = row.get("macd_hist", -1) > 0
        conds["no_shooting_star"]   = row.get("shooting_star", 1) == 0
        conds["no_evening_star"]    = row.get("evening_star", 1) == 0
        conds["no_bear_engulf"]     = row.get("bear_engulf", 1) == 0
        conds["no_doji"]            = row.get("doji", 1) == 0
    except Exception as e:
        return None
    return conds


def main():
    global total_candles, near_miss_1, setup_hits

    pairs = WATCHLIST[:MAX_PAIRS]
    print(f"Menganalisa {len(pairs)} pair, timeframe={TIMEFRAME} ...\n")

    for symbol in pairs:
        try:
            df = fetch_ohlcv(symbol, TIMEFRAME, limit=LIMIT)
            if df is None or len(df) < 100:
                continue
            df = institutional_ai_v4(df)
        except Exception as e:
            print(f"  [SKIP] {symbol}: {e}")
            continue

        # cek 50 candle terakhir aja (biar relevan dgn kondisi market saat ini)
        recent = df.tail(50)
        for _, row in recent.iterrows():
            conds = check_conditions(row)
            if conds is None:
                continue
            total_candles += 1

            failed = [k for k, v in conds.items() if v is False]
            if row.get("signal") == "BUY (SETUP)":
                setup_hits += 1

            if len(failed) == 0:
                setup_hits += 0  # sudah dihitung di atas kalau memang label match
            elif len(failed) == 1:
                near_miss_1 += 1

            for k in failed:
                fail_counts[k] = fail_counts.get(k, 0) + 1

        print(f"  [OK] {symbol}: {len(recent)} candle diproses")

    print("\n=== HASIL ANALISA ===")
    print(f"Total candle dicek : {total_candles}")
    print(f"Sinyal SETUP aktual: {setup_hits}")
    print(f"Near-miss (gagal cuma 1 syarat): {near_miss_1}")
    print("\nFrekuensi kegagalan per syarat (semakin tinggi = semakin sering jadi penghambat):")
    for k, v in sorted(fail_counts.items(), key=lambda x: -x[1]):
        pct = (v / total_candles * 100) if total_candles else 0
        print(f"  {k:25s}: gagal {v:5d}x ({pct:5.1f}%)")


if __name__ == "__main__":
    main()

