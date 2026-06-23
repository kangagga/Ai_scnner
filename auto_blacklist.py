"""
Auto-blacklist pair yang konsisten loss
Dijalankan periodik oleh main.py
"""
import sqlite3, logging
from datetime import datetime, timedelta
from blacklist import is_blacklisted, _load, _save
from config import (
    BLACKLIST_DAYS, BLACKLIST_MIN_TRADES as MIN_TRADES,
    BLACKLIST_MAX_WR as MAX_WINRATE,
    BLACKLIST_MAX_LOSS as CONSECUTIVE_LOSS,
)

logger = logging.getLogger(__name__)

VIRTUAL_DB  = "virtual_trading.db"
SIGNALS_DB  = "signals.db"
MAX_AVG_LOSS = -2.0

def get_pair_stats(days_back: int = 14) -> list:
    """Ambil statistik per pair dari N hari terakhir"""
    conn = sqlite3.connect(VIRTUAL_DB)
    since = (datetime.now() - timedelta(days=days_back)).isoformat()
    rows = conn.execute("""
        SELECT 
            symbol,
            COUNT(*) as total,
            SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(pnl_pct), 2) as avg_pnl,
            MIN(pnl_pct) as worst_pnl
        FROM virtual_trades
        WHERE closed=1 
          AND result IN ('WIN','LOSS')
          AND timestamp >= ?
        GROUP BY symbol
        HAVING COUNT(*) >= ?
        ORDER BY avg_pnl ASC
    """, (since, MIN_TRADES)).fetchall()
    conn.close()
    return rows

def get_consecutive_losses(symbol: str) -> int:
    """Hitung loss berturut-turut terakhir untuk pair"""
    conn = sqlite3.connect(VIRTUAL_DB)
    rows = conn.execute("""
        SELECT result FROM virtual_trades
        WHERE symbol=? AND closed=1 AND result IN ('WIN','LOSS')
        ORDER BY timestamp DESC LIMIT 10
    """, (symbol,)).fetchall()
    conn.close()
    count = 0
    for (r,) in rows:
        if r == 'LOSS':
            count += 1
        else:
            break
    return count

# is_blacklisted() → gunakan langsung dari blacklist.py

def add_to_blacklist(symbol: str, reason: str, days: int = BLACKLIST_DAYS):
    """Tambahkan pair ke blacklist — pakai blacklist.py (JSON)"""
    try:
        from blacklist import _load, _save, BLACKLIST_FILE
        data   = _load()
        until  = (datetime.now() + timedelta(days=days)).isoformat()
        data["blacklist"][symbol] = {"until": until, "reason": reason}
        _save(data)
        logger.warning(f"[AUTO-BL] {symbol} diblacklist {days}hr: {reason}")
        return True
    except Exception as e:
        logger.error(f"[AUTO-BL] Gagal tambah {symbol}: {e}")
        return False

def run_auto_blacklist() -> dict:
    """
    Evaluasi semua pair dan blacklist yang layak.
    Return: dict hasil evaluasi
    """
    result = {"checked": 0, "blacklisted": [], "skipped": []}
    stats  = get_pair_stats(days_back=14)

    for row in stats:
        symbol, total, wins, avg_pnl, worst_pnl = row
        winrate = wins / total * 100 if total > 0 else 0
        consec  = get_consecutive_losses(symbol)
        result["checked"] += 1

        reasons = []

        # Kriteria 1: winrate sangat rendah + avg loss
        if winrate < MAX_WINRATE and avg_pnl < MAX_AVG_LOSS:
            reasons.append(f"WR={winrate:.0f}% avg={avg_pnl:.1f}%")

        # Kriteria 2: consecutive loss
        if consec >= CONSECUTIVE_LOSS:
            reasons.append(f"{consec}x loss berturut")

        # Kriteria 3: avg loss sangat dalam
        if avg_pnl < -4.0 and total >= 3:
            reasons.append(f"avg loss dalam ({avg_pnl:.1f}%)")

        if reasons and not is_blacklisted(symbol):
            reason_str = " | ".join(reasons)
            add_to_blacklist(symbol, reason_str)
            result["blacklisted"].append(f"{symbol}: {reason_str}")
            logger.warning(f"[AUTO-BL] {symbol} → {reason_str}")
        else:
            result["skipped"].append(symbol)

    logger.info(f"[AUTO-BL] Selesai: {result['checked']} pair dicek, "
                f"{len(result['blacklisted'])} diblacklist")
    return result


def get_blacklist_report() -> str:
    """Laporan blacklist untuk Telegram"""
    try:
        from blacklist import _load
        data = _load()
        bl   = data.get("blacklist", {})
        now  = datetime.now().isoformat()
        active = {k: v for k, v in bl.items()
                  if isinstance(v, dict) and v.get("until", "") > now}
        if not active:
            return "✅ Tidak ada pair dalam blacklist"
        lines = ["🚫 <b>Auto-Blacklist Aktif:</b>"]
        for sym, info in sorted(active.items()):
            exp   = info.get("until", "")[:10]
            reason= info.get("reason", "")
            lines.append(f"  • {sym}: {reason} (s/d {exp})")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Gagal ambil blacklist: {e}"
