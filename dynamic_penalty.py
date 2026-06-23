"""
Dynamic Penalty — multi-dimensi
Dibaca dari model/trade_analysis.json yang dihasilkan trade_analyzer.py
"""
import json, time
from pathlib import Path
from datetime import datetime, timezone

ANALYSIS_PATH = "model/trade_analysis.json"
_CACHE = {"data": None, "ts": 0}
try:
    from config import PENALTY_CACHE_TTL as _TTL
except ImportError:
    _TTL = 300

def get_session(hour=None):
    if hour is None:
        hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 8:   return "ASIA"
    if 8 <= hour < 16:  return "EUROPE"
    return "US"

def _load_analysis() -> dict:
    now = time.time()
    if _CACHE["data"] and now - _CACHE["ts"] < _TTL:
        return _CACHE["data"]
    p = Path(ANALYSIS_PATH)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        _CACHE["data"] = data
        _CACHE["ts"]   = now
        return data
    except Exception:
        return {}

def load_rules() -> list:
    return _load_analysis().get("penalty_rules", [])

def get_dynamic_penalty(signal: str, hour: int = None,
                        regime: str = "NEUTRAL") -> tuple:
    session  = get_session(hour)
    sig_base = signal.split(" ")[0]
    is_setup = "(SETUP)" in signal or "(REVERSAL)" in signal
    rules    = load_rules()
    matched  = {}

    for rule in rules:
        rtype   = rule.get("type", "signal_session")
        penalty = rule.get("penalty", 0)

        if rtype == "signal_session_regime":
            if (rule.get("signal") == sig_base and
                rule.get("session") == session and
                rule.get("regime")  == regime):
                adj = penalty // 2 if is_setup else penalty
                if abs(adj) > abs(matched.get("L3", {}).get("p", 0)):
                    matched["L3"] = {"p": adj, "r": rule.get("reason","")}

        elif rtype == "signal_session":
            if (rule.get("signal") == sig_base and
                rule.get("session") == session):
                adj = penalty // 2 if is_setup else penalty
                if abs(adj) > abs(matched.get("L2", {}).get("p", 0)):
                    matched["L2"] = {"p": adj, "r": rule.get("reason","")}

        elif rtype == "hour" and hour is not None:
            if rule.get("hour") == hour:
                if abs(penalty) > abs(matched.get("L1", {}).get("p", 0)):
                    matched["L1"] = {"p": penalty, "r": rule.get("reason","")}

    if not matched:
        return 0, "OK"

    best      = matched.get("L3") or matched.get("L2") or matched.get("L1")
    total     = best["p"]
    reason    = best["r"]
    if "L1" in matched and matched["L1"] != best:
        total  += matched["L1"]["p"] // 2
        reason += f" | {matched['L1']['r']}"

    return round(total, 1), reason

def get_pair_penalty(symbol: str) -> tuple:
    data     = _load_analysis()
    worst    = data.get("worst_pairs", {})
    per_pair = data.get("per_pair", {})
    sym      = symbol.replace("/", "")
    if sym in worst:
        wr        = worst[sym]
        pair_data = per_pair.get(sym, {})
        total     = pair_data.get("total", 0)
        if total >= 5 and wr < 30:
            return -10, f"{sym} WR={wr}% (worst pair)"
        elif total >= 3 and wr == 0:
            return -20, f"{sym} WR=0% (blacklist candidate)"
    return 0, "OK"

def get_penalty_summary() -> str:
    rules = load_rules()
    if not rules:
        return "Belum ada penalty rules (butuh lebih banyak data)"
    lines = [f"📋 Dynamic Penalty Rules ({len(rules)} aktif):"]
    for r in rules[:10]:
        lines.append(f"  {r['reason']} → {r['penalty']} (n={r.get('n',0)})")
    return "\n".join(lines)
