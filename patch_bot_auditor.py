import ast
import shutil
import sys

FILE = "bot_auditor.py"
BACKUP = FILE + ".bak_before_sqlinj_getdb_fix"

with open(FILE, "r", encoding="utf-8") as f:
    lines = f.readlines()

# ============================================================
# PATCH 1: run_audit() - fix SQL Injection di baris 108
# ============================================================
IDX_108 = 107  # 0-indexed untuk baris 108

old_108 = ('    cur.execute("SELECT COUNT(*), SUM(CASE WHEN result=\'WIN\' THEN 1 ELSE 0 END), '
           'SUM(CASE WHEN result=\'LOSS\' THEN 1 ELSE 0 END), ROUND(AVG(pnl_pct),2), '
           'ROUND(SUM(pnl_pct),2) FROM virtual_trades WHERE closed=1 AND '
           'substr(closed_at,1,10)=\'" + today + "\'")\n')

new_108 = ('    cur.execute("SELECT COUNT(*), SUM(CASE WHEN result=\'WIN\' THEN 1 ELSE 0 END), '
           'SUM(CASE WHEN result=\'LOSS\' THEN 1 ELSE 0 END), ROUND(AVG(pnl_pct),2), '
           'ROUND(SUM(pnl_pct),2) FROM virtual_trades WHERE closed=1 AND '
           'substr(closed_at,1,10)=?", (today,))\n')

if lines[IDX_108] != old_108:
    print("GAGAL: Anchor baris 108 tidak cocok persis. Tidak ada file yang diubah.")
    print("Isi baris 108 saat ini:")
    print(repr(lines[IDX_108]))
    sys.exit(1)

lines[IDX_108] = new_108
print("OK: Patch 1 (SQL injection run_audit) siap diterapkan.")

# ============================================================
# PATCH 2: get_summary_today() - rewrite full, query virtual_trading.db
# ============================================================
start_anchor = "def get_summary_today():\n"
end_anchor = ('        return {\'status\': f\'\u26a0\ufe0f {str(e)}\', '
              '\'date\': datetime.now().strftime("%Y-%m-%d")}\n')

try:
    start_idx = lines.index(start_anchor)
except ValueError:
    print("GAGAL: Start anchor 'def get_summary_today():' tidak ditemukan.")
    sys.exit(1)

end_idx = None
for i in range(start_idx, len(lines)):
    if lines[i] == end_anchor:
        end_idx = i
        break

if end_idx is None:
    print("GAGAL: End anchor (baris except terakhir) tidak ditemukan setelah start anchor.")
    sys.exit(1)

new_func = '''def get_summary_today():
    """Return ringkasan trading hari ini untuk /health"""
    from datetime import datetime
    try:
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        conn = sqlite3.connect("/home/userland/ai-scanner/virtual_trading.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) "
            "FROM virtual_trades WHERE closed=1 AND substr(closed_at,1,10)=?",
            (today,)
        )
        row = cur.fetchone()
        total = row[0] or 0
        wins = row[1] or 0

        cur.execute("SELECT COUNT(*) FROM virtual_trades WHERE closed=0")
        active_row = cur.fetchone()
        active_positions = active_row[0] or 0

        conn.close()

        if not total:
            return {'status': '\u2705 Online', 'date': today, 'total_trades': 0, 'active_positions': active_positions}

        return {
            'status': '\u2705 Running',
            'date': today,
            'total_trades': total,
            'wins': wins,
            'losses': total - wins,
            'win_rate': f"{(wins/total*100):.1f}%" if total else 'N/A',
            'active_positions': active_positions
        }
    except Exception as e:
        return {'status': f'\u26a0\ufe0f {str(e)}', 'date': datetime.now(WIB).strftime("%Y-%m-%d")}
'''

lines[start_idx:end_idx + 1] = [new_func]
print("OK: Patch 2 (get_summary_today rewrite) siap diterapkan.")

# ============================================================
# VALIDASI SYNTAX SEBELUM DITULIS
# ============================================================
new_content = "".join(lines)

try:
    ast.parse(new_content)
except SyntaxError as e:
    print("GAGAL: Syntax error setelah patch, file TIDAK ditulis.")
    print(e)
    sys.exit(1)

# ============================================================
# BACKUP DAN TULIS
# ============================================================
shutil.copy(FILE, BACKUP)
with open(FILE, "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"SUKSES: {FILE} sudah dipatch. Backup ada di {BACKUP}")
