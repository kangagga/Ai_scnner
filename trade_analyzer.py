import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

DB_PATH = "virtual_trading.db"

def load_trades():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM virtual_trades WHERE closed=1 AND result IN ('WIN','LOSS')",
        conn
    )
    conn.close()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["hour"] = df["timestamp"].dt.hour
    df["label"] = (df["result"] == "WIN").astype(int)
    df["entry"] = pd.to_numeric(df["entry"], errors="coerce")
    df["sl"] = pd.to_numeric(df["sl"], errors="coerce")
    df["tp1"] = pd.to_numeric(df["tp1"], errors="coerce")
    df["pnl_pct"] = pd.to_numeric(df["pnl_pct"], errors="coerce").fillna(0)
    df["sl_pct"] = ((df["entry"] - df["sl"]).abs() / df["entry"] * 100).fillna(0)
    df["tp1_pct"] = ((df["tp1"] - df["entry"]).abs() / df["entry"] * 100).fillna(0)
    df["rr"] = (df["tp1_pct"] / df["sl_pct"].replace(0, np.nan)).fillna(0).clip(0, 10)
    return df

def win_rate(df):
    if len(df) == 0: return 0.0
    return round(df["label"].mean() * 100, 1)

def profit_factor(df):
    wins = df[df["label"]==1]["pnl_pct"].sum()
    losses = df[df["label"]==0]["pnl_pct"].abs().sum()
    return round(wins / losses, 2) if losses > 0 else 0.0

def avg_rr(df):
    return round(df["rr"].mean(), 2)

def max_drawdown(df):
    cumulative = df["pnl_pct"].cumsum()
    peak = cumulative.cummax()
    dd = (cumulative - peak)
    return round(dd.min(), 2)

def session_label(hour):
    if 0 <= hour < 8:   return "ASIA"
    if 8 <= hour < 16:  return "EUROPE"
    return "US"

def analyze():
    df = load_trades()
    if len(df) < 10:
        print("Data belum cukup (min 10 trades)")
        return {}

    df["session"] = df["hour"].apply(session_label)

    result = {}

    # 1. Overall
    result["overall"] = {
        "total": len(df),
        "win_rate": win_rate(df),
        "profit_factor": profit_factor(df),
        "avg_rr": avg_rr(df),
        "max_drawdown": max_drawdown(df),
    }

    # 2. Per pair
    pair_stats = {}
    for sym, g in df.groupby("symbol"):
        if len(g) < 3: continue
        pair_stats[sym] = {
            "total": len(g),
            "win_rate": win_rate(g),
            "profit_factor": profit_factor(g),
            "avg_rr": avg_rr(g),
        }
    result["per_pair"] = pair_stats

    # 3. Per signal (BUY/SELL)
    sig_stats = {}
    for sig, g in df.groupby("signal"):
        sig_stats[sig] = {
            "total": len(g),
            "win_rate": win_rate(g),
            "profit_factor": profit_factor(g),
        }
    result["per_signal"] = sig_stats

    # 4. Per session
    sess_stats = {}
    for sess, g in df.groupby("session"):
        sess_stats[sess] = {
            "total": len(g),
            "win_rate": win_rate(g),
            "profit_factor": profit_factor(g),
        }
    result["per_session"] = sess_stats

    # 5. Per jam
    hour_stats = {}
    for h, g in df.groupby("hour"):
        hour_stats[int(h)] = {
            "total": len(g),
            "win_rate": win_rate(g),
        }
    result["per_hour"] = hour_stats

    # 6. Per timeframe
    tf_stats = {}
    for tf, g in df.groupby("timeframe"):
        tf_stats[tf] = {
            "total": len(g),
            "win_rate": win_rate(g),
            "profit_factor": profit_factor(g),
        }
    result["per_timeframe"] = tf_stats

    # 7. Best/worst pair
    pair_df = pd.DataFrame(pair_stats).T
    if len(pair_df) > 0:
        pair_df["win_rate"] = pd.to_numeric(pair_df["win_rate"])
        result["best_pairs"] = pair_df.nlargest(3, "win_rate")["win_rate"].to_dict()
        result["worst_pairs"] = pair_df.nsmallest(3, "win_rate")["win_rate"].to_dict()

    # 8. Dynamic penalty rules
    penalties = []
    for (sig, sess), g in df.groupby(["signal", "session"]):
        if len(g) < 5: continue
        wr = win_rate(g)
        if wr < 35:
            penalties.append({
                "signal": sig,
                "session": sess,
                "win_rate": wr,
                "penalty": -15,
                "reason": f"{sig}+{sess} WR={wr}%<35%"
            })
        elif wr < 45:
            penalties.append({
                "signal": sig,
                "session": sess,
                "win_rate": wr,
                "penalty": -8,
                "reason": f"{sig}+{sess} WR={wr}%<45%"
            })
    result["penalty_rules"] = penalties

    # Simpan ke JSON
    Path("model").mkdir(exist_ok=True)
    with open("model/trade_analysis.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    return result

def print_report(result):
    o = result.get("overall", {})
    print("=" * 50)
    print("TRADE ANALYSIS REPORT")
    print("=" * 50)
    print(f"Total Trades  : {o.get('total')}")
    print(f"Win Rate      : {o.get('win_rate')}%")
    print(f"Profit Factor : {o.get('profit_factor')}")
    print(f"Avg R:R       : {o.get('avg_rr')}")
    print(f"Max Drawdown  : {o.get('max_drawdown')}%")

    print("\n--- Per Signal ---")
    for k, v in result.get("per_signal", {}).items():
        print(f"  {k}: WR={v['win_rate']}% ({v['total']} trades) PF={v['profit_factor']}")

    print("\n--- Per Session ---")
    for k, v in result.get("per_session", {}).items():
        print(f"  {k}: WR={v['win_rate']}% ({v['total']} trades)")

    print("\n--- Per Timeframe ---")
    for k, v in result.get("per_timeframe", {}).items():
        print(f"  {k}: WR={v['win_rate']}% ({v['total']} trades)")

    print("\n--- Best Pairs ---")
    for k, v in result.get("best_pairs", {}).items():
        print(f"  {k}: {v}%")

    print("\n--- Worst Pairs ---")
    for k, v in result.get("worst_pairs", {}).items():
        print(f"  {k}: {v}%")

    print("\n--- Dynamic Penalty Rules ---")
    rules = result.get("penalty_rules", [])
    if rules:
        for r in rules:
            print(f"  {r['reason']} → penalty {r['penalty']}")
    else:
        print("  Belum ada rule (butuh lebih banyak data per kombinasi)")

if __name__ == "__main__":
    result = analyze()
    print_report(result)