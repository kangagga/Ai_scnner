"""
Self-Learning — retrain XGBoost otomatis dengan model protection
"""
import json, logging, sqlite3, shutil
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

MODEL_DIR     = Path("model")
MODEL_PATH    = MODEL_DIR / "xgb_model.json"
MODEL_BACKUP  = MODEL_DIR / "xgb_model_backup.json"
META_PATH     = MODEL_DIR / "xgb_meta.json"
ANALYSIS_PATH = MODEL_DIR / "trade_analysis.json"

def should_retrain(retrain_every_n: int = 50) -> bool:
    meta     = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text())
    last_n   = meta.get("n_total", 0)

    conn     = sqlite3.connect("virtual_trading.db")
    current_n= conn.execute(
        "SELECT COUNT(*) FROM virtual_trades WHERE closed=1 AND result IN ('WIN','LOSS')"
    ).fetchone()[0]
    conn.close()

    # Hanya retrain dari data baru (smc_score > 0)
    conn     = sqlite3.connect("virtual_trading.db")
    new_n    = conn.execute(
        "SELECT COUNT(*) FROM virtual_trades WHERE closed=1 AND result IN ('WIN','LOSS') AND smc_score > 0"
    ).fetchone()[0]
    conn.close()

    new_trades = current_n - last_n
    logger.debug(f"[SELF-LEARN] {new_trades}/{retrain_every_n} trades baru | {new_n} trades dengan SMC features")
    return new_trades >= retrain_every_n and new_n >= 30

def get_current_auc() -> float:
    if not META_PATH.exists():
        return 0.0
    return json.loads(META_PATH.read_text()).get("auc", 0.0)

def retrain_with_protection() -> dict:
    """
    Retrain XGBoost dengan model protection:
    - Backup model lama
    - Train model baru
    - Bandingkan AUC
    - Rollback jika model baru lebih buruk
    """
    from xgb_trainer import XGBTrainer
    from trade_analyzer import analyze

    result = {
        "status"     : "skipped",
        "old_auc"    : 0.0,
        "new_auc"    : 0.0,
        "rolled_back": False,
        "message"    : "",
    }

    # Update trade analysis dulu
    logger.info("[SELF-LEARN] Update trade analysis...")
    try:
        analyze()
        logger.info("[SELF-LEARN] trade_analysis.json diupdate")
    except Exception as e:
        logger.warning(f"[SELF-LEARN] analyze() error: {e}")

    old_auc = get_current_auc()
    result["old_auc"] = old_auc

    # Backup model lama
    if MODEL_PATH.exists():
        shutil.copy2(MODEL_PATH, MODEL_BACKUP)
        logger.info(f"[SELF-LEARN] Backup model → {MODEL_BACKUP}")

    # Train model baru
    logger.info("[SELF-LEARN] Mulai retrain...")
    try:
        trainer  = XGBTrainer()
        meta     = trainer.train()

        if "error" in meta:
            result["status"]  = "error"
            result["message"] = meta["error"]
            # Restore backup
            if MODEL_BACKUP.exists():
                shutil.copy2(MODEL_BACKUP, MODEL_PATH)
            return result

        new_auc = meta.get("auc", 0.0)
        result["new_auc"] = new_auc
        result["status"]  = "trained"

        # Model protection — rollback jika AUC turun > 3%
        if old_auc > 0 and new_auc < old_auc - 0.03:
            logger.warning(
                f"[SELF-LEARN] AUC turun {old_auc:.3f}→{new_auc:.3f} — ROLLBACK!"
            )
            if MODEL_BACKUP.exists():
                shutil.copy2(MODEL_BACKUP, MODEL_PATH)
            result["rolled_back"] = True
            result["message"]     = f"Rollback: AUC {old_auc:.3f}→{new_auc:.3f}"
        else:
            delta = new_auc - old_auc
            result["message"] = (
                f"Model diupdate: AUC {old_auc:.3f}→{new_auc:.3f} ({delta:+.3f})"
            )
            logger.info(f"[SELF-LEARN] {result['message']}")

    except Exception as e:
        result["status"]  = "error"
        result["message"] = str(e)
        logger.error(f"[SELF-LEARN] Retrain error: {e}")
        if MODEL_BACKUP.exists():
            shutil.copy2(MODEL_BACKUP, MODEL_PATH)

    return result

def run_self_learning(retrain_every_n: int = 50) -> dict:
    """Entry point dari main.py"""
    if not should_retrain(retrain_every_n):
        return {"status": "skipped", "message": "Belum cukup trade baru"}
    return retrain_with_protection()
