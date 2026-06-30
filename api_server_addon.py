

# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT TAMBAHAN — DATA REAL UNTUK DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
# Ditambahkan untuk memperbaiki dashboard.html yang sebelumnya menampilkan
# data dummy/hardcode (Market Regime, Open Positions, Portfolio Heat,
# Streak Loss, Total PnL semuanya placeholder). Endpoint ini READ-ONLY,
# tidak mengubah logic trading/risk apapun — hanya membaca state yang sudah ada.
# ═══════════════════════════════════════════════════════════════════════════

import json as _json
import sqlite3 as _sqlite3
import os as _os

_DB_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "virtual_trading.db")
_ACTIVE_TRADES_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "active_trades.json")


@app.route("/api/portfolio")
def api_portfolio():
    """
    Data real untuk kartu stats dashboard: Open Positions, Portfolio Heat,
    Streak Loss, Trading Health — diambil dari risk_manager.get_risk_status()
    (in-memory state real-time) + detail posisi dari active_trades.json.
    """
    try:
        from risk_manager import get_risk_status
        risk = get_risk_status()
    except Exception as e:
        logger.warning(f"[API] get_risk_status error: {e}")
        risk = {}

    positions = []
    try:
        if _os.path.exists(_ACTIVE_TRADES_PATH):
            with open(_ACTIVE_TRADES_PATH, "r") as f:
                active = _json.load(f)
            for key, t in active.items():
                positions.append({
                    "key":       key,
                    "symbol":    t.get("symbol", key.split("_")[0]),
                    "timeframe": t.get("timeframe", "1h"),
                    "signal":    t.get("signal", ""),
                    "entry":     t.get("entry", 0),
                    "sl":        t.get("sl", 0),
                    "tp1":       t.get("tp1", 0),
                    "tp2":       t.get("tp2", 0),
                    "tp3":       t.get("tp3", 0),
                })
    except Exception as e:
        logger.warning(f"[API] Gagal baca active_trades.json: {e}")

    return jsonify({
        "health":           risk.get("health", "🟢 HEALTHY"),
        "balance":          risk.get("balance", 0),
        "peak_balance":     risk.get("peak_balance", 0),
        "drawdown_pct":     risk.get("drawdown_pct", 0),
        "daily_pnl_pct":    risk.get("daily_pnl_pct", 0),
        "portfolio_heat":   risk.get("portfolio_heat", 0),
        "consecutive_loss": risk.get("consecutive_loss", 0),
        "trading_halted":   risk.get("trading_halted", False),
        "halt_reason":      risk.get("halt_reason", ""),
        "open_positions":   len(positions),
        "max_positions":    risk.get("max_positions", 5),
        "total_trades":     risk.get("total_trades", 0),
        "positions":        positions,
    })


@app.route("/api/performance")
def api_performance():
    """
    Data performa real dari virtual_trading.db: win rate, total PnL,
    profit factor, dan equity curve 7 hari terakhir untuk chart dashboard.
    Menggantikan chart hardcode '+28.65%' yang sebelumnya statis.
    """
    try:
        conn = _sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True, timeout=5)
        cur = conn.cursor()

        # Statistik keseluruhan trade yang sudah closed
        cur.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END),
                   SUM(pnl_usdt),
                   SUM(CASE WHEN pnl_usdt > 0 THEN pnl_usdt ELSE 0 END),
                   SUM(CASE WHEN pnl_usdt < 0 THEN ABS(pnl_usdt) ELSE 0 END)
            FROM virtual_trades WHERE closed = 1
        """)
        row = cur.fetchone()
        total, wins, losses, total_pnl, gross_profit, gross_loss = row
        total = total or 0
        wins = wins or 0
        losses = losses or 0
        total_pnl = total_pnl or 0.0
        gross_profit = gross_profit or 0.0
        gross_loss = gross_loss or 0.0

        win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (
            round(gross_profit, 2) if gross_profit > 0 else 0.0
        )

        # Equity curve 7 hari terakhir — pakai balance_after tiap trade closed
        cur.execute("""
            SELECT closed_at, balance_after FROM virtual_trades
            WHERE closed = 1 AND closed_at >= date('now', '-7 days')
            ORDER BY closed_at ASC
        """)
        curve_rows = cur.fetchall()
        equity_curve = [
            {"time": r[0], "balance": r[1]}
            for r in curve_rows if r[1] is not None
        ]

        conn.close()

        pnl_pct_from_start = 0.0
        if equity_curve:
            start_balance = equity_curve[0]["balance"]
            end_balance = equity_curve[-1]["balance"]
            if start_balance:
                pnl_pct_from_start = round((end_balance - start_balance) / start_balance * 100, 2)

        return jsonify({
            "total_trades":   total,
            "wins":           wins,
            "losses":         losses,
            "win_rate":       win_rate,
            "total_pnl_usd":  round(total_pnl, 2),
            "profit_factor":  profit_factor,
            "equity_curve":   equity_curve,
            "pnl_pct_7d":     pnl_pct_from_start,
        })
    except Exception as e:
        logger.error(f"[API] api_performance error: {e}")
        return jsonify({"error": str(e), "total_trades": 0, "win_rate": 0}), 500


@app.route("/api/market_regime")
def api_market_regime():
    """
    Market regime real (BTC trend, fear&greed) — menggantikan
    'BULLISH 78%' hardcode di dashboard.
    """
    try:
        from market_context import get_market_context
        ctx = get_market_context()
        btc_trend = ctx.get("btc_trend", {})
        fg = ctx.get("fear_greed", {})

        trend_str = btc_trend.get("trend", "NEUTRAL") if isinstance(btc_trend, dict) else str(btc_trend)
        is_bullish = "UP" in trend_str.upper()
        is_bearish = "DOWN" in trend_str.upper()

        label = "BULLISH" if is_bullish else ("BEARISH" if is_bearish else "NEUTRAL")

        return jsonify({
            "regime": label,
            "trend_raw": trend_str,
            "fear_greed_value": fg.get("value", 50) if isinstance(fg, dict) else 50,
            "fear_greed_label": fg.get("label", "Neutral") if isinstance(fg, dict) else "Neutral",
            "summary": ctx.get("summary", ""),
        })
    except Exception as e:
        logger.warning(f"[API] api_market_regime error: {e}")
        return jsonify({"regime": "NEUTRAL", "trend_raw": "NEUTRAL", "fear_greed_value": 50})
