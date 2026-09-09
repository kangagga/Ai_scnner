import ast
import shutil
import sys

FILE = "scanner.py"
BACKUP = FILE + ".bak_before_stablecoin_exclude"

with open(FILE, "r", encoding="utf-8") as f:
    lines = f.readlines()

# ============================================================
# Anchor: blok filter LEVERAGED_SUFFIXES (baris 833-841)
# ============================================================
START_IDX = 832  # 0-indexed untuk baris 833

old_block = [
    '            LEVERAGED_SUFFIXES = ("3L","5L","3S","5S","2L","2S","10L","10S")\n',
    '            seen, symbols = set(), []\n',
    '            for s in combined:\n',
    '                if s not in seen:\n',
    '                    seen.add(s)\n',
    '                    base = s[:-4] if s.endswith("USDT") else s\n',
    '                    if base.endswith(LEVERAGED_SUFFIXES):\n',
    '                        continue\n',
    '                    symbols.append(s)\n',
]

actual_block = lines[START_IDX:START_IDX + len(old_block)]

if actual_block != old_block:
    print("GAGAL: Anchor blok baris 833-841 tidak cocok persis. Tidak ada file yang diubah.")
    print("Isi baris 833-841 saat ini:")
    for l in actual_block:
        print(repr(l))
    sys.exit(1)

new_block = [
    '            LEVERAGED_SUFFIXES = ("3L","5L","3S","5S","2L","2S","10L","10S")\n',
    '            STABLECOIN_BASES = {\n',
    '                "USDT", "USDC", "DAI", "TUSD", "BUSD", "FDUSD", "USDD",\n',
    '                "PYUSD", "GUSD", "USDP", "USDG", "EURT", "EURC", "USTC",\n',
    '                "FRAX", "LUSD",\n',
    '            }\n',
    '            seen, symbols = set(), []\n',
    '            for s in combined:\n',
    '                if s not in seen:\n',
    '                    seen.add(s)\n',
    '                    base = s[:-4] if s.endswith("USDT") else s\n',
    '                    if base.endswith(LEVERAGED_SUFFIXES):\n',
    '                        continue\n',
    '                    if base in STABLECOIN_BASES:\n',
    '                        continue\n',
    '                    symbols.append(s)\n',
]

lines[START_IDX:START_IDX + len(old_block)] = new_block
print("OK: Patch exclude stablecoin siap diterapkan.")

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
