
import sqlite3, json, os
from datetime import datetime, timedelta, timezone
import logging
logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
VIRTUAL_DB = "/home/userland/ai-scanner/virtual_trading.db"
VIRTUAL_BALANCE = 1000.0  # Balance awal $1000

def is_duplicate_position(symbol, timeframe, signal):
    """Cek apakah sudah ada posisi terbuka untuk pair+timeframe (read-only,
    tidak insert). [FIX 2026-08-26] Sebelumnya query ikut mencocokkan kolom
    signal secara exact, sehingga "BUY (SR BOUNCE)" dan "SELL (SR BOUNCE)"
    dianggap 2 kombinasi berbeda -- akibatnya posisi BUY dan SELL bisa
    terbuka bersamaan di pair+timeframe yang sama (saling bertentangan,
    tidak masuk akal secara trading). Sekarang cek per pair+timeframe saja,
    apapun arah/jenis sinyalnya -- 1 pair+timeframe maksimal 1 posisi
    terbuka."""
    try:
        conn = sqlite3.connect(VIRTUAL_DB)
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM virtual_trades
            WHERE symbol=? AND timeframe=? AND closed=0
            LIMIT 1
        """, (symbol, timeframe))
        result = cur.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        logger.warning(f"[is_duplicate_position] Error cek {symbol}: {e}")
        return False


def init_virtual_db():
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS virtual_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            signal TEXT,
            entry REAL,
            sl REAL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            exit_price REAL,
            pnl_pct REAL,
            pnl_usd REAL,
            result TEXT,
            balance_after REAL,
            timeframe TEXT
        );
        CREATE TABLE IF NOT EXISTS virtual_balance (
            id INTEGER PRIMARY KEY,
            balance REAL,
            peak_balance REAL,
            total_trades INTEGER,
            total_wins INTEGER,
            total_losses INTEGER,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS virtual_trade_partials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER,
            tp_level TEXT,
            exit_price REAL,
            pct_closed REAL,
            pnl_pct REAL,
            pnl_usdt REAL,
            closed_at TEXT
        );
    """)
    # Init balance kalau belum ada
    cur.execute("SELECT COUNT(*) FROM virtual_balance")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO virtual_balance VALUES (1, ?, ?, 0, 0, 0, ?)",
                   (VIRTUAL_BALANCE, VIRTUAL_BALANCE, datetime.now(WIB).isoformat()))
    conn.commit()
    conn.close()

def get_balance():
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()
    cur.execute("SELECT balance, peak_balance, total_trades, total_wins, total_losses FROM virtual_balance WHERE id=1")
    row = cur.fetchone()
    conn.close()
    return {"balance": row[0], "peak": row[1], "total": row[2], "wins": row[3], "losses": row[4]}

def add_virtual_trade(signal: dict):
    """Tambah trade virtual saat sinyal masuk"""
    init_virtual_db()
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()
    
    symbol = signal.get("symbol")
    timeframe = signal.get("timeframe")
    sig_type = signal.get("signal")
    
    # === FILTER DUPLIKASI ===
    # Cek apakah sudah ada posisi terbuka untuk pair+timeframe+signal yang sama
    cur.execute("""
        SELECT id FROM virtual_trades
        WHERE symbol=? AND timeframe=? AND signal=? AND closed=0
        LIMIT 1
    """, (symbol, timeframe, sig_type))
    if cur.fetchone():
        logger.info(f"[DUPLICATE] {symbol}/{timeframe} {sig_type} sudah ada posisi terbuka, skip")
        conn.close()
        return
    
    now = datetime.now(WIB).isoformat()
    cur.execute("""INSERT INTO virtual_trades
        (timestamp, symbol, signal, entry, sl, tp1, tp2, tp3, timeframe,
         smc_score, smc_bonus, ob_imbalance, ob_pressure, ob_bonus,
         vp_ratio, vp_bonus, liq_usd, liq_score, liq_adj,
         funding_rate, price_vs_vwap, score_raw, score_final,
         regime, hour_entry,
         support, resistance, sr_guard_pass)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?)""",
        (now, symbol, sig_type,
         signal.get("entry", 0), signal.get("sl", 0),
         signal.get("tp1", 0), signal.get("tp2", 0),
         signal.get("tp3", 0), timeframe,
         signal.get("smc_data", {}).get("score", 0),
         signal.get("smc_bonus", 0),
         signal.get("ob_imbalance", 0),
         signal.get("ob_pressure", "N/A"),
         signal.get("ob_bonus", 0),
         signal.get("buy_sell_ratio", 1.0),  # vp_ratio field
         signal.get("vp_bonus", 0),
         signal.get("liq_usd", 0),
         signal.get("liq_score", 5),
         signal.get("liq_adj", 0),
         signal.get("funding_rate_ob", 0),
         signal.get("price_vs_vwap", 0),
         signal.get("score_raw", 0),
         signal.get("score", 0),
         signal.get("regime", "NEUTRAL"),
         int(datetime.now().strftime("%H")),
         signal.get("support", 0),
         signal.get("resistance", 0),
         1))
    conn.commit()

    # ── Notifikasi Telegram saat posisi dibuka ──
    try:
        from telegram_sender import send_alert
        _entry  = signal.get("entry", 0)
        _sl     = signal.get("sl", 0)
        _tp1    = signal.get("tp1", 0)
        _score  = signal.get("score", 0)
        _smc    = signal.get("smc_data", {}).get("score", 0)
        _rr     = signal.get("rr_ratio", 0)
        if not _rr and _entry and _sl and _tp1:
            _risk = abs(_entry - _sl)
            _reward = abs(_tp1 - _entry)
            _rr = round(_reward / _risk, 2) if _risk > 0 else 0
        _is_manual = "MANUAL" in str(sig_type)
        _score_line = "N/A (Manual Override)" if _is_manual else f"{_score}/100 | SMC: {_smc}/100"
        _msg = (
            f"🚀 <b>TRADE DIBUKA</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 {symbol} | {timeframe} | {sig_type}\n"
            f"💰 Entry  : <code>{_entry}</code>\n"
            f"🛑 SL     : <code>{_sl}</code>\n"
            f"✅ TP1    : <code>{_tp1}</code>\n"
            f"⚖️  R:R   : 1:{_rr}\n"
            f"🎯 Score  : {_score_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        send_alert(_msg)
    except Exception as _ne:
        logger.debug(f"[NOTIF] Gagal kirim notif open: {_ne}")
    conn.close()

    # Sinkronisasi ke risk_manager supaya /status di Telegram akurat
    try:
        from risk_manager import open_position
        open_position(
            symbol=symbol,
            timeframe=timeframe,
            signal=sig_type,
            risk_pct=2.0,
        )
    except Exception as e:
        logger.warning(f"[RISK_SYNC] Gagal open_position: {e}")

def close_virtual_trade(symbol: str, timeframe: str, signal: str, pnl_pct: float,
                         pct_closed: float = 100.0, tp_level: str = "FINAL",
                         is_final: bool = True):
    """Tutup (partial atau final) trade virtual & catat hasil per-leg"""
    init_virtual_db()
    conn = sqlite3.connect(VIRTUAL_DB)
    cur = conn.cursor()
    now = datetime.now(WIB).isoformat()

    # Ambil trade yang masih open
    cur.execute("""
        SELECT id, entry FROM virtual_trades
        WHERE symbol=? AND timeframe=? AND signal=? AND closed=0
        ORDER BY timestamp DESC LIMIT 1
    """, (symbol, timeframe, signal))
    row = cur.fetchone()

    if not row:
        logger.warning(f"No open trade found for {symbol}/{timeframe}/{signal}")
        conn.close()
        return

    trade_id, entry = row

    # Hitung pnl_usdt untuk porsi (pct_closed) yang ditutup di leg ini
    trade_amount = 25.0
    leg_amount = trade_amount * (pct_closed / 100.0)
    pnl_usdt = leg_amount * pnl_pct / 100.0

    # Exit price (arah beda untuk BUY vs SELL)
    if signal.startswith("BUY"):
        exit_price = entry * (1 + pnl_pct / 100)
    else:
        exit_price = entry * (1 - pnl_pct / 100)

    # Catat leg ini sebagai partial record (selalu, baik partial maupun final)
    cur.execute("""
        INSERT INTO virtual_trade_partials
        (trade_id, tp_level, exit_price, pct_closed, pnl_pct, pnl_usdt, closed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (trade_id, tp_level, exit_price, pct_closed, pnl_pct, pnl_usdt, now))

    if not is_final:
        conn.commit()
        conn.close()
        logger.info(
            f"Partial close: {symbol}/{timeframe} {signal} | {tp_level} | "
            f"{pct_closed}% | PnL leg: {pnl_pct:.2f}% / ${pnl_usdt:.2f} (sisa posisi jalan)"
        )
        return

    # Final close: agregat semua partial (termasuk leg ini) lalu tutup trade
    cur.execute("""
        SELECT COALESCE(SUM(pnl_usdt), 0) FROM virtual_trade_partials WHERE trade_id=?
    """, (trade_id,))
    total_pnl_usdt = cur.fetchone()[0]
    total_pnl_pct = round(total_pnl_usdt / trade_amount * 100.0, 2)

    result = "WIN" if total_pnl_usdt > 0 else "LOSS"
    cur.execute("""
        UPDATE virtual_trades SET
            closed=1, exit_price=?, pnl_pct=?, pnl_usd=?, pnl_usdt=?, result=?,
            closed_at=?
        WHERE id=?
        """, (exit_price, total_pnl_pct, total_pnl_usdt, total_pnl_usdt, result, now, trade_id))

    conn.commit()
    conn.close()

    status = "WIN" if total_pnl_usdt > 0 else "LOSS"
    logger.info(
        f"Trade closed (final): {symbol}/{timeframe} {signal} | "
        f"{status} | Total PnL: {total_pnl_pct:.2f}% / ${total_pnl_usdt:.2f}"
    )

    # Sinkronisasi ke risk_manager untuk update balance & win rate (sekali, agregat)
    try:
        from risk_manager import record_trade_result
        win = total_pnl_usdt > 0
        record_trade_result(
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            pnl_usdt=total_pnl_usdt,
            win=win
        )
        logger.info(f"[RISK_SYNC] record_trade_result OK: {symbol} win={win}")
    except Exception as e:
        logger.warning(f"[RISK_SYNC] Gagal record_trade_result: {e}")

def get_summary():
    """Ringkasan performa virtual"""
    init_virtual_db()
    bal = get_balance()
    balance = bal["balance"]
    peak = bal["peak"]
    total = bal["total"]
    wins = bal["wins"]
    losses = bal["losses"]
    wr = round(100*wins/total, 1) if total else 0
    profit = round(balance - VIRTUAL_BALANCE, 2)
    profit_pct = round((balance - VIRTUAL_BALANCE) / VIRTUAL_BALANCE * 100, 2)
    drawdown = round((peak - balance) / peak * 100, 2) if peak > 0 else 0

    return {
        "balance": balance,
        "profit": profit,
        "profit_pct": profit_pct,
        "peak": peak,
        "drawdown": drawdown,
        "total": total,
        "wins": wins,
        "losses": losses,
        "wr": wr
    }

def send_virtual_summary(send_alert_fn):
    """Kirim ringkasan virtual trading ke Telegram"""
    s = get_summary()
    emoji = "📈" if s["profit"] >= 0 else "📉"
    msg = (
        f"{emoji} <b>Virtual Trading Update</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Balance  : ${s['balance']:.2f}\n"
        f"📊 Profit   : ${s['profit']:.2f} ({s['profit_pct']}%)\n"
        f"🏔️  Peak     : ${s['peak']:.2f}\n"
        f"📉 Drawdown : {s['drawdown']}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Total Trade: {s['total']}\n"
        f"✅ Menang   : {s['wins']}\n"
        f"❌ Kalah    : {s['losses']}\n"
        f"📈 Win Rate : {s['wr']}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Virtual Trading Bot"
    )
    send_alert_fn(msg)

if __name__ == "__main__":
    init_virtual_db()
    s = get_summary()
    logger.info(f"[VT] Balance: ${s['balance']:.2f}")
    logger.info(f"[VT] Profit: ${s['profit']:.2f} ({s['profit_pct']}%)")
    logger.info(f"[VT] Win Rate: {s['wr']}%")
    logger.info(f"[VT] Total trades: {s['total']}")
