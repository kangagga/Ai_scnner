# ============================================================
#  database.py — SQLite storage untuk sinyal & performa
# ============================================================
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = "signals.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT,
            symbol      TEXT,
            timeframe   TEXT,
            signal      TEXT,
            confidence  REAL,
            momentum    REAL,
            win_rate    REAL,
            entry       REAL,
            sl          REAL,
            tp1         REAL,
            tp2         REAL,
            tp3         REAL,
            rr_ratio    REAL,
            sent        INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS performance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT,
            symbol      TEXT,
            signal      TEXT,
            entry       REAL,
            exit_price  REAL,
            pnl_pct     REAL,
            result      TEXT
        );
    """)
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

def save_signal(s: dict):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO signals 
            (timestamp, symbol, timeframe, signal, confidence, momentum, 
             win_rate, entry, sl, tp1, tp2, tp3, rr_ratio, sent)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            datetime.now().isoformat(),
            s.get("symbol"), s.get("timeframe"), s.get("signal"),
            s.get("confidence"), s.get("momentum"), s.get("win_rate"),
            s.get("entry"), s.get("sl"), s.get("tp1"),
            s.get("tp2"), s.get("tp3"), s.get("rr_ratio"), 1
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"save_signal error: {e}")

def get_recent_signals(limit=50):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.warning(f"get_recent_signals error: {e}")
        return []

init_db()

def update_signal_result(symbol: str, signal: str, entry: float, exit_price: float):
    """Update hasil aktual sinyal — profit atau loss."""
    try:
        pnl = ((exit_price - entry) / entry * 100) if signal.startswith("BUY") else ((entry - exit_price) / entry * 100)
        result = "WIN" if pnl > 0 else "LOSS"
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO performance (timestamp, symbol, signal, entry, exit_price, pnl_pct, result)
            VALUES (?,?,?,?,?,?,?)
        """, (datetime.now().isoformat(), symbol, signal, entry, exit_price, round(pnl, 2), result))
        conn.commit()
        conn.close()
        logger.info(f"📊 Result saved: {symbol} {signal} PnL={pnl:.2f}% {result}")

        # Auto-blacklist kalau loss 3x berturut-turut
        from blacklist import report_false_signal
        if result == "LOSS":
            report_false_signal(symbol)

    except Exception as e:
        logger.warning(f"update_signal_result error: {e}")

def get_realtime_winrate(symbol: str = None) -> dict:
    """Hitung win rate aktual dari database."""
    try:
        conn = get_conn()
        c = conn.cursor()
        if symbol:
            c.execute("SELECT result FROM performance WHERE symbol=?", (symbol,))
        else:
            c.execute("SELECT result FROM performance")
        rows = c.fetchall()
        conn.close()
        if not rows:
            return {"total": 0, "win_rate": 0}
        total = len(rows)
        wins  = sum(1 for r in rows if r[0] == "WIN")
        return {"total": total, "win_rate": round(wins/total*100, 1)}
    except Exception as e:
        logger.warning(f"get_realtime_winrate error: {e}")
        return {"total": 0, "win_rate": 0}

def cleanup_old_data(days: int = 30):
    """Hapus data lama lebih dari N hari."""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM signals WHERE timestamp < datetime('now', ?)", (f'-{days} days',))
        c.execute("DELETE FROM performance WHERE timestamp < datetime('now', ?)", (f'-{days} days',))
        deleted = conn.total_changes
        conn.commit()
        conn.close()
        logger.info(f"🧹 Cleanup: {deleted} record lama dihapus")
    except Exception as e:
        logger.warning(f"cleanup error: {e}")
