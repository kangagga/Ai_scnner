import ast
import shutil
import sys

FILE = "exit_monitor.py"
BACKUP = FILE + ".bak_before_blacklist_breakeven_exclude"

with open(FILE, "r", encoding="utf-8") as f:
    lines = f.readlines()

# ============================================================
# Anchor: kondisi auto-blacklist setelah SL (baris 301, sudah
# geser +2 dari patch breakeven_label sebelumnya)
# ============================================================
IDX_301 = 300  # 0-indexed untuk baris 301

old_301 = '            if "STOP LOSS" in label:\n'
new_301 = '            if "STOP LOSS" in label and "BREAKEVEN" not in label:\n'

if lines[IDX_301] != old_301:
    print("GAGAL: Anchor baris 301 tidak cocok persis. Tidak ada file yang diubah.")
    print("Isi baris 301 saat ini:")
    print(repr(lines[IDX_301]))
    sys.exit(1)

lines[IDX_301] = new_301
print("OK: Patch exclude breakeven dari blacklist siap diterapkan.")

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
