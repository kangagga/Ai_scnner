"""
module_auditor.py — Performance Audit per 100 Trades
"""

import sqlite3
import os
import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

DB_PATH        = os.path.expanduser("~/ai-scanner/virtual_trading.db")
AUDIT_INTERVAL = 100
STATE_FILE     = os.path.expanduser("~/ai-scanner/audit_state.json")
REPORT_DIR     = os.path.expanduser("~/ai-scanner/audit_reports/")

MODULES = {
    "SMC"      : {"bonus_col": "smc_bonus",  "score_col": "smc_score"},
    "OB"       : {"bonus_col": "ob_bonus",   "score_col": "ob_imbalance"},
    "VP"       : {"bonus_col": "vp_bonus",   "score_col": "vp_ratio"},
    "Liquidity": {"bonus_col": "liq_adj",    "score_col": "liq_score"},
    "Scorer"   : {"bonus_col": "score_final","score_col": "score_raw"},
}

GRADE = {
    "🟢 BAGUS" : lambda wr, avg_pnl: wr >= 60 and avg_pnl > 0,
    "🟡 CUKUP" : lambda wr, avg_pnl: 45 <= wr < 60 or (wr >= 60 and avg_pnl <= 0),
    "🔴 LEMAH" : lambda wr, avg_pnl: wr < 45 or avg_pnl < -0.5,
}

Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)

def get_conn():
    return sqlite3.connect(DB_PATH)

def get_last_audited_id():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f).get("last_audited_id", 0)
    return 0

def save_last_audited_id(trade_id):
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
    state["last_audited_id"] = trade_id
    state["last_audit_time"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def fetch_trades_since(last_id):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, symbol, signal, result,
               pnl_pct, pnl_usd, score_raw, score_final,
               smc_bonus, smc_score,
               ob_bonus, ob_imbalance,
               vp_bonus, vp_ratio,
               liq_adj, liq_score,
               regime, hour_entry, timeframe, closed_at
        FROM virtual_trades
        WHERE closed = 1 AND id > ?
        ORDER BY id ASC
    """, (last_id,))
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def fetch_balance():
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT balance, peak_balance, total_trades, total_wins, total_losses FROM virtual_balance WHERE id=1")
    row = cur.fetchone()
    conn.close()
    if row:
        return {"balance": row[0], "peak_balance": row[1],
                "total_trades": row[2], "total_wins": row[3], "total_losses": row[4]}
    return {}

def analyse_module(trades, module, cols):
    bonus_col = cols["bonus_col"]
    active    = [t for t in trades if (t.get(bonus_col) or 0) > 0]
    inactive  = [t for t in trades if (t.get(bonus_col) or 0) <= 0]

    def stats(group):
        if not group:
            return {"count": 0, "win_rate": 0, "avg_pnl_pct": 0, "total_pnl_usd": 0}
        wins = sum(1 for t in group if t.get("result") == "WIN")
        pcts = [t.get("pnl_pct") or 0 for t in group]
        usds = [t.get("pnl_usd") or 0 for t in group]
        return {
            "count"        : len(group),
            "win_rate"     : round(wins / len(group) * 100, 1),
            "avg_pnl_pct"  : round(sum(pcts) / len(pcts), 2),
            "total_pnl_usd": round(sum(usds), 3),
        }

    act   = stats(active)
    inact = stats(inactive)
    bonuses   = [t.get(bonus_col) or 0 for t in active]
    avg_bonus = round(sum(bonuses) / len(bonuses), 2) if bonuses else 0
    lift      = round(act["win_rate"] - inact["win_rate"], 1) if inact["count"] > 0 else 0

    grade = "🔴 LEMAH"
    for label, fn in GRADE.items():
        if fn(act["win_rate"], act["avg_pnl_pct"]):
            grade = label
            break

    return {"module": module, "grade": grade, "active": act,
            "inactive": inact, "avg_bonus": avg_bonus, "lift_wr": lift}

def analyse_regime(trades):
    regimes = {}
    for t in trades:
        r = t.get("regime") or "NEUTRAL"
        if r not in regimes:
            regimes[r] = {"count": 0, "wins": 0, "pnl": 0}
        regimes[r]["count"] += 1
        regimes[r]["pnl"]   += t.get("pnl_pct") or 0
        if t.get("result") == "WIN":
            regimes[r]["wins"] += 1
    result = {}
    for r, v in regimes.items():
        result[r] = {
            "count"   : v["count"],
            "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0,
            "avg_pnl" : round(v["pnl"] / v["count"], 2) if v["count"] else 0,
        }
    return result

def analyse_timeframe(trades):
    tfs = {}
    for t in trades:
        tf = t.get("timeframe") or "?"
        if tf not in tfs:
            tfs[tf] = {"count": 0, "wins": 0, "pnl": 0}
        tfs[tf]["count"] += 1
        tfs[tf]["pnl"]   += t.get("pnl_pct") or 0
        if t.get("result") == "WIN":
            tfs[tf]["wins"] += 1
    result = {}
    for tf, v in tfs.items():
        result[tf] = {
            "count"   : v["count"],
            "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0,
            "avg_pnl" : round(v["pnl"] / v["count"], 2) if v["count"] else 0,
        }
    return dict(sorted(result.items(), key=lambda x: -x[1]["win_rate"]))

def analyse_hour(trades):
    hours = {}
    for t in trades:
        h = t.get("hour_entry")
        if h is None:
            continue
        if h not in hours:
            hours[h] = {"count": 0, "wins": 0, "pnl": 0}
        hours[h]["count"] += 1
        hours[h]["pnl"]   += t.get("pnl_pct") or 0
        if t.get("result") == "WIN":
            hours[h]["wins"] += 1
    result = {}
    for h, v in hours.items():
        if v["count"] >= 3:
            result[h] = {
                "count"   : v["count"],
                "win_rate": round(v["wins"] / v["count"] * 100, 1),
                "avg_pnl" : round(v["pnl"] / v["count"], 2),
            }
    return result

def build_report(trades, batch_num):
    total   = len(trades)
    wins    = sum(1 for t in trades if t.get("result") == "WIN")
    losses  = total - wins
    wr      = round(wins / total * 100, 1) if total else 0
    pnl_pct = sum(t.get("pnl_pct") or 0 for t in trades)
    pnl_usd = sum(t.get("pnl_usd") or 0 for t in trades)
    balance = fetch_balance()

    sep   = "=" * 52
    lines = [
        "", sep,
        f"  MODULE AUDIT -- BATCH #{batch_num}",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        sep,
        f"  Trades   : {total} (Win: {wins} | Loss: {losses})",
        f"  Win Rate : {wr}%",
        f"  PnL Batch: {pnl_pct:+.2f}% | ${pnl_usd:+.2f}",
    ]
    if balance:
        lines += [
            f"  Balance  : ${balance.get('balance', 0):.2f}",
            f"  Peak     : ${balance.get('peak_balance', 0):.2f}",
            f"  Total All: {balance.get('total_trades', 0)} trades",
        ]

    lines += ["", "-" * 52, "  PERFORMA PER MODUL", "-" * 52]

    module_results = []
    for mod, cols in MODULES.items():
        module_results.append(analyse_module(trades, mod, cols))

    grade_order = {"🟢 BAGUS": 0, "🟡 CUKUP": 1, "🔴 LEMAH": 2}
    module_results.sort(key=lambda r: (grade_order.get(r["grade"], 9), -r["active"]["win_rate"]))

    for res in module_results:
        act   = res["active"]
        inact = res["inactive"]
        lift  = f"(+{res['lift_wr']}% lift)" if res["lift_wr"] > 0 else \
                f"({res['lift_wr']}% lift)"   if res["lift_wr"] < 0 else ""
        lines += [
            "",
            f"  {res['grade']}  {res['module']}",
            f"    Aktif  : {act['count']} trades | WR {act['win_rate']}% | AvgPnL {act['avg_pnl_pct']:+.2f}% {lift}",
            f"    Inaktif: {inact['count']} trades | WR {inact['win_rate']}%",
            f"    AvgBonus: {res['avg_bonus']} | TotalPnL: ${act['total_pnl_usd']:+.2f}",
        ]

    lines += ["", "-" * 52, "  REKOMENDASI", "-" * 52]
    weak = [r for r in module_results if "LEMAH" in r["grade"]]
    good = [r for r in module_results if "BAGUS" in r["grade"]]

    if good:
        lines.append(f"  OK  Pertahankan bobot: {', '.join(r['module'] for r in good)}")
    if weak:
        for r in weak:
            act = r["active"]
            if act["win_rate"] < 40:
                lines.append(f"  !!  {r['module']}: WR {act['win_rate']}% -- kurangi bobot bonus")
            elif act["avg_pnl_pct"] < -0.5:
                lines.append(f"  !!  {r['module']}: avg PnL {act['avg_pnl_pct']:+.2f}% -- cek threshold")
            else:
                lines.append(f"  !!  {r['module']}: di bawah standar -- monitor lanjut")
    if not weak:
        lines.append("  Semua modul performa baik di batch ini!")

    regimes = analyse_regime(trades)
    lines += ["", "-" * 52, "  WIN RATE PER REGIME", "-" * 52]
    for regime, v in sorted(regimes.items(), key=lambda x: -x[1]["win_rate"]):
        bar = "#" * int(v["win_rate"] / 10)
        lines.append(f"  {regime:<12} {bar:<10} {v['win_rate']}% ({v['count']} trades, avg {v['avg_pnl']:+.2f}%)")

    tfs = analyse_timeframe(trades)
    lines += ["", "-" * 52, "  WIN RATE PER TIMEFRAME", "-" * 52]
    for tf, v in tfs.items():
        bar = "#" * int(v["win_rate"] / 10)
        lines.append(f"  {tf:<8} {bar:<10} {v['win_rate']}% ({v['count']} trades, avg {v['avg_pnl']:+.2f}%)")

    hours = analyse_hour(trades)
    if hours:
        sorted_h = sorted(hours.items(), key=lambda x: -x[1]["win_rate"])
        best3    = sorted_h[:3]
        worst3   = sorted_h[-3:]
        lines += ["", "-" * 52, "  JAM ENTRY TERBAIK & TERBURUK", "-" * 52]
        lines.append("  Terbaik:")
        for h, v in best3:
            lines.append(f"    {h:02d}:00  WR {v['win_rate']}% | {v['count']} trades | avg {v['avg_pnl']:+.2f}%")
        lines.append("  Terburuk:")
        for h, v in reversed(worst3):
            lines.append(f"    {h:02d}:00  WR {v['win_rate']}% | {v['count']} trades | avg {v['avg_pnl']:+.2f}%")

    lines += ["", sep, ""]
    return "\n".join(lines)

def run_audit(force=False):
    last_id = get_last_audited_id()
    trades  = fetch_trades_since(last_id)

    if not force and len(trades) < AUDIT_INTERVAL:
        remaining = AUDIT_INTERVAL - len(trades)
        print(f"[AUDIT] {len(trades)}/{AUDIT_INTERVAL} trades sejak audit terakhir. Butuh {remaining} lagi.")
        return False

    batch         = trades[:AUDIT_INTERVAL] if not force else trades
    last_trade_id = batch[-1]["id"] if batch else last_id
    state         = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    batch_num     = state.get("batch_count", 0) + 1

    if not batch:
        print("[AUDIT] Tidak ada trades untuk diaudit.")
        return False

    report = build_report(batch, batch_num)
    print(report)

    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"audit_batch{batch_num:03d}_{ts}.txt")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"[AUDIT] Report disimpan: {report_path}")

    state["last_audited_id"] = last_trade_id
    state["last_audit_time"] = datetime.now().isoformat()
    state["batch_count"]     = batch_num
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    return True

def watch_mode(check_interval_sec=300):
    print(f"[AUDIT] Watch mode aktif -- cek setiap {check_interval_sec}s")
    while True:
        try:
            run_audit()
        except Exception as e:
            print(f"[AUDIT] Error: {e}")
        time.sleep(check_interval_sec)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch",    action="store_true")
    parser.add_argument("--force",    action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    if args.watch:
        watch_mode(args.interval)
    else:
        run_audit(force=args.force)
