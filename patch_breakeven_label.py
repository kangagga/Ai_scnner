import ast
import shutil
import sys

FILE = "exit_monitor.py"
BACKUP = FILE + ".bak_before_breakeven_label"

with open(FILE, "r", encoding="utf-8") as f:
    lines = f.readlines()

# ============================================================
# Anchor: blok label BREAKEVEN / TRAILING STOP (baris 243-250)
# ============================================================
START_IDX = 242  # 0-indexed untuk baris 243

old_block = [
    '            if abs(pnl_pct) < 0.1:\n',
    '                label = "BREAKEVEN"\n',
    '                pnl_pct = 0.0\n',
    '            elif "TP" in label and is_profit:\n',
    '                emoji_result = "\U0001f4b0"\n',
    '            elif "STOP LOSS" in label and pnl_pct > 0:\n',
    '                label = "TRAILING STOP"\n',
    '                emoji_result = "\u2705"\n',
]

actual_block = lines[START_IDX:START_IDX + len(old_block)]

if actual_block != old_block:
    print("GAGAL: Anchor blok baris 243-250 tidak cocok persis. Tidak ada file yang diubah.")
    print("Isi baris 243-250 saat ini:")
    for l in actual_block:
        print(repr(l))
    sys.exit(1)

new_block = [
    '            if "STOP LOSS" in label and trade["entry"] and abs(target - trade["entry"]) <= abs(trade["entry"]) * 0.0005:\n',
    '                label = "STOP LOSS (BREAKEVEN)"\n',
    '            if abs(pnl_pct) < 0.1:\n',
    '                label = "BREAKEVEN"\n',
    '                pnl_pct = 0.0\n',
    '            elif "TP" in label and is_profit:\n',
    '                emoji_result = "\U0001f4b0"\n',
    '            elif "STOP LOSS" in label and pnl_pct > 0:\n',
    '                label = "TRAILING STOP"\n',
    '                emoji_result = "\u2705"\n',
]

lines[START_IDX:START_IDX + len(old_block)] = new_block
print("OK: Patch label STOP LOSS (BREAKEVEN) siap diterapkan.")

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
