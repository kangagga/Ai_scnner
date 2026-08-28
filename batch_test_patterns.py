"""
batch_test_patterns.py
=======================
Batch scan chart pattern di seluruh WATCHLIST bot (config.py), untuk
timeframe 1h & 4h, TANPA menyentuh bot yang jalan.

Tujuan: cari beberapa contoh pair yang KEBETULAN pattern-nya terdeteksi,
supaya bisa divalidasi manual di TradingView (bukan cuma BTC yang lagi
trending murni tanpa pattern apapun).

CARA PAKAI:
    python3 batch_test_patterns.py
    python3 batch_test_patterns.py 4h      # hanya scan timeframe 4h
    python3 batch_test_patterns.py 1h 50   # scan 1h, hanya 50 pair pertama

Output: daftar pair + pattern yang terdeteksi, diurutkan strength tertinggi,
supaya kamu bisa langsung cek manual pair yang paling menonjol dulu.
"""

import sys
import time
import pandas as pd

from chart_patterns import detect_all_patterns
from data_fetcher import fetch_ohlcv
from config import WATCHLIST, TIMEFRAMES


def scan(timeframes, pair_limit):
    pairs = WATCHLIST[:pair_limit]
    all_results = []
    errors = []

    print(f"Scanning {len(pairs)} pair x {timeframes} ...\n")

    for tf in timeframes:
        for i, symbol in enumerate(pairs):
            try:
                raw = fetch_ohlcv(symbol, tf, limit=300)
                df = pd.DataFrame(raw) if not isinstance(raw, pd.DataFrame) else raw
                df.columns = [c.lower() for c in df.columns]
                if len(df) < 60:
                    continue
                found = detect_all_patterns(df)
                for r in found:
                    all_results.append({
                        "symbol": symbol,
                        "timeframe": tf,
                        "pattern": r["pattern"],
                        "direction": r["direction"],
                        "strength": r["strength"],
                    })
            except Exception as e:
                errors.append((symbol, tf, str(e)))
            # jeda kecil supaya tidak membebani rate limit Gate.io
            time.sleep(0.15)
            if (i + 1) % 25 == 0:
                print(f"  [{tf}] {i+1}/{len(pairs)} pair discan...")

    return all_results, errors


def main():
    timeframes = TIMEFRAMES
    pair_limit = len(WATCHLIST)

    if len(sys.argv) > 1:
        timeframes = [sys.argv[1]]
    if len(sys.argv) > 2:
        pair_limit = int(sys.argv[2])

    results, errors = scan(timeframes, pair_limit)

    print(f"\n=== HASIL: {len(results)} pattern terkonfirmasi ditemukan ===\n")
    results.sort(key=lambda r: r["strength"], reverse=True)
    for r in results:
        print(f"{r['symbol']:15s} {r['timeframe']:3s}  {r['pattern']:28s} "
              f"{r['direction']:8s} strength={r['strength']}")

    if errors:
        print(f"\n=== {len(errors)} error saat fetch/deteksi (pair mungkin delisted/tidak ada di Gate.io) ===")
        for symbol, tf, err in errors[:15]:
            print(f"  {symbol} {tf}: {err}")
        if len(errors) > 15:
            print(f"  ... dan {len(errors) - 15} error lainnya")


if __name__ == "__main__":
    main()
