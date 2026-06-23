"""
XGBoost Trainer — 16 fitur dari kolom baru virtual_trades
"""
import sqlite3, json, logging, numpy as np, pandas as pd
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
    from sklearn.utils.class_weight import compute_sample_weight
    SKL_AVAILABLE = True
except ImportError:
    SKL_AVAILABLE = False

MODEL_DIR    = Path("model")
MODEL_PATH   = MODEL_DIR / "xgb_model.json"
FEATURE_PATH = MODEL_DIR / "feature_cols.txt"
META_PATH    = MODEL_DIR / "xgb_meta.json"

FEATURE_COLS = [
    "side_num", "hour_of_day", "day_of_week", "timeframe_num",
    "risk_reward", "sl_pct", "tp1_pct",
    "smc_score", "smc_bonus",
    "ob_imbalance", "ob_bonus",
    "vp_ratio", "vp_bonus",
    "liq_score", "liq_adj",
    "price_vs_vwap",
]

def load_trades(db_path="virtual_trading.db", min_trades=50):
    conn = sqlite3.connect(db_path)
    df   = pd.read_sql_query(
        "SELECT * FROM virtual_trades WHERE closed=1 AND result IN ('WIN','LOSS')",
        conn
    )
    conn.close()

    if len(df) < min_trades:
        raise ValueError(f"Hanya {len(df)} trades. Butuh minimal {min_trades}.")

    logger.info(f"[XGB] Loaded {len(df)} trades")
    df["label"]    = (df["result"] == "WIN").astype(int)
    df["side_num"] = df["signal"].map({"BUY": 1, "SELL": -1}).fillna(0)

    df["timestamp"]   = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["hour_of_day"] = df["timestamp"].dt.hour.fillna(12)
    df["day_of_week"] = df["timestamp"].dt.dayofweek.fillna(0)

    tf_map = {"1m":0.016,"5m":0.083,"15m":0.25,"30m":0.5,
              "1h":1,"2h":2,"4h":4,"8h":8,"1d":24}
    df["timeframe_num"] = df["timeframe"].map(tf_map).fillna(1)

    for col in ["entry","sl","tp1","pnl_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["sl_pct"]  = ((df["entry"]-df["sl"]).abs()/df["entry"]*100).fillna(0)
    df["tp1_pct"] = ((df["tp1"]-df["entry"]).abs()/df["entry"]*100).fillna(0)
    df["risk_reward"] = (df["tp1_pct"]/df["sl_pct"].replace(0,np.nan)).fillna(0).clip(0,10)

    # Kolom baru — fill 0 jika belum ada (trades lama)
    new_cols = ["smc_score","smc_bonus","ob_imbalance","ob_bonus",
                "vp_ratio","vp_bonus","liq_score","liq_adj","price_vs_vwap"]
    for col in new_cols:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df

class XGBTrainer:
    def __init__(self):
        MODEL_DIR.mkdir(exist_ok=True)

    def train(self, db_path="virtual_trading.db") -> dict:
        if not XGB_AVAILABLE or not SKL_AVAILABLE:
            return {"error": "xgboost/sklearn tidak tersedia"}

        try:
            df = load_trades(db_path)
        except ValueError as e:
            return {"error": str(e)}

        # Filter trades lama (sebelum kolom baru) — smc_score=0 semua = data lama
        new_data = df[df["smc_score"] > 0]
        if len(new_data) >= 30:
            df = new_data
            logger.info(f"[XGB] Pakai {len(df)} trades baru (dengan SMC features)")
        else:
            logger.info(f"[XGB] Pakai semua {len(df)} trades (data baru belum cukup)")

        X = df[FEATURE_COLS].values
        y = df["label"].values

        # Handle imbalance
        win_rate = y.mean()
        weights  = compute_sample_weight("balanced", y)
        logger.info(f"[XGB] Win rate: {win_rate:.1%} | Features: {len(FEATURE_COLS)}")

        X_train, X_test, y_train, y_test, w_train, _ = train_test_split(
            X, y, weights, test_size=0.2, random_state=42, stratify=y
        )

        model = xgb.XGBClassifier(
            n_estimators    = 200,
            max_depth       = 4,
            learning_rate   = 0.05,
            subsample       = 0.8,
            colsample_bytree= 0.8,
            min_child_weight= 3,
            reg_alpha       = 0.1,
            reg_lambda      = 1.0,
            use_label_encoder=False,
            eval_metric     = "logloss",
            random_state    = 42,
        )
        model.fit(X_train, y_train, sample_weight=w_train,
                  eval_set=[(X_test, y_test)], verbose=False)

        y_prob = model.predict_proba(X_test)[:, 1]
        auc    = roc_auc_score(y_test, y_prob)
        logger.info(f"[XGB] AUC: {auc:.3f}")

        # Simpan model + metadata
        model.save_model(str(MODEL_PATH))
        FEATURE_PATH.write_text("\n".join(FEATURE_COLS))

        meta = {
            "trained_at" : datetime.now().isoformat(),
            "n_total"    : len(df),
            "n_train"    : len(X_train),
            "n_test"     : len(X_test),
            "auc"        : round(auc, 4),
            "win_rate"   : round(float(win_rate), 4),
            "features"   : FEATURE_COLS,
        }
        META_PATH.write_text(json.dumps(meta, indent=2))
        logger.info(f"[XGB] Model disimpan → {MODEL_PATH}")

        return meta

    def predict(self, features: dict) -> float:
        """Return win probability 0-1 untuk satu sinyal"""
        if not XGB_AVAILABLE or not MODEL_PATH.exists():
            return 0.5

        try:
            model = xgb.XGBClassifier()
            model.load_model(str(MODEL_PATH))
            vals = [features.get(c, 0) for c in FEATURE_COLS]
            X    = np.array([vals])
            prob = model.predict_proba(X)[0][1]
            return round(float(prob), 4)
        except Exception as e:
            logger.error(f"[XGB] Predict error: {e}")
            return 0.5

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    trainer = XGBTrainer()
    result  = trainer.train()
    print(json.dumps(result, indent=2))
