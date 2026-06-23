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
    from sklearn.metrics import roc_auc_score, classification_report
    SKL_AVAILABLE = True
except ImportError:
    SKL_AVAILABLE = False

MODEL_DIR = Path("model")
MODEL_PATH = MODEL_DIR / "xgb_model.json"
FEATURE_PATH = MODEL_DIR / "feature_cols.txt"
META_PATH = MODEL_DIR / "xgb_meta.json"

FEATURE_COLS = [
    "side_num", "hour_of_day", "day_of_week",
    "timeframe_num", "risk_reward", "sl_pct", "tp1_pct",
]

def load_trades(db_path="virtual_trading.db", min_trades=50):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT * FROM virtual_trades WHERE closed=1 AND result IN ('WIN','LOSS')", conn)
    conn.close()
    if len(df) < min_trades:
        raise ValueError(f"Hanya {len(df)} trades. Butuh minimal {min_trades}.")
    print(f"[XGB] Loaded {len(df)} trades")
    df["label"] = (df["result"] == "WIN").astype(int)
    df["side_num"] = df["signal"].map({"BUY": 1, "SELL": -1}).fillna(0)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["hour_of_day"] = df["timestamp"].dt.hour.fillna(12)
    df["day_of_week"] = df["timestamp"].dt.dayofweek.fillna(0)
    tf_map = {"1m":0.016,"5m":0.083,"15m":0.25,"30m":0.5,"1h":1,"2h":2,"4h":4,"8h":8,"1d":24}
    df["timeframe_num"] = df["timeframe"].map(tf_map).fillna(1)
    df["entry"] = pd.to_numeric(df["entry"], errors="coerce")
    df["sl"] = pd.to_numeric(df["sl"], errors="coerce")
    df["tp1"] = pd.to_numeric(df["tp1"], errors="coerce")
    df["sl_pct"] = ((df["entry"]-df["sl"]).abs()/df["entry"]*100).fillna(0)
    df["tp1_pct"] = ((df["tp1"]-df["entry"]).abs()/df["entry"]*100).fillna(0)
    df["risk_reward"] = (df["tp1_pct"]/df["sl_pct"].replace(0,np.nan)).fillna(0).clip(0,10)
    df[FEATURE_COLS] = df[FEATURE_COLS].fillna(0).astype(float)
    return df

class XGBTrainer:
    def __init__(self, db_path="virtual_trading.db"):
        self.db_path = db_path
        self.model = None
        self.feature_cols = FEATURE_COLS
        MODEL_DIR.mkdir(exist_ok=True)

    def train(self):
        if not XGB_AVAILABLE or not SKL_AVAILABLE:
            raise ImportError("pip install xgboost scikit-learn")
        df = load_trades(self.db_path)
        X = df[self.feature_cols]
        y = df["label"]
        win_rate = y.mean()
        if len(df) < 80:
            X_train, X_test, y_train, y_test = X, X, y, y
        else:
            X_train,X_test,y_train,y_test = train_test_split(X,y,test_size=0.2,random_state=42,stratify=y)
        spw = (y_train==0).sum() / max((y_train==1).sum(), 1)
        model = xgb.XGBClassifier(
            objective="binary:logistic", eval_metric="auc",
            max_depth=3, n_estimators=80, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, scale_pos_weight=spw,
            tree_method="hist", device="cpu", verbosity=0, random_state=42)
        model.fit(X_train, y_train, eval_set=[(X_test,y_test)], verbose=False)
        y_prob = model.predict_proba(X_test)[:,1]
        auc = roc_auc_score(y_test, y_prob)
        report = classification_report(y_test,(y_prob>=0.5).astype(int),output_dict=True)
        metrics = {"auc":round(auc,4),"accuracy":round(report["accuracy"],4),
                   "win_rate_hist":round(float(win_rate),4),"n_total":len(df),
                   "trained_at":datetime.utcnow().isoformat()}
        fi = sorted(zip(self.feature_cols,model.feature_importances_),key=lambda x:x[1],reverse=True)
        metrics["feature_importance"] = fi
        print(f"[XGB] AUC={auc:.4f} Acc={metrics['accuracy']:.2%} WinRate={win_rate:.1%}")
        print(f"[XGB] Features: {fi}")
        self.model = model
        model.save_model(str(MODEL_PATH))
        FEATURE_PATH.write_text("\n".join(self.feature_cols))
        META_PATH.write_text(json.dumps(metrics, indent=2, default=str))
        print(f"[XGB] Saved → {MODEL_PATH}")
        return metrics

    def load(self):
        if not XGB_AVAILABLE or not MODEL_PATH.exists():
            return False
        self.model = xgb.XGBClassifier()
        self.model.load_model(str(MODEL_PATH))
        if FEATURE_PATH.exists():
            self.feature_cols = FEATURE_PATH.read_text().strip().split("\n")
        print("[XGB] Model loaded")
        return True

    def predict(self, features):
        if self.model is None:
            if not self.load(): return 0.5
        row = {col: float(features.get(col,0.0)) for col in self.feature_cols}
        X = pd.DataFrame([row])[self.feature_cols]
        return round(float(self.model.predict_proba(X)[0][1]),4)

    def should_entry(self, signal, timeframe, entry, sl, tp1, hour=None, min_win_prob=0.52):
        if hour is None: hour = datetime.utcnow().hour
        sl_pct = abs(entry-sl)/entry*100
        tp1_pct = abs(tp1-entry)/entry*100
        rr = (tp1_pct/sl_pct) if sl_pct>0 else 0
        tf_map = {"1m":0.016,"5m":0.083,"15m":0.25,"30m":0.5,"1h":1,"2h":2,"4h":4,"8h":8,"1d":24}
        features = {"side_num":1 if signal=="BUY" else -1,"hour_of_day":hour,
                    "day_of_week":datetime.utcnow().weekday(),
                    "timeframe_num":tf_map.get(timeframe,1),
                    "risk_reward":min(rr,10),"sl_pct":sl_pct,"tp1_pct":tp1_pct}
        win_prob = self.predict(features)
        ok = win_prob >= min_win_prob
        return ok, win_prob, ("OK" if ok else f"win_prob {win_prob:.2f} < {min_win_prob}")

def maybe_retrain(db_path="virtual_trading.db", retrain_every_n=20):
    meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
    last_n = meta.get("n_total", 0)
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT COUNT(*) FROM virtual_trades WHERE closed=1 AND result IN ('WIN','LOSS')")
    current_n = cur.fetchone()[0]
    conn.close()
    if current_n - last_n >= retrain_every_n:
        print(f"[XGB] Retrain ({current_n-last_n} trades baru)")
        t = XGBTrainer(db_path); t.train(); return True
    return False

def xgb_telegram_line(win_prob, entry_ok):
    icon = "🤖✅" if entry_ok else "🤖❌"
    bar = "█"*int(win_prob*10) + "░"*(10-int(win_prob*10))
    return f"{icon} <b>XGB</b>: {win_prob:.0%} [{bar}]"

_instance = None
def get_trainer(db_path="virtual_trading.db"):
    global _instance
    if _instance is None:
        _instance = XGBTrainer(db_path)
        _instance.load()
    return _instance