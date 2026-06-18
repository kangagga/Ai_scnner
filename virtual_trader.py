
import sqlite3, json, os
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
VIRTUAL_DB = "/home/userland/ai-scanner/virtual_trading.db"
VIRTUAL_BALANCE = 1000.0  # Balance awal $1000

def init_db():
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS virtual_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            signal TEXT,
            entry REAL,
            sl REAL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            exit_price REAL,
            pnl_pct REAL,
            pnl_usd REAL,
            result TEXT,
            balance_after REAL,
            timeframe TEXT
        );
        CREATE TABLE IF NOT EXISTS virtual_balance (
            id INTEGER PRIMARY KEY,
            balance REAL,
            peak_balance REAL,
            total_trades INTEGER,
            total_wins INTEGER,
            total_losses INTEGER,
            updated_at TEXT
        );
    """)
    # Init balance kalau belum ada
    cur.execute("SELECT COUNT(*) FROM virtual_balance")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO virtual_balance VALUES (1, ?, ?, 0, 0, 0, ?)",
                   (VIRTUAL_BALANCE, VIRTUAL_BALANCE, datetime.now(WIB).isoformat()))
    conn.commit()
    conn.close()

def get_balance():
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()
    cur.execute("SELECT balance, peak_balance, total_trades, total_wins, total_losses FROM virtual_balance WHERE id=1")
    row = cur.fetchone()
    conn.close()
    return {"balance": row[0], "peak": row[1], "total": row[2], "wins": row[3], "losses": row[4]}

def add_virtual_trade(signal: dict):
    """Tambah trade virtual saat sinyal masuk"""
    init_db()
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()
    now = datetime.now(WIB).isoformat()
    cur.execute("""INSERT INTO virtual_trades
        (timestamp, symbol, signal, entry, sl, tp1, tp2, tp3, timeframe)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now, signal.get("symbol"), signal.get("signal"),
         signal.get("entry", 0), signal.get("sl", 0),
         signal.get("tp1", 0), signal.get("tp2", 0),
         signal.get("tp3", 0), signal.get("timeframe", "")))
    conn.commit()
    conn.close()

def close_virtual_trade(symbol: str, signal_type: str, exit_price: float, pnl_pct: float):
    """Tutup trade virtual dan update balance"""
    init_db()
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()

    # Ambil balance sekarang
    cur.execute("SELECT balance, peak_balance, total_trades, total_wins, total_losses FROM virtual_balance WHERE id=1")
    row = cur.fetchone()
    balance, peak, total, wins, losses = row

    # Hitung PnL dalam USD (risk 2% per trade)
    risk_usd = balance * 0.02
    pnl_usd = round(risk_usd * (pnl_pct / 100.0), 2)
    new_balance = round(balance + pnl_usd, 2)
    new_peak = max(peak, new_balance)
    result = "WIN" if pnl_pct > 0 else "LOSS"
    new_wins = wins + (1 if result == "WIN" else 0)
    new_losses = losses + (1 if result == "LOSS" else 0)
    now = datetime.now(WIB).isoformat()

    # Update trade
    cur.execute("""UPDATE virtual_trades SET
        exit_price=?, pnl_pct=?, pnl_usd=?, result=?, balance_after=?
        WHERE symbol=? AND signal=? AND exit_price IS NULL
        ORDER BY id DESC LIMIT 1""",
        (exit_price, pnl_pct, pnl_usd, result, new_balance, symbol, signal_type))

    # Update balance
    cur.execute("""UPDATE virtual_balance SET
        balance=?, peak_balance=?, total_trades=?, total_wins=?, total_losses=?, updated_at=?
        WHERE id=1""",
        (new_balance, new_peak, total+1, new_wins, new_losses, now))

    conn.commit()
    conn.close()
    return new_balance, pnl_usd

def get_summary():
    """Ringkasan performa virtual"""
    init_db()
    bal = get_balance()
    balance = bal["balance"]
    peak = bal["peak"]
    total = bal["total"]
    wins = bal["wins"]
    losses = bal["losses"]
    wr = round(100*wins/total, 1) if total else 0
    profit = round(balance - VIRTUAL_BALANCE, 2)
    profit_pct = round((balance - VIRTUAL_BALANCE) / VIRTUAL_BALANCE * 100, 2)
    drawdown = round((peak - balance) / peak * 100, 2) if peak > 0 else 0

    return {
        "balance": balance,
        "profit": profit,
        "profit_pct": profit_pct,
        "peak": peak,
        "drawdown": drawdown,
        "total": total,
        "wins": wins,
        "losses": losses,
        "wr": wr
    }

def send_virtual_summary(send_alert_fn):
    """Kirim ringkasan virtual trading ke Telegram"""
    s = get_summary()
    emoji = "📈" if s["profit"] >= 0 else "📉"
    msg = (
        f"{emoji} <b>Virtual Trading Update</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Balance  : ${s['balance']:.2f}\n"
        f"📊 Profit   : ${s['profit']:.2f} ({s['profit_pct']}%)\n"
        f"🏔️  Peak     : ${s['peak']:.2f}\n"
        f"📉 Drawdown : {s['drawdown']}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Total Trade: {s['total']}\n"
        f"✅ Menang   : {s['wins']}\n"
        f"❌ Kalah    : {s['losses']}\n"
        f"📈 Win Rate : {s['wr']}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Virtual Trading Bot"
    )
    send_alert_fn(msg)

if __name__ == "__main__":
    init_db()
    s = get_summary()
    print(f"Balance  : ${s['balance']:.2f}")
    print(f"Profit   : ${s['profit']:.2f} ({s['profit_pct']}%)")
    print(f"Win Rate : {s['wr']}%")
    print(f"Total    : {s['total']} trade")
