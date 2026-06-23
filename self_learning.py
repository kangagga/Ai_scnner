import json
import logging
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

MODEL_DIR = Path("model")
MODEL_PATH = MODEL_DIR / "xgb_model.json"
MODEL_BACKUP = MODEL_DIR / "xgb_model_backup.json"
META_PATH = MODEL_DIR / "xgb_meta.json"
ANALYSIS_PATH = MODEL_DIR / "trade_analysis.json"

def should_retrain(retrain_every_n: int = 20) -> bool:
    meta = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text())
    last_n = meta.get("n_total", 0)

    conn = sqlite3.connect("virtual_trading.db")
    cur = conn.execute(
        "SELECT COUNT(*) FROM virtual_trades WHERE closed=1 AND result IN ('WIN','LOSS')"
    )
    current_n = cur.fetchone()[0]
    conn.close()

    new_trades = current_n - last_n
    logger.debug(f"[SELF-LEARN] {new_trades}/{retrain_every_n} trades baru")
    return new_trades >= retrain_every_n

def get_current_auc() -> float:
    if not META_PATH.exists():
        return 0.0
    meta = json.loads(META_PATH.read_text())
    return meta.get("auc", 0.0)

def retrain_with_protection() -> dict:
    """
    Retrain XGBoost. Jika model baru lebih buruk, rollback ke model lama.
    Return: dict hasil retrain
    """
    from xgb_trainer import XGBTrainer
    from trade_analyzer import analyze

    # Update trade analysis dulu
    logger.info("[SELF-LEARN] Update trade analysis...")
    try:
        analyze()
        logger.info("[SELF-LEARN] Trade analysis updated")
    except Exception as e:
        logger.warning(f"[SELF-LEARN] analyze error: {e}")

    # Backup model lama
    old_auc = get_current_auc()
    if MODEL_PATH.exists():
        shutil.copy(MODEL_PATH, MODEL_BACKUP)
        logger.info(f"[SELF-LEARN] Backup model lama (AUC={old_auc:.4f})")

    # Train model baru
    try:
        trainer = XGBTrainer("virtual_trading.db")
        metrics = trainer.train()
        new_auc = metrics.get("auc", 0.0)

        logger.info(f"[SELF-LEARN] Model baru AUC={new_auc:.4f} vs lama={old_auc:.4f}")

        # Proteksi — rollback jika model baru lebih buruk
        if old_auc > 0 and new_auc < old_auc - 0.02:
            logger.warning(
                f"[SELF-LEARN] Model baru lebih buruk ({new_auc:.4f} < {old_auc:.4f}), ROLLBACK!"
            )
            if MODEL_BACKUP.exists():
                shutil.copy(MODEL_BACKUP, MODEL_PATH)
            metrics["rolled_back"] = True
            metrics["reason"] = f"new AUC {new_auc:.4f} < old {old_auc:.4f}"
        else:
            metrics["rolled_back"] = False
            logger.info(f"[SELF-LEARN] Model baru diterima ✅")

        # Reload singleton
        try:
            import xgb_trainer as _xt
            _xt._instance = None
            logger.info("[SELF-LEARN] XGB singleton reset, akan reload saat dipakai")
        except Exception:
            pass

        return metrics

    except Exception as e:
        logger.error(f"[SELF-LEARN] Retrain error: {e}")
        if MODEL_BACKUP.exists():
            shutil.copy(MODEL_BACKUP, MODEL_PATH)
            logger.info("[SELF-LEARN] Rollback ke backup karena error")
        return {"error": str(e), "rolled_back": True}


def run_self_learning(retrain_every_n: int = 20):
    """
    Entry point utama — panggil ini dari main.py setiap N trade.
    """
    if not should_retrain(retrain_every_n):
        return False

    logger.info(f"[SELF-LEARN] Trigger retrain setelah {retrain_every_n} trade baru")
    result = retrain_with_protection()

    rolled = result.get("rolled_back", False)
    auc = result.get("auc", 0.0)
    status = "⚠️ ROLLBACK" if rolled else "✅ OK"
    logger.info(f"[SELF-LEARN] Selesai — {status} | AUC={auc:.4f}")
    return True