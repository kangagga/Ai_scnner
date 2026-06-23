import json
from pathlib import Path
from datetime import datetime, timezone

ANALYSIS_PATH = "model/trade_analysis.json"

def get_session(hour=None):
    if hour is None:
        hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 8:   return "ASIA"
    if 8 <= hour < 16:  return "EUROPE"
    return "US"

def load_rules():
    p = Path(ANALYSIS_PATH)
    if not p.exists():
        return []
    with open(p) as f:
        data = json.load(f)
    return data.get("penalty_rules", [])

def get_dynamic_penalty(signal: str, hour: int = None) -> tuple:
    """
    Return (penalty_score, reason)
    Dipanggil dari scanner.py sebelum return sinyal.
    """
    session = get_session(hour)
    rules = load_rules()
    
    # Normalisasi signal — BUY (SETUP) → cek rule BUY dulu, lalu SETUP
    sig_base = signal.split(" ")[0]  # BUY atau SELL
    sig_full = signal                 # BUY (SETUP) dll

    total_penalty = 0
    reasons = []

    for rule in rules:
        rule_sig = rule.get("signal", "")
        rule_sess = rule.get("session", "")
        penalty = rule.get("penalty", 0)
        
        # Match signal base (BUY/SELL) + session
        if rule_sig == sig_base and rule_sess == session:
            # SETUP signals dapat setengah penalty karena WR lebih tinggi
            if "(SETUP)" in sig_full or "(REVERSAL)" in sig_full:
                adj = penalty // 2
            else:
                adj = penalty
            total_penalty += adj
            reasons.append(f"{rule_sig}+{session} WR={rule.get('win_rate')}%")

    return total_penalty, " | ".join(reasons) if reasons else "OK"

def get_pair_penalty(symbol: str) -> tuple:
    """
    Tambahan penalty jika pair masuk worst list.
    Return (penalty, reason)
    """
    p = Path(ANALYSIS_PATH)
    if not p.exists():
        return 0, "OK"
    with open(p) as f:
        data = json.load(f)
    
    worst = data.get("worst_pairs", {})
    per_pair = data.get("per_pair", {})
    
    sym = symbol.replace("/", "")
    
    if sym in worst:
        wr = worst[sym]
        pair_data = per_pair.get(sym, {})
        total = pair_data.get("total", 0)
        if total >= 5 and wr < 30:
            return -10, f"{sym} WR={wr}% (worst pair)"
        elif total >= 3 and wr == 0:
            return -20, f"{sym} WR=0% (blacklist candidate)"
    
    return 0, "OK"