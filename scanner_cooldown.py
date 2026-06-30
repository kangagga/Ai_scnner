"""
scanner/cooldown.py — cooldown state + SQLite persist
"""
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

DB_PATH = "signals.db"

SIGNAL_COOLDOWN: Dict[str, int] = {
    "BUY (SETUP)"    : 60,
    "SELL (SETUP)"   : 60,
    "BUY"            : 45,
    "SELL"           : 45,
    "BUY (REVERSAL)" : 30,
    "SELL (REVERSAL)": 30,
}
DEFAULT_COOLDOWN_MINUTES = 45

_state: Dict[str, Tuple] = {}
_lock  = threading.Lock()


def init_db() -> None:
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS signal_cooldown (
                key         TEXT PRIMARY KEY,
                signal_type TEXT,
                last_time   TEXT
            )
        """)
        con.commit()
        con.close()
    except Exception as e:
        logger.warning(f"[COOLDOWN] init gagal: {e}")


def load_state() -> None:
    try:
        con  = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT key, signal_type, last_time FROM signal_cooldown"
        ).fetchall()
        con.close()
        loaded = {}
        for key, sig_type, last_time_str in rows:
            try:
                loaded[key] = (sig_type, datetime.fromisoformat(last_time_str))
            except Exception:
                continue
        with _lock:
            _state.update(loaded)
        logger.info(f"[COOLDOWN] Loaded {len(loaded)} entries")
    except Exception as e:
        logger.warning(f"[COOLDOWN] load gagal: {e}")


def _save(key: str, signal_type: str, last_time: datetime) -> None:
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO signal_cooldown (key, signal_type, last_time) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "signal_type=excluded.signal_type, last_time=excluded.last_time",
            (key, signal_type, last_time.isoformat()),
        )
        con.commit()
        con.close()
    except Exception as e:
        logger.warning(f"[COOLDOWN] save gagal: {e}")


def is_duplicate(symbol: str, timeframe: str, signal_type: str, confidence: float = 0) -> bool:
    # Normalize signal direction untuk key (BUY (SETUP) → BUY, SELL (REVERSAL) → SELL)
    _dir = "BUY" if "BUY" in signal_type.upper() else "SELL"
    key  = f"{symbol}_{timeframe}_{_dir}"
    now      = datetime.now()
    cooldown = SIGNAL_COOLDOWN.get(signal_type, DEFAULT_COOLDOWN_MINUTES)
    with _lock:
        state = _state.get(key)
        if state is None:
            _state[key] = (signal_type, now)
            _save(key, signal_type, now)
            return False
        prev_type, last_time = state
        delta = (now - last_time).total_seconds() / 60.0
        if delta < cooldown:
            logger.debug(f"[COOLDOWN] {key} SKIP {delta:.1f}/{cooldown}m")
            return True
        _state[key] = (signal_type, now)
        _save(key, signal_type, now)
        return False


def reset(symbol: str, timeframe: str) -> None:
    key = f"{symbol}_{timeframe}"
    with _lock:
        _state.pop(key, None)
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("DELETE FROM signal_cooldown WHERE key=?", (key,))
        con.commit()
        con.close()
    except Exception as e:
        logger.warning(f"[COOLDOWN] reset gagal: {e}")


def get_state_snapshot() -> dict:
    with _lock:
        return {k: (v[0], v[1].isoformat()) for k, v in _state.items()}


init_db()
load_state()
