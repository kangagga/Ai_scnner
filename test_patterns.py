"""
test_patterns.py
================
Script test STANDALONE untuk verifikasi manual chart_patterns.py.
BELUM menyentuh bot (indicators.py / scanner.py / telegram_sender.py) sama sekali.

CARA PAKAI:
    python3 test_patterns.py BTC/USDT 1h

Script ini akan:
    - Pakai fetch_ohlcv yang SUDAH ADA di data_fetcher.py (tidak duplikat logic fetch)
    - Jalankan semua detector di chart_patterns.py
    - Print hasil dalam format mudah dibaca + print juga swing high/low
      yang kepakai, supaya kamu bisa cocokkan manual dengan chart di
      TradingView / exchange.
"""

import sys
import pandas as pd

from chart_patterns import (
    find_swing_points,
    detect_double_top_bottom,
    detect_head_and_shoulders,
    detect_triangle,
    detect_wedge,
    detect_flag_pennant,
    detect_all_patterns,
)

try:
    from data_fetcher import fetch_ohlcv
except ImportError as e:
    print(f"[ERROR] Gagal import fetch_ohlcv dari data_fetcher.py: {e}")
    print("Cek signature asli fetch_ohlcv dan kasih tahu Claude, jangan lanjut dulu.")
    sys.exit(1)


def main():
    if len(sys.argv) < 3:
        print("Pemakaian: python3 test_patterns.py <SYMBOL> <TIMEFRAME>")
        print("Contoh   : python3 test_patterns.py BTC/USDT 1h")
        sys.exit(1)

    symbol = sys.argv[1]
    timeframe = sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    print(f"\n=== Testing chart patterns: {symbol} {timeframe} (limit={limit} candle) ===\n")

    # NOTE: kalau fetch_ohlcv mengembalikan bukan DataFrame dengan kolom
    # open/high/low/close/volume, sesuaikan konversi di bawah ini.
    raw = fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(raw) if not isinstance(raw, pd.DataFrame) else raw

    expected_cols = {"open", "high", "low", "close", "volume"}
    missing = expected_cols - set(c.lower() for c in df.columns)
    if missing:
        print(f"[WARNING] Kolom hilang/beda nama: {missing}")
        print(f"Kolom yang ada: {list(df.columns)}")
        print("Sesuaikan mapping kolom sebelum lanjut.")
        sys.exit(1)

    df.columns = [c.lower() for c in df.columns]
    print(f"Jumlah candle diterima: {len(df)}")
    print(f"Harga close terakhir : {df['close'].iloc[-1]}\n")

    # --- Swing points mentah, buat sanity check manual ---
    swing_highs, swing_lows = find_swing_points(df, order=5)
    print(f"Jumlah swing high terdeteksi: {len(swing_highs)}")
    print(f"Jumlah swing low terdeteksi : {len(swing_lows)}")
    if swing_highs:
        print("5 swing high terakhir (index, harga):")
        for i, p in swing_highs[-5:]:
            print(f"   idx={i:4d}  price={p}")
    if swing_lows:
        print("5 swing low terakhir (index, harga):")
        for i, p in swing_lows[-5:]:
            print(f"   idx={i:4d}  price={p}")
    print()

    # --- Jalankan tiap detector satu-satu (biar jelas kalau ada yang error) ---
    checks = {
        "Double Top/Bottom": lambda: detect_double_top_bottom(df),
        "Head and Shoulders": lambda: detect_head_and_shoulders(df),
        "Triangle": lambda: detect_triangle(df),
        "Wedge": lambda: detect_wedge(df),
        "Flag/Pennant": lambda: detect_flag_pennant(df),
    }

    for name, fn in checks.items():
        try:
            r = fn()
            status = "TERDETEKSI" if r["detected"] else "tidak terdeteksi"
            print(f"[{name}] {status}")
            if r["detected"]:
                print(f"    pattern   : {r['pattern']}")
                print(f"    direction : {r['direction']}")
                print(f"    strength  : {r['strength']}")
                print(f"    details   : {r['details']}")
        except Exception as e:
            print(f"[{name}] ERROR saat eksekusi: {e}")
        print()

    # --- Aggregator (yang nanti dipakai bot) ---
    print("=== Hasil detect_all_patterns() (yang akan dipakai untuk confidence boost) ===")
    all_found = detect_all_patterns(df)
    if not all_found:
        print("Tidak ada pattern terkonfirmasi saat ini.")
    for r in all_found:
        print(f" - {r['pattern']} | {r['direction']} | strength={r['strength']} | {r['details']}")


if __name__ == "__main__":
    main()
