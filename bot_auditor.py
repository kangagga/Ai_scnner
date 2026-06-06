
import sqlite3, json, os, sys
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))

def get_db():
    return sqlite3.connect("/home/userland/ai-scanner/signals.db")

def audit_win_rate():
    issues = []
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT date(timestamp), COUNT(*), ROUND(100.0 * SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) / COUNT(*), 1) FROM performance WHERE timestamp >= date('now', '-2 days') GROUP BY date(timestamp) ORDER BY date(timestamp) DESC")
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
        with open("/home/userland/ai-scanner/active_trades.json") as f:
            trades = json.load(f)
        stuck = [k for k,t in trades.items() if t.get("tp1",0)==0 and t.get("tp2",0)==0 and t.get("tp3",0)==0]
        if stuck:
            issues.append(str(len(stuck)) + " posisi stuck TP=0")
        if len(trades) > 30:
            issues.append("Posisi terbuka terlalu banyak: " + str(len(trades)))
    except Exception as e:
        issues.append("Gagal baca active_trades: " + str(e))
    return issues

def audit_consecutive_loss():
    issues = []
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT result FROM performance ORDER BY timestamp DESC LIMIT 20")
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

    conn = get_db()
    cur = conn.cursor()
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END), SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END), ROUND(AVG(pnl_pct),2), ROUND(SUM(pnl_pct),2) FROM performance WHERE date(timestamp)='" + today + "'")
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
    msg += "\n\nAI Signal Bot Auto Audit"
    send_alert(msg)
    print("Audit selesai")
    print("Issues:", issues)

if __name__ == "__main__":
    run_audit()
