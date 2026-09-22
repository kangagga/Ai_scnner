"""
Pending Signals — state machine minimal untuk level "SIAP ENTRY — KONFIRMASI DULU".
[NEW 2026-09-21] Audit menemukan AUTO_EXECUTE=True membuat "SIAP ENTRY" diperlakukan
identik dengan "EKSEKUSI", tanpa jeda konfirmasi apapun. Modul ini menambah 1 langkah:
sinyal SIAP ENTRY disimpan sebagai PENDING dulu, di-promote jadi virtual trade sungguhan
HANYA setelah candle berikutnya terbentuk DAN kondisi sinyal masih valid saat dicek ulang.

Level "EKSEKUSI — ENTRY SEKARANG" TIDAK terpengaruh sama sekali oleh modul ini.
Tabel terpisah dari virtual_trades -- tidak mengubah skema/query yang sudah ada.
"""
import sqlite3, json, logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)
WIB = timezone(timedelta(hours=7))
PENDING_DB = "/home/userland/ai-scanner/virtual_trading.db"

TIMEFRAME_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
MAX_PENDING_CANDLES = 2  # lebih dari ini tanpa confirm -> drop sebagai INVALID

def init_pending_db():
    conn = sqlite3.connect(PENDING_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_momentum (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, timeframe TEXT, signal TEXT,
            created_at TEXT, sig_json TEXT, status TEXT DEFAULT 'PENDING'
        )
    """)
    conn.commit()
    conn.close()

def add_pending(sig: dict) -> bool:
    init_pending_db()
    conn = sqlite3.connect(PENDING_DB)
    cur = conn.cursor()
    symbol, timeframe, signal = sig.get("symbol"), sig.get("timeframe"), sig.get("signal")
    cur.execute("""SELECT id FROM pending_momentum
                   WHERE symbol=? AND timeframe=? AND signal=? AND status='PENDING'""",
                (symbol, timeframe, signal))
    if cur.fetchone():
        conn.close()
        return False
    now = datetime.now(WIB).isoformat()
    cur.execute("""INSERT INTO pending_momentum (symbol, timeframe, signal, created_at, sig_json, status)
                   VALUES (?, ?, ?, ?, ?, 'PENDING')""",
                (symbol, timeframe, signal, now, json.dumps(sig)))
    conn.commit()
    conn.close()
    logger.info(f"[PENDING] {symbol}/{timeframe} {signal} -> disimpan PENDING, tunggu candle berikutnya")
    return True

def get_due_pending() -> list:
    """Kandidat PENDING yang candle berikutnya sudah terbentuk -- siap dicek ulang."""
    init_pending_db()
    conn = sqlite3.connect(PENDING_DB)
    cur = conn.cursor()
    cur.execute("""SELECT id, symbol, timeframe, signal, created_at, sig_json
                   FROM pending_momentum WHERE status='PENDING'""")
    rows = cur.fetchall()
    conn.close()

    due = []
    now = datetime.now(WIB)
    for pid, symbol, timeframe, signal, created_at, sig_json in rows:
        tf_sec = TIMEFRAME_SECONDS.get(timeframe, 3600)
        created = datetime.fromisoformat(created_at)
        elapsed = (now - created).total_seconds()
        if elapsed >= tf_sec:
            due.append({"id": pid, "symbol": symbol, "timeframe": timeframe,
                        "signal": signal, "elapsed": elapsed, "tf_sec": tf_sec,
                        "sig": json.loads(sig_json)})
    return due

def mark_status(pid: int, status: str):
    conn = sqlite3.connect(PENDING_DB)
    cur = conn.cursor()
    cur.execute("UPDATE pending_momentum SET status=? WHERE id=?", (status, pid))
    conn.commit()
    conn.close()

def check_pending_signals():
    """Dipanggil di awal tiap job_scan(). Untuk kandidat PENDING yang candle
    berikutnya sudah terbentuk: cek apakah harga sudah bergerak SEARAH prediksi
    (bukan menuntut sinyal identik muncul lagi -- MOMENTUM itu transient by
    design, price_change_3 rolling window pasti bergeser tiap candle baru,
    jadi exact-match terlalu ketat, terbukti 12/12 gagal di percobaan pertama).

    CONFIRMED: harga sekarang sudah bergerak searah entry (BUY: harga > entry;
               SELL: harga < entry) -- momentum terbukti lanjut, promote ke trade.
    INVALID  : harga sudah kena SL, atau stagnan/berbalik tanpa progres searah
               -- momentum gagal lanjut, drop tanpa pernah masuk virtual_trades."""
    from virtual_trader import add_virtual_trade
    from exit_monitor import add_trade as exit_add_trade, get_current_price

    due = get_due_pending()
    if not due:
        return

    for item in due:
        pid, symbol, timeframe = item["id"], item["symbol"], item["timeframe"]
        sig = item["sig"]
        orig_signal = item["signal"]
        try:
            entry = sig.get("entry", 0)
            sl = sig.get("sl", 0)
            is_buy = orig_signal.startswith("BUY")

            price = get_current_price(symbol)
            if not price or entry <= 0:
                logger.info(f"[PENDING->INVALID] {symbol}/{timeframe} {orig_signal}: gagal ambil harga saat re-cek")
                mark_status(pid, "INVALID")
                continue

            # Cek SL duluan -- kalau sudah kena, jangan pernah dikonfirmasi
            hit_sl = (is_buy and price <= sl) or (not is_buy and price >= sl)
            if hit_sl:
                logger.info(f"[PENDING->INVALID] {symbol}/{timeframe} {orig_signal}: harga sudah kena SL sebelum sempat konfirmasi ({price} vs sl={sl})")
                mark_status(pid, "INVALID")
                continue

            # Confirmed kalau harga sudah bergerak searah (continuation terbukti)
            moved_favorable = (price > entry) if is_buy else (price < entry)
            if moved_favorable:
                logger.info(f"[PENDING->CONFIRMED] {symbol}/{timeframe} {orig_signal}: harga lanjut searah ({entry} -> {price}), promote ke ACTIVE")
                add_virtual_trade(sig)
                exit_add_trade(sig)
                mark_status(pid, "CONFIRMED")
            else:
                logger.info(f"[PENDING->INVALID] {symbol}/{timeframe} {orig_signal}: harga stagnan/berbalik ({entry} -> {price}), tidak ada continuation")
                mark_status(pid, "INVALID")
        except Exception as e:
            logger.warning(f"[PENDING] Error re-cek {symbol}/{timeframe}: {e}")
            mark_status(pid, "INVALID")

def get_all_pending() -> list:
    """Semua kandidat PENDING saat ini (due maupun belum), untuk ditampilkan
    di Telegram -- pengganti tombol Virtual Balance."""
    init_pending_db()
    conn = sqlite3.connect(PENDING_DB)
    cur = conn.cursor()
    cur.execute("""SELECT id, symbol, timeframe, signal, created_at
                   FROM pending_momentum WHERE status='PENDING'
                   ORDER BY created_at ASC""")
    rows = cur.fetchall()
    conn.close()

    now = datetime.now(WIB)
    result = []
    for pid, symbol, timeframe, signal, created_at in rows:
        tf_sec = TIMEFRAME_SECONDS.get(timeframe, 3600)
        created = datetime.fromisoformat(created_at)
        elapsed = (now - created).total_seconds()
        remaining_sec = max(0, tf_sec - elapsed)
        result.append({
            "id": pid, "symbol": symbol, "timeframe": timeframe,
            "signal": signal, "created_at": created_at,
            "remaining_min": round(remaining_sec / 60, 1),
            "is_due": remaining_sec <= 0,
        })
    return result
