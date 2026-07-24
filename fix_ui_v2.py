with open('telegram_sender.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Verifikasi dulu baris yang mau diganti sesuai ekspektasi
assert lines[451].strip() == 'text = text_raw.lower()', f"Baris 452 tidak sesuai: {lines[451]!r}"
assert 'if not text.startswith' in lines[453], f"Baris 454 tidak sesuai: {lines[453]!r}"

# Cari akhir blok (baris "if text == \"/status\":")
end_idx = None
for i in range(451, 550):
    if lines[i].strip() == 'if text == "/status":':
        end_idx = i
        break

if end_idx is None:
    print("NOT_FOUND: baris akhir blok tidak ketemu")
else:
    new_block = '''        text = text_raw.lower()

        # [FIX 2026-07-10] Tombol menu ditangani SEBELUM filter startswith("/")
        if text == "/start" or text == "/menu":
            _pending_action.pop(chat_id, None)
            _send_with_keyboard(
                "\U0001F916 <b>Selamat datang di AI Signal Bot</b>\\n"
                "Pilih menu di bawah, atau ketik command manual seperti biasa.",
                MAIN_MENU_KEYBOARD
            )
            continue

        if chat_id in _pending_action:
            action = _pending_action.pop(chat_id)
            if action == "analyze":
                text = f"/analyze {text_raw}".lower()
            elif action == "execute":
                text = f"/execute {text_raw}".lower()

        if text_raw == "\U0001F4CA Status":
            text = "/status"
        elif text_raw == "\U0001F4E1 Live Positions":
            text = "/live_positions"
        elif text_raw == "\U0001F50D Analyze Pair":
            _pending_action[chat_id] = "analyze"
            _send("\U0001F50D Ketik nama pair yang mau dianalisa, contoh: <code>BTCUSDT</code>")
            continue
        elif text_raw == "\U0001F3AF Execute Manual":
            _pending_action[chat_id] = "execute"
            _send("\U0001F3AF Ketik: <code>PAIR BUY</code> atau <code>PAIR SELL</code>\\nContoh: <code>BTCUSDT BUY</code>")
            continue
        elif text_raw == "\U0001F4C8 Pair Status":
            text = "/pair_status"
        elif text_raw == "\U0001F4CA Win Rate Pair":
            text = "/winrate_pair"
        elif text_raw == "\U0001F4C9 Sinyal Terakhir":
            text = "/sinyal"
        elif text_raw == "\U0001F504 Scan Manual":
            text = "/scan"
        elif text_raw == "\u26A0\uFE0F Reset Streak":
            text = "/reset_streak"
        elif text_raw == "\u2753 Bantuan":
            text = "/help"

        if not text.startswith("/"):
            continue

        if text == "/status":
'''
    lines[451:end_idx+1] = [new_block]

    with open('telegram_sender.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("SUCCESS: Blok berhasil diganti (baris 452 sampai " + str(end_idx+1) + ")")
