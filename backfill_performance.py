"""
backfill_performance.py — Sinkronkan data historis dari virtual_trading.db (virtual_trades)
ke signals.db (tabel performance), karena tabel performance selama ini kosong
akibat update_signal_result() tidak pernah dipanggil.

Jalankan SEKALI SAJA dari folder ai-scanner:
    python3 backfill_performance.py

Aman dijalankan berkali-kali (skip duplikat berdasarkan symbol+timestamp+entry).
"""

import sqlite3

VT_DB   = "virtual_trading.db"
SIG_DB  = "signals.db"

def main():
    vt_conn = sqlite3.connect(VT_DB)
    vt_conn.row_factory = sqlite3.Row
    vt_c = vt_conn.cursor()

    sig_conn = sqlite3.connect(SIG_DB)
    sig_c = sig_conn.cursor()

    vt_c.execute("""
        SELECT timestamp, symbol, signal, entry, exit_price, pnl_pct, result,
               timeframe, regime
        FROM virtual_trades
        WHERE closed = 1
    """)
    rows = vt_c.fetchall()
    print(f"Ditemukan {len(rows)} closed trades di virtual_trades.")

    inserted = 0
    skipped  = 0

    for r in rows:
        # Cek duplikat: apakah sudah ada baris performance dengan symbol+timestamp+entry yang sama
        sig_c.execute("""
            SELECT COUNT(*) FROM performance
            WHERE symbol = ? AND timestamp = ? AND entry = ?
        """, (r["symbol"], r["timestamp"], r["entry"]))
        exists = sig_c.fetchone()[0]

        if exists:
            skipped += 1
            continue

        sig_c.execute("""
            INSERT INTO performance (
                timestamp, symbol, signal, entry, exit_price, pnl_pct, result,
                timeframe, regime
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["timestamp"], r["symbol"], r["signal"], r["entry"],
            r["exit_price"], r["pnl_pct"], r["result"],
            r["timeframe"], r["regime"]
        ))
        inserted += 1

    sig_conn.commit()
    print(f"Berhasil insert {inserted} baris baru, skip {skipped} duplikat.")

    # Verifikasi akhir
    sig_c.execute("SELECT COUNT(*) FROM performance")
    total = sig_c.fetchone()[0]
    print(f"Total baris di tabel performance sekarang: {total}")

    vt_conn.close()
    sig_conn.close()


if __name__ == "__main__":
    main()

