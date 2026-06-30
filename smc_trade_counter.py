"""
smc_trade_counter.py — counter SMC trades + trigger XGBoost retrain
Trigger retrain otomatis setiap 50 SMC trades.
"""
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH               = "signals.db"
SMC_RETRAIN_THRESHOLD = 50


class SMCTradeCounter:
    def __init__(self, db_path=DB_PATH, threshold=SMC_RETRAIN_THRESHOLD):
        self.db_path   = db_path
        self.threshold = threshold
        self._lock     = threading.Lock()
        self._init_db()

    def _init_db(self):
        con = sqlite3.connect(self.db_path)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS smc_counter (
                id          INTEGER PRIMARY KEY,
                symbol      TEXT,
                timeframe   TEXT,
                signal_type TEXT,
                smc_score   REAL,
                ts          TEXT
            );
            CREATE TABLE IF NOT EXISTS smc_retrain_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                triggered_at TEXT,
                smc_count    INTEGER,
                status       TEXT
            );
        """)
        con.commit()
        con.close()

    def get_smc_count(self) -> int:
        try:
            con = sqlite3.connect(self.db_path)
            last = con.execute(
                "SELECT triggered_at FROM smc_retrain_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last:
                count = con.execute(
                    "SELECT COUNT(*) FROM smc_counter WHERE ts > ?", (last[0],)
                ).fetchone()[0]
            else:
                count = con.execute(
                    "SELECT COUNT(*) FROM smc_counter"
                ).fetchone()[0]
            con.close()
            return count
        except Exception as e:
            logger.warning(f"[SMC_COUNTER] get_count error: {e}")
            return 0

    def record_trade(self, symbol, timeframe="", signal_type="",
                     smc_score=0, has_smc=True) -> Optional[int]:
        if not has_smc:
            return None
        ts = datetime.utcnow().isoformat()
        try:
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT INTO smc_counter (symbol,timeframe,signal_type,smc_score,ts) "
                "VALUES (?,?,?,?,?)",
                (symbol, timeframe, signal_type, smc_score, ts),
            )
            con.commit()
            con.close()
        except Exception as e:
            logger.warning(f"[SMC_COUNTER] record error: {e}")
            return None

        count = self.get_smc_count()
        logger.info(f"[SMC_COUNTER] {symbol} SMC trade #{count}/{self.threshold}")
        if count >= self.threshold:
            self._trigger_retrain(count)
        return count

    def _trigger_retrain(self, count):
        with self._lock:
            try:
                con  = sqlite3.connect(self.db_path)
                last = con.execute(
                    "SELECT triggered_at FROM smc_retrain_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
                con.close()
                if last:
                    from datetime import timedelta
                    last_dt = datetime.fromisoformat(last[0])
                    if (datetime.utcnow() - last_dt).total_seconds() < 600:
                        logger.info("[SMC_COUNTER] Retrain skipped — baru triggered")
                        return
            except Exception:
                pass

            logger.warning(
                f"[SMC_COUNTER] 🚀 {count}/{self.threshold} tercapai — trigger retrain!"
            )
            self._log_retrain(count, "TRIGGERED")
            threading.Thread(target=self._run_retrain, daemon=True).start()

    def _run_retrain(self):
        try:
            from xgb_trainer import XGBTrainer
            result = XGBTrainer().retrain()
            auc    = result.get("auc", 0) if isinstance(result, dict) else 0
            logger.info(f"[SMC_COUNTER] ✅ Retrain selesai — AUC: {auc:.4f}")
            self._log_retrain(self.get_smc_count(), f"DONE auc={auc:.4f}")
        except Exception as e:
            logger.error(f"[SMC_COUNTER] ❌ Retrain gagal: {e}")
            self._log_retrain(0, f"ERROR: {e}")

    def _log_retrain(self, count, status):
        try:
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT INTO smc_retrain_log (triggered_at,smc_count,status) VALUES (?,?,?)",
                (datetime.utcnow().isoformat(), count, status),
            )
            con.commit()
            con.close()
        except Exception as e:
            logger.warning(f"[SMC_COUNTER] log error: {e}")

    def get_status(self) -> dict:
        count = self.get_smc_count()
        try:
            con      = sqlite3.connect(self.db_path)
            total    = con.execute("SELECT COUNT(*) FROM smc_counter").fetchone()[0]
            last_ret = con.execute(
                "SELECT triggered_at, status FROM smc_retrain_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            con.close()
        except Exception:
            total, last_ret = 0, None
        return {
            "smc_trades_since_retrain": count,
            "threshold"               : self.threshold,
            "progress_pct"            : round(count / self.threshold * 100, 1),
            "total_smc_trades"        : total,
            "last_retrain"            : last_ret[0] if last_ret else "Never",
            "last_retrain_status"     : last_ret[1] if last_ret else "N/A",
            "next_retrain_at"         : self.threshold - count,
        }


_instance: Optional[SMCTradeCounter] = None

def get_smc_counter() -> SMCTradeCounter:
    global _instance
    if _instance is None:
        _instance = SMCTradeCounter()
    return _instance
