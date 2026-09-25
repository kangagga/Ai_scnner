"""
Trade Features — logging fitur mentah per trade untuk analisis PHASE 3+.
[NEW 2026-09-21] Hasil audit: sebelumnya cuma WIN/LOSS+pnl_pct yang tersimpan,
tidak ada fitur mentah (RSI, ATR, jarak S/R, dst) maupun MAE/MFE. Tanpa ini
mustahil membedakan "SL terlalu ketat" vs "sinyal awal salah arah".
Tabel terpisah dari virtual_trades -- tidak mengubah skema/query yang sudah ada.
Berlaku untuk SEMUA jenis sinyal (SR/SETUP/MOMENTUM/BREAKOUT), bukan cuma MOMENTUM.
"""
import sqlite3, logging

logger = logging.getLogger(__name__)
FEATURES_DB = "/home/userland/ai-scanner/virtual_trading.db"

def init_features_db():
    conn = sqlite3.connect(FEATURES_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_features (
            trade_id INTEGER PRIMARY KEY,
            price_change_3 REAL, rvol REAL, rsi REAL, adx REAL,
            ema200_aligned INTEGER,
            dist_to_resistance_pct REAL, dist_to_support_pct REAL,
            atr REAL, atr_extension REAL, squeeze_score REAL,
            candle_body_ratio REAL, candle_close_location REAL,
            liq_score INTEGER, slippage_est REAL,
            mae_pct REAL DEFAULT 0, mfe_pct REAL DEFAULT 0,
            market_regime TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_features(trade_id: int, sig: dict):
    """Simpan fitur mentah saat trade dibuka. Dipanggil dari add_virtual_trade()
    setelah trade_id baru diketahui. Gagal di sini TIDAK boleh menggagalkan
    penyimpanan trade utama -- selalu dibungkus try/except di sisi pemanggil."""
    init_features_db()

    entry = sig.get("entry", 0)
    resistance = sig.get("resistance", 0)
    support = sig.get("support", 0)
    atr = sig.get("atr", 0)
    close = entry  # candle saat sinyal, close ~ entry
    signal = sig.get("signal", "")

    dist_res_pct = round(abs(entry - resistance) / entry * 100, 3) if entry and resistance else 0
    dist_sup_pct = round(abs(entry - support) / entry * 100, 3) if entry and support else 0

    price_change_3 = sig.get("price_change_3", 0)
    atr_extension = round(abs(price_change_3) / atr, 3) if atr else 0

    ema_trend = sig.get("ema_trend", "")
    is_buy = signal.startswith("BUY")
    # ema_trend biasanya string spt "Above EMA200"/"Below EMA200" -- deteksi kasar
    ema_above = "above" in str(ema_trend).lower() or "🔼" in str(ema_trend)
    ema_aligned = 1 if (is_buy and ema_above) or (not is_buy and not ema_above) else 0

    conn = sqlite3.connect(FEATURES_DB)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO trade_features
        (trade_id, price_change_3, rvol, rsi, adx, ema200_aligned,
         dist_to_resistance_pct, dist_to_support_pct, atr, atr_extension, squeeze_score,
         candle_body_ratio, candle_close_location, liq_score, slippage_est,
         market_regime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_id, price_change_3, sig.get("volume_ratio", 0),
        sig.get("rsi", 0), sig.get("adx", 0), ema_aligned,
        dist_res_pct, dist_sup_pct, atr, atr_extension, sig.get("squeeze_score", 0),
        sig.get("body_ratio", 0), 0,  # candle_close_location: belum dihitung, TODO
        sig.get("liq_score", 5), sig.get("slippage_est", 0),
        sig.get("regime", "NEUTRAL"),
    ))
    conn.commit()
    conn.close()

def update_mae_mfe(trade_id: int, mae_pct: float, mfe_pct: float):
    """Update MAE/MFE selama trade masih open. Dipanggil dari exit_monitor
    tiap siklus check_exits(). Simpan nilai EKSTREM (paling jauh tercatat)."""
    conn = sqlite3.connect(FEATURES_DB)
    cur = conn.cursor()
    cur.execute("""
        UPDATE trade_features SET
            mae_pct = MIN(mae_pct, ?),
            mfe_pct = MAX(mfe_pct, ?)
        WHERE trade_id = ?
    """, (mae_pct, mfe_pct, trade_id))
    conn.commit()
    conn.close()
