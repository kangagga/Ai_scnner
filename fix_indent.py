with open('main.py', 'r') as f:
    content = f.read()

old = '''                if not AUTO_EXECUTE:
                    if ("EKSEKUSI" in level) or ("SIAP ENTRY" in level):
                        logger.info(f"[MANUAL_MODE] {sig.get('symbol')} {sig.get('signal')} conf={conf} WR={wr}% level={level} -- auto-execute OFF, tunggu /execute manual")
                    continue

                if ("EKSEKUSI" in level) or ("SIAP ENTRY" in level):'''

new = '''                    if not AUTO_EXECUTE:
                        if ("EKSEKUSI" in level) or ("SIAP ENTRY" in level):
                            logger.info(f"[MANUAL_MODE] {sig.get('symbol')} {sig.get('signal')} conf={conf} WR={wr}% level={level} -- auto-execute OFF, tunggu /execute manual")
                        continue

                    if ("EKSEKUSI" in level) or ("SIAP ENTRY" in level):'''

if old in content:
    content = content.replace(old, new, 1)
    with open('main.py', 'w') as f:
        f.write(content)
    print("✅ Indentasi diperbaiki")
else:
    print("❌ Pattern tidak ketemu — perlu cek manual")
