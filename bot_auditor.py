
import sqlite3, json, os, sys
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))

def get_db():
    return sqlite3.connect("/home/userland/ai-scanner/signals.db")

def audit_win_rate():
    issues = []
    conn = sqlite3.connect("/home/userland/ai-scanner/virtual_trading.db")
    cur = conn.cursor()
    # [FIX 2026-08-20] Sumber data: virtual_trades (bukan tabel performance
    # yang sudah tidak pernah diisi sejak sistem pindah ke virtual_trading.db)
    cutoff_wib = (datetime.now(WIB) - timedelta(days=2)).strftime("%Y-%m-%d")
    cur.execute(
        "SELECT substr(closed_at,1,10), COUNT(*), ROUND(100.0 * SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) / COUNT(*), 1) "
        "FROM virtual_trades WHERE closed=1 AND closed_at >= ? GROUP BY substr(closed_at,1,10) ORDER BY substr(closed_at,1,10) DESC",
        (cutoff_wib,)
    )
    rows = cur.fetchall()
    conn.close()
    if len(rows) >= 2:
        wr_today, wr_yesterday = rows[0][2], rows[1][2]
        if wr_today < 50:
            issues.append("Peringatan Win rate rendah hari ini: " + str(wr_today) + "%")
        if wr_yesterday - wr_today > 20:
            issues.append("Win rate drop " + str(round(wr_yesterday-wr_today,1)) + "% dari kemarin")
    return issues

def audit_active_trades():
    issues = []
    try:
        # [FIX 2026-08-20] Sumber data: virtual_trades WHERE closed=0 (bukan
        # active_trades.json yang tidak lagi disentuh oleh /live_positions
        # maupun handler Close Posisi)
        conn = sqlite3.connect("/home/userland/ai-scanner/virtual_trading.db")
        cur = conn.cursor()
        cur.execute("SELECT symbol, tp1, tp2, tp3 FROM virtual_trades WHERE closed=0")
        rows = cur.fetchall()
        conn.close()
        stuck = [r[0] for r in rows if (r[1] or 0) == 0 and (r[2] or 0) == 0 and (r[3] or 0) == 0]
        if stuck:
            issues.append(str(len(stuck)) + " posisi stuck TP=0")
        if len(rows) > 30:
            issues.append("Posisi terbuka terlalu banyak: " + str(len(rows)))
    except Exception as e:
        issues.append("Gagal baca virtual_trades: " + str(e))
    return issues

def audit_consecutive_loss():
    issues = []
    # [FIX 2026-08-20] Sumber data: virtual_trades (bukan tabel performance)
    conn = sqlite3.connect("/home/userland/ai-scanner/virtual_trading.db")
    cur = conn.cursor()
    cur.execute("SELECT result FROM virtual_trades WHERE closed=1 ORDER BY closed_at DESC LIMIT 20")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    streak = 0
    for r in rows:
        if r == "LOSS": streak += 1
        else: break
    if streak >= 5:
        issues.append("KRITIS Loss beruntun " + str(streak) + " trade!")
    elif streak >= 3:
        issues.append("Loss beruntun " + str(streak) + " trade")
    return issues

def audit_log_errors():
    issues = []
    try:
        with open("/home/userland/ai-scanner/signal_bot.log") as f:
            lines = f.readlines()[-1000:]
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        errors   = [l for l in lines if "[ERROR]" in l and today in l]
        timeouts = [l for l in lines if "TIMEOUT" in l and today in l]
        unknown  = [l for l in lines if "UNKNOWN" in l and today in l]
        if len(errors) > 10:
            issues.append("Error tinggi: " + str(len(errors)) + " error hari ini")
        if len(timeouts) > 50:
            issues.append("Timeout Gate.io: " + str(len(timeouts)) + "x hari ini")
        if len(unknown) > 20:
            issues.append("Regime UNKNOWN: " + str(len(unknown)) + "x hari ini")
    except Exception as e:
        issues.append("Gagal baca log: " + str(e))
    return issues

def run_audit():
    sys.path.insert(0, "/home/userland/ai-scanner")
    from telegram_sender import send_alert
    now = datetime.now(WIB).strftime("%d/%m/%Y %H:%M")
    issues = audit_win_rate() + audit_active_trades() + audit_log_errors() + audit_consecutive_loss()

    # [FIX 2026-08-20] Sumber data: virtual_trades (bukan tabel performance)
    conn = sqlite3.connect("/home/userland/ai-scanner/virtual_trading.db")
    cur = conn.cursor()
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END), SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END), ROUND(AVG(pnl_pct),2), ROUND(SUM(pnl_pct),2) FROM virtual_trades WHERE closed=1 AND substr(closed_at,1,10)='" + today + "'")
    row = cur.fetchone()
    conn.close()
    total = row[0] or 0
    menang = row[1] or 0
    kalah = row[2] or 0
    avg_pnl = row[3] or 0
    total_pnl = row[4] or 0
    wr = round(100*menang/total,1) if total else 0
    status = "SEHAT" if not issues else str(len(issues)) + " MASALAH DITEMUKAN"

    msg = "<b>AUDIT BOT HARIAN</b>\n"
    msg += "Waktu: " + now + " WIB\n"
    msg += "Status: " + status + "\n\n"
    msg += "<b>Ringkasan Hari Ini:</b>\n"
    msg += "Total trade : " + str(total) + "\n"
    msg += "Menang/Kalah: " + str(menang) + "/" + str(kalah) + "\n"
    msg += "Win Rate    : " + str(wr) + "%\n"
    msg += "Avg PnL     : " + str(avg_pnl) + "%\n"
    msg += "Total PnL   : " + str(total_pnl) + "%\n"
    if issues:
        msg += "\nMasalah:\n"
        for i in issues:
            msg += "- " + i + "\n"
    else:
        msg += "\nTidak ada masalah terdeteksi"

    # FIX: tambahkan analisa kualitatif Groq AI sebagai lapisan tambahan
    try:
        from ai_analyst import _call_groq
        audit_summary = (
            f"Total trade hari ini: {total}, Menang: {menang}, Kalah: {kalah}, "
            f"Win Rate: {wr}%, Avg PnL: {avg_pnl}%, Total PnL: {total_pnl}%\n"
            f"Masalah rule-based terdeteksi: {'; '.join(issues) if issues else 'tidak ada'}"
        )
        ai_prompt = (
            f"Kamu adalah auditor sistem trading bot crypto (Bahasa Indonesia, singkat max 5 kalimat).\n"
            f"Waktu audit sekarang: {now} WIB.\n"
            f"Data audit hari ini:\n{audit_summary}\n\n"
            f"PENTING - pertimbangkan jam audit sebelum menyimpulkan: kalau audit dijalankan "
            f"dini hari (00:00-07:00 WIB) dan trade masih 0, itu WAJAR karena hari baru saja "
            f"mulai -- JANGAN sebut ini sebagai anomali atau kecurigaan gangguan sistem. "
            f"Hanya curigai 0 trade sebagai masalah kalau audit dijalankan siang/sore/malam "
            f"(sudah banyak jam berlalu sejak tengah malam) dan tetap 0.\n"
            f"Analisa: apakah ada pola anomali yang mencurigakan (bukan soal sinyal trading, "
            f"tapi soal kesehatan sistem - misal performa tiba-tiba memburuk drastis, "
            f"terlalu banyak posisi terbuka, atau pola error yang berulang)? "
            f"Beri rekomendasi konkret jika ada yang perlu diperhatikan."
        )
        ai_result = _call_groq(ai_prompt, max_tokens=300)
        if ai_result:
            msg += "\n\n<b>🤖 Analisa AI:</b>\n" + ai_result
    except Exception as _e:
        msg += f"\n\n⚠️ Analisa AI gagal: {_e}"

    msg += "\n\nAI Signal Bot Auto Audit"
    send_alert(msg)
    print("Audit selesai")
    print("Issues:", issues)

if __name__ == "__main__":
    run_audit()

def get_summary_today():
    """Return ringkasan trading hari ini untuk /health"""
    from datetime import datetime
    try:
        db = get_db()
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Ambil trades hari ini - sesuaikan query sama struktur DB lo
        trades = db.get(f"trades_{today}") if hasattr(db, 'get') else []
        
        if not trades:
            return {'status': '✅ Online', 'date': today, 'total_trades': 0}
        
        wins = sum(1 for t in trades if t.get('is_win'))
        total = len(trades)
        
        return {
            'status': '✅ Running',
            'date': today,
            'total_trades': total,
            'wins': wins,
            'losses': total - wins,
            'win_rate': f"{(wins/total*100):.1f}%" if total else 'N/A',
            'active_positions': sum(1 for t in trades if t.get('status') == 'open')
        }
    except Exception as e:
        return {'status': f'⚠️ {str(e)}', 'date': datetime.now().strftime("%Y-%m-%d")}
