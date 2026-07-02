"""
smc_scorer.py — SMC Confidence Scorer
Institutional AI v9 | SMC Layer
Gabungkan semua komponen scoring sesuai bobot:
Trend Score     : 25
FVG Score       : 20
Supply Demand   : 20
Retest Score    : 15
Volume Score    : 10
Divergence Score: 10
"""
import pandas as pd
from trend_filter       import get_trend_score, analyze_trend
from smart_zone_engine  import get_fvg_score, get_smc_analysis
from zone_detector      import get_zone_score
from retest_filter      import get_retest_score, is_retest
from volume_filter      import get_volume_score, analyze_volume
from divergence_detector import get_divergence_score, detect_divergence


def smc_confidence(df: pd.DataFrame, signal: str) -> dict:
    """
    Hitung SMC confidence score 0-100.
    
    Returns:
        dict: {
            "score"       : float 0-100,
            "trend_score" : float 0-25,
            "fvg_score"   : float 0-20,
            "zone_score"  : float 0-20,
            "retest_score": float 0-15,
            "volume_score": float 0-10,
            "div_score"   : float 0-10,
            "breakdown"   : dict,
            "retest_info" : dict,
            "div_info"    : dict,
            "volume_info" : dict,
            "trend_info"  : dict,
            "valid"       : bool,
            "reason"      : str
        }
    """
    # Hitung semua komponen
    trend_score  = get_trend_score(df, signal)
    fvg_score    = get_fvg_score(df, signal)
    zone_score   = get_zone_score(df, signal)
    retest_score = get_retest_score(df, signal)
    volume_score = get_volume_score(df, signal)
    div_score    = get_divergence_score(df, signal)

    # Detail info
    retest_info = is_retest(df, signal)
    div_info    = detect_divergence(df)
    volume_info = analyze_volume(df, signal)
    trend_info  = analyze_trend(df)

    # Total score
    total = (
        trend_score +
        fvg_score   +
        zone_score  +
        retest_score+
        volume_score+
        div_score
    )
    total = round(min(total, 100), 1)

    # Validasi minimum
    reasons = []
    valid   = True

    # Hard filter: doji → invalid
    if volume_info.get("is_doji"):
        valid  = False
        reasons.append("Doji candle")

    # Hard filter: melawan trend kuat → invalid
    if trend_score == 0 and trend_info.get("strength") == "STRONG":
        valid  = False
        reasons.append("Melawan trend kuat")

    # Hard filter: tidak ada retest sama sekali
    if retest_score == 0:
        reasons.append("Tidak dalam zona retest")

    breakdown = {
        "trend"     : trend_score,
        "fvg"       : fvg_score,
        "zone"      : zone_score,
        "retest"    : retest_score,
        "volume"    : volume_score,
        "divergence": div_score,
    }

    return {
        "score"       : total,
        "trend_score" : trend_score,
        "fvg_score"   : fvg_score,
        "zone_score"  : zone_score,
        "retest_score": retest_score,
        "volume_score": volume_score,
        "div_score"   : div_score,
        "breakdown"   : breakdown,
        "retest_info" : retest_info,
        "div_info"    : div_info,
        "volume_info" : volume_info,
        "trend_info"  : trend_info,
        "valid"       : valid,
        "reason"      : ", ".join(reasons) if reasons else "OK",
        # ── Score adjustment untuk scanner.py ──
        # SMC score 0-100 → bonus/penalty -10 s/d +15
        "score_adjustment": (
            +15 if total >= 85 else
            +10 if total >= 70 else
            +5  if total >= 55 else
            0
        ),
    }


def format_smc_report(result: dict, symbol: str, signal: str) -> str:
    """Format SMC analysis untuk Telegram."""
    b = result["breakdown"]
    r = result["retest_info"]
    t = result["trend_info"]

    return (
        f"🧠 <b>SMC Analysis — {symbol}</b>\n"
        f"{'━'*25}\n"
        f"📊 Signal    : {signal}\n"
        f"🎯 SMC Score : {result['score']}/100\n"
        f"{'━'*25}\n"
        f"📈 Trend     : {t.get('trend','?')} ({t.get('strength','?')}) [{b['trend']}/25]\n"
        f"🔲 FVG       : {b['fvg']}/20\n"
        f"🟦 Zone      : {b['zone']}/20\n"
        f"🔄 Retest    : {r.get('reason','?')} [{b['retest']}/15]\n"
        f"📦 Volume    : {result['volume_info'].get('reason','?')} [{b['volume']}/10]\n"
        f"📉 Divergence: {result['div_info'].get('reason','?')} [{b['divergence']}/10]\n"
        f"{'━'*25}\n"
        f"{'✅ VALID' if result['valid'] else '❌ INVALID'} — {result['reason']}\n"
    )
