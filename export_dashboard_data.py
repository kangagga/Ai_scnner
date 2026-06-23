#!/usr/bin/env python3
"""
export_dashboard_data.py — Export data trading bot ke satu file JSON
ringkas untuk dipakai di dashboard artifact (paste isinya ke chat Claude).
"""
import sqlite3
import json
import os
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def safe_round(v, n=4):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return 0


def export_virtual_trades(db_path="virtual_trading.db"):
    if not os.path.exists(db_path):
        return {"trades": [], "balance": {}}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, timestamp, symbol, signal, entry, sl, tp1, tp2, tp3,
               exit_price, pnl_pct, pnl_usd, result, balance_after,
               timeframe, closed
        FROM virtual_trades
        ORDER BY timestamp ASC
    """)
    trades = []
    for row in cur.fetchall():
        d = dict(row)
        trades.append({
            "id": d["id"],
            "timestamp": d["timestamp"],
            "symbol": d["symbol"],
            "signal": d["signal"],
            "entry": safe_round(d["entry"], 8),
            "sl": safe_round(d["sl"], 8),
            "tp1": safe_round(d["tp1"], 8),
            "tp2": safe_round(d["tp2"], 8),
            "tp3": safe_round(d["tp3"], 8),
            "exit_price": safe_round(d["exit_price"], 8),
            "pnl_pct": safe_round(d["pnl_pct"], 2),
            "pnl_usd": safe_round(d["pnl_usd"], 2),
            "result": d["result"] or "",
            "timeframe": d["timeframe"] or "1h",
            "closed": bool(d["closed"]),
        })
    cur.execute("SELECT * FROM virtual_balance ORDER BY id DESC LIMIT 1")
    bal_row = cur.fetchone()
    balance = dict(bal_row) if bal_row else {}
    conn.close()
    return {"trades": trades, "balance": balance}


def export_signals(db_path="signals.db", limit=300):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, symbol, timeframe, signal, confidence,
               win_rate, entry, sl, tp1, tp2, tp3, rr_ratio
        FROM signals
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def export_performance(db_path="signals.db"):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT timestamp, symbol, signal, entry, exit_price, pnl_pct, result
            FROM performance
            ORDER BY timestamp DESC
            LIMIT 300
        """)
        rows = [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return rows


def export_risk_state(path="risk_state.json"):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def compute_summary(trades):
    closed = [t for t in trades if t["closed"]]
    wins = [t for t in closed if t["pnl_pct"] > 0]
    losses = [t for t in closed if t["pnl_pct"] < 0]
    breakeven = [t for t in closed if t["pnl_pct"] == 0]

    total_pnl_pct = sum(t["pnl_pct"] for t in closed)
    total_pnl_usd = sum(t["pnl_usd"] for t in closed)

    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0
    avg_win = round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0

    by_symbol = {}
    for t in closed:
        sym = t["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "wins": 0, "losses": 0, "pnl_pct": 0.0}
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["pnl_pct"] += t["pnl_pct"]
        if t["pnl_pct"] > 0:
            by_symbol[sym]["wins"] += 1
        elif t["pnl_pct"] < 0:
            by_symbol[sym]["losses"] += 1
    for sym in by_symbol:
        by_symbol[sym]["pnl_pct"] = round(by_symbol[sym]["pnl_pct"], 2)

    return {
        "total_trades": len(closed),
        "open_trades": len(trades) - len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": win_rate,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "total_pnl_pct": round(total_pnl_pct, 2),
        "total_pnl_usd": round(total_pnl_usd, 2),
        "by_symbol": by_symbol,
    }


def main():
    os.chdir(BASE_DIR)
    vt_data = export_virtual_trades()
    signals = export_signals()
    performance = export_performance()
    risk_state = export_risk_state()
    summary = compute_summary(vt_data["trades"])

    export = {
        "generated_at": datetime.now(WIB).isoformat(),
        "balance": vt_data["balance"],
        "trades": vt_data["trades"],
        "signals": signals,
        "performance": performance,
        "risk_state": risk_state,
        "summary": summary,
    }

    out_path = os.path.join(BASE_DIR, "dashboard_export.json")
    with open(out_path, "w") as f:
        json.dump(export, f, indent=2, default=str)

    print(f"Export selesai: {out_path}")
    print(f"Total trades: {len(vt_data['trades'])} ({summary['total_trades']} closed, {summary['open_trades']} open)")
    print(f"Win rate: {summary['win_rate']}%")
    print(f"Total PnL: {summary['total_pnl_pct']}% / ${summary['total_pnl_usd']}")
    print(f"Signals tercatat: {len(signals)}")


if __name__ == "__main__":
    main()
