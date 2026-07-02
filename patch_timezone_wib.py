#!/usr/bin/env python3
"""
patch_timezone_wib.py — Perbaiki bug inkonsistensi timezone.

Masalah: OS UserLand berjalan di UTC, tapi semua timestamp yang disimpan
ke database eksplisit pakai WIB (+07:00). Query yang pakai date('now'),
datetime('now'), atau 'localtime' modifier SQLite mengikuti timezone OS
(UTC), sehingga salah mengelompokkan tanggal terutama untuk trade yang
terjadi di jam 00:00-06:59 WIB (dini hari) — pada jam tersebut UTC-nya
masih tanggal sebelumnya.

Perbaikan: hitung cutoff/tanggal pembanding di Python memakai
datetime.now(WIB) secara eksplisit, lalu kirim sebagai parameter ke query
SQL (bukan biarkan SQLite yang menghitung 'now' versinya sendiri).

Jalankan dari ~/ai-scanner: python3 patch_timezone_wib.py
"""

import re


def patch_bot_auditor():
    """Perbaiki audit_win_rate() di bot_auditor.py — filter 2 hari WIB eksplisit."""
    path = "bot_auditor.py"
    with open(path, "r") as f:
        content = f.read()

    old = '''def audit_win_rate():
    issues = []
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT date(timestamp), COUNT(*), ROUND(100.0 * SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) / COUNT(*), 1) FROM performance WHERE timestamp >= date('now', '-2 days') GROUP BY date(timestamp) ORDER BY date(timestamp) DESC")
    rows = cur.fetchall()
    conn.close()'''

    new = '''def audit_win_rate():
    issues = []
    conn = get_db()
    cur = conn.cursor()
    # [FIX-TZ] Hitung cutoff pakai WIB eksplisit, bukan date('now') SQLite
    # yang mengikuti timezone OS (UTC) sedangkan timestamp tersimpan WIB.
    cutoff_wib = (datetime.now(WIB) - timedelta(days=2)).strftime("%Y-%m-%d")
    cur.execute(
        "SELECT date(timestamp), COUNT(*), ROUND(100.0 * SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) / COUNT(*), 1) "
        "FROM performance WHERE timestamp >= ? GROUP BY date(timestamp) ORDER BY date(timestamp) DESC",
        (cutoff_wib,)
    )
    rows = cur.fetchall()
    conn.close()'''

    if old not in content:
        print(f"[{path}] GAGAL: pattern audit_win_rate tidak ditemukan persis")
        return False

    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)
    print(f"[{path}] OK: audit_win_rate() diperbaiki (cutoff WIB eksplisit)")
    return True


def patch_database():
    """Perbaiki get_today_signals() di database.py — pakai tanggal WIB eksplisit."""
    path = "database.py"
    with open(path, "r") as f:
        content = f.read()

    old = '''        c.execute("SELECT * FROM signals WHERE date(timestamp) = date('now', 'localtime') ORDER BY confidence DESC")'''

    new = '''        # [FIX-TZ] 'localtime' modifier SQLite ikut timezone OS (UTC),
        # padahal timestamp tersimpan dalam WIB. Hitung tanggal WIB eksplisit.
        from datetime import datetime, timezone, timedelta
        _WIB = timezone(timedelta(hours=7))
        _today_wib = datetime.now(_WIB).strftime("%Y-%m-%d")
        c.execute("SELECT * FROM signals WHERE date(timestamp) = ? ORDER BY confidence DESC", (_today_wib,))'''

    if old not in content:
        print(f"[{path}] GAGAL: pattern get_today_signals tidak ditemukan persis")
        return False

    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)
    print(f"[{path}] OK: get_today_signals() diperbaiki (tanggal WIB eksplisit)")
    return True


def patch_api_server():
    """Perbaiki equity curve 7 hari di api_server.py — cutoff WIB eksplisit."""
    path = "api_server.py"
    with open(path, "r") as f:
        content = f.read()

    old = '''        # Equity curve 7 hari terakhir — pakai balance_after tiap trade closed
        cur.execute("""
            SELECT closed_at, balance_after FROM virtual_trades
            WHERE closed = 1 AND closed_at >= date('now', '-7 days')
            ORDER BY closed_at ASC
        """)'''

    new = '''        # [FIX-TZ] Equity curve 7 hari terakhir — cutoff dihitung pakai WIB
        # eksplisit di Python, bukan date('now') SQLite yang ikut timezone OS (UTC).
        from datetime import datetime, timezone as _tz, timedelta as _td
        _WIB = _tz(_td(hours=7))
        _cutoff_wib = (datetime.now(_WIB) - _td(days=7)).isoformat()
        cur.execute("""
            SELECT closed_at, balance_after FROM virtual_trades
            WHERE closed = 1 AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (_cutoff_wib,))'''

    if old not in content:
        print(f"[{path}] GAGAL: pattern equity curve tidak ditemukan persis")
        return False

    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)
    print(f"[{path}] OK: equity curve 7 hari diperbaiki (cutoff WIB eksplisit)")
    return True


if __name__ == "__main__":
    print("=== PATCH TIMEZONE WIB ===\n")
    results = [
        patch_bot_auditor(),
        patch_database(),
        patch_api_server(),
    ]
    print(f"\n=== SELESAI: {sum(results)}/3 file berhasil dipatch ===")
