
import sqlite3, json, os
from datetime import datetime, timedelta, timezone
import logging
logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
VIRTUAL_DB = "/home/userland/ai-scanner/virtual_trading.db"
VIRTUAL_BALANCE = 1000.0  # Balance awal $1000

def is_duplicate_position(symbol, timeframe, signal):
    """Cek apakah sudah ada posisi terbuka untuk pair+timeframe+signal (read-only, tidak insert)."""
    try:
        conn = sqlite3.connect(VIRTUAL_DB)
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM virtual_trades
            WHERE symbol=? AND timeframe=? AND signal=? AND closed=0
            LIMIT 1
        """, (symbol, timeframe, signal))
        result = cur.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        logger.warning(f"[is_duplicate_position] Error cek {symbol}: {e}")
        return False


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
    
    symbol = signal.get("symbol")
    timeframe = signal.get("timeframe")
    sig_type = signal.get("signal")
    
    # === FILTER DUPLIKASI ===
    # Cek apakah sudah ada posisi terbuka untuk pair+timeframe+signal yang sama
    cur.execute("""
        SELECT id FROM virtual_trades
        WHERE symbol=? AND timeframe=? AND signal=? AND closed=0
        LIMIT 1
    """, (symbol, timeframe, sig_type))
    if cur.fetchone():
        logger.info(f"[DUPLICATE] {symbol}/{timeframe} {sig_type} sudah ada posisi terbuka, skip")
        conn.close()
        return
    
    now = datetime.now(WIB).isoformat()
    cur.execute("""INSERT INTO virtual_trades
        (timestamp, symbol, signal, entry, sl, tp1, tp2, tp3, timeframe)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now, symbol, sig_type,
         signal.get("entry", 0), signal.get("sl", 0),
         signal.get("tp1", 0), signal.get("tp2", 0),
         signal.get("tp3", 0), timeframe))
    conn.commit()
    conn.close()

    # Sinkronisasi ke risk_manager supaya /status di Telegram akurat
    try:
        from risk_manager import open_position
        open_position(
            symbol=symbol,
            timeframe=timeframe,
            signal=sig_type,
            risk_pct=2.0,
        )
    except Exception as e:
        logger.warning(f"[RISK_SYNC] Gagal open_position: {e}")

def close_virtual_trade(symbol: str, timeframe: str, signal: str, pnl_pct: float):
    """Tutup trade virtual & catat hasil"""
    init_db()
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()
    now = datetime.now(WIB).isoformat()
    
    # Ambil trade yang masih open
    cur.execute("""
        SELECT id, entry FROM virtual_trades
        WHERE symbol=? AND timeframe=? AND signal=? AND closed=0
        ORDER BY timestamp DESC LIMIT 1
    """, (symbol, timeframe, signal))
    row = cur.fetchone()
    
    if not row:
        logger.warning(f"No open trade found for {symbol}/{timeframe}/{signal}")
        conn.close()
        return
    
    trade_id, entry = row
    
    # Hitung pnl_usdt (asumsi $25 per virtual trade)
    trade_amount = 25.0
    pnl_usdt = trade_amount * pnl_pct / 100.0
    
    # Exit price
    if pnl_pct >= 0:
        exit_price = entry * (1 + pnl_pct / 100)
    else:
        exit_price = entry * (1 + pnl_pct / 100)
    
    result = "WIN" if pnl_pct > 0 else "LOSS"
    cur.execute("""
        UPDATE virtual_trades SET
            closed=1, exit_price=?, pnl_pct=?, pnl_usd=?, pnl_usdt=?, result=?,
            closed_at=?
        WHERE id=?
        """, (exit_price, pnl_pct, pnl_usdt, pnl_usdt, result, now, trade_id))
    
    conn.commit()
    conn.close()
    
    status = "WIN" if pnl_pct > 0 else "LOSS"
    logger.info(
        f"Trade closed: {symbol}/{timeframe} {signal} | "
        f"{status} | PnL: {pnl_pct:.2f}% / ${pnl_usdt:.2f}"
    )
    
    # Sinkronisasi ke risk_manager untuk update balance & win rate
    try:
        from risk_manager import record_trade_result
        win = pnl_pct > 0
        record_trade_result(
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            pnl_usdt=pnl_usdt,
            win=win
        )
        logger.info(f"[RISK_SYNC] record_trade_result OK: {symbol} win={win}")
    except Exception as e:
        logger.warning(f"[RISK_SYNC] Gagal record_trade_result: {e}")
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
