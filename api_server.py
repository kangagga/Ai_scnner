# ============================================================
#  api_server.py  –  Flask API untuk Live Dashboard
# ============================================================

import logging
import threading
from datetime import datetime
from flask import Flask, jsonify, send_file
from database import get_recent_signals
from flask_cors import CORS

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

_state_lock   = threading.Lock()
_dashboard_data = {
    "signals"       : [],
    "last_scan"     : None,
    "scan_progress" : {"pct": 0, "current": "", "total": 0, "done": 0},
    "stats"         : {"total": 0, "buy": 0, "sell": 0, "avg_wr": 0.0, "avg_score": 0.0},
    "cooldowns"     : {},
    "logs"          : [],
    "bot_start"     : datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    "config"        : {},
}

def update_signals(signals: list):
    with _state_lock:
        _dashboard_data["signals"]   = signals
        _dashboard_data["last_scan"] = datetime.now().strftime("%H:%M:%S")
        buy  = sum(1 for s in signals if "BUY"  in s.get("signal", ""))
        sell = sum(1 for s in signals if "SELL" in s.get("signal", ""))
        wrs  = [s.get("win_rate", s.get("predicted_wr", 0)) for s in signals]
        scrs = [s.get("score", s.get("confidence", 0))      for s in signals]
        _dashboard_data["stats"] = {
            "total"    : len(signals),
            "buy"      : buy,
            "sell"     : sell,
            "avg_wr"   : round(sum(wrs) / len(wrs), 1)   if wrs  else 0.0,
            "avg_score": round(sum(scrs) / len(scrs), 1) if scrs else 0.0,
        }

def update_progress(pct: float, current: str, done: int, total: int):
    with _state_lock:
        _dashboard_data["scan_progress"] = {
            "pct"    : round(pct, 1),
            "current": current,
            "done"   : done,
            "total"  : total,
        }

def add_log(icon: str, message: str):
    with _state_lock:
        _dashboard_data["logs"].insert(0, {
            "icon"   : icon,
            "message": message,
            "time"   : datetime.now().strftime("%H:%M:%S"),
        })
        _dashboard_data["logs"] = _dashboard_data["logs"][:50]

def update_cooldowns(cooldowns: dict):
    with _state_lock:
        _dashboard_data["cooldowns"] = cooldowns

def set_config(cfg: dict):
    with _state_lock:
        _dashboard_data["config"] = cfg

import os

@app.route("/")
def index():
    base = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(base, "dashboard.html"))

@app.route("/api/signals")
def api_signals():
    from database import get_recent_signals
    with _state_lock:
        signals = _dashboard_data["signals"]
    if not signals:
        signals = get_recent_signals(limit=20)
    return jsonify(signals)
    # Kalau tidak ada sinyal live, ambil dari database
    from database import get_recent_signals
    with _state_lock:
        signals = _dashboard_data["signals"]
    if not signals:
        signals = get_recent_signals(limit=20)
    return jsonify(signals)

@app.route("/api/signals_orig")
def api_signals_orig():
    with _state_lock:
        return jsonify(_dashboard_data["signals"])

@app.route("/api/status")
def api_status():
    with _state_lock:
        return jsonify({
            "last_scan"     : _dashboard_data["last_scan"],
            "scan_progress" : _dashboard_data["scan_progress"],
            "stats"         : _dashboard_data["stats"],
            "cooldowns"     : _dashboard_data["cooldowns"],
            "logs"          : _dashboard_data["logs"],
            "bot_start"     : _dashboard_data["bot_start"],
            "config"        : _dashboard_data["config"],
        })

@app.route("/api/history")
def api_history():
    """Sinyal historis dari database."""
    try:
        signals = get_recent_signals(limit=100)
        return jsonify({"signals": signals, "total": len(signals)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stats")
def api_stats():
    """Statistik performa dari database."""
    try:
        signals = get_recent_signals(limit=200)
        if not signals:
            return jsonify({"total": 0})
        buy  = [s for s in signals if "BUY" in s.get("signal","")]
        sell = [s for s in signals if "SELL" in s.get("signal","")]
        avg_conf = sum(s.get("confidence",0) for s in signals) / len(signals)
        avg_wr   = sum(s.get("win_rate",0) for s in signals) / len(signals)
        return jsonify({
            "total"   : len(signals),
            "buy"     : len(buy),
            "sell"    : len(sell),
            "avg_conf": round(avg_conf, 1),
            "avg_wr"  : round(avg_wr, 1)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "time": datetime.now().isoformat()})

def start_api(host="0.0.0.0", port=5000):
    def _run():
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)
        app.run(host=host, port=port, debug=False, use_reloader=False)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info(f"🌐 Dashboard API berjalan di http://{host}:{port}")

@app.route("/manifest.json")
def manifest():
    return send_file("static/manifest.json", mimetype="application/manifest+json")

@app.route("/sw.js")
def service_worker():
    return send_file("static/sw.js", mimetype="application/javascript")

@app.route("/heatmap")
def heatmap():
    return send_file("static/heatmap.html")


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

        # [FIX-TZ] Equity curve 7 hari terakhir — cutoff dihitung pakai WIB
        # eksplisit di Python, bukan date('now') SQLite yang ikut timezone OS (UTC).
        from datetime import datetime, timezone as _tz, timedelta as _td
        _WIB = _tz(_td(hours=7))
        _cutoff_wib = (datetime.now(_WIB) - _td(days=7)).isoformat()
        cur.execute("""
            SELECT closed_at, balance_after FROM virtual_trades
            WHERE closed = 1 AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (_cutoff_wib,))
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


# ═══════════════════════════════════════════════════════════════════════
# ENDPOINT AI SCANNER ANDROID — READ-ONLY + KONTROL AMAN
# ═══════════════════════════════════════════════════════════════════════
# Ditambahkan untuk aplikasi Android "AI SCANNER — Full Trading Command Center".
# Semua endpoint READ-ONLY hanya membaca state/database yang sudah ada — tidak
# mengubah logic trading/risk. Endpoint KONTROL hanya mengubah flag aman di
# risk_manager (paused / trading_halted) yang memang sudah dipakai engine untuk
# memblokir trade baru, wajib header X-API-Key, dan dicatat ke audit_log/.
# ═══════════════════════════════════════════════════════════════════════

from flask import request as _flask_request
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

_WIB2 = _tz(_td(hours=7))

# Kunci kontrol HANYA dari environment. TIDAK ada fallback bawaan.
# Jika AI_SCANNER_API_KEY tidak dikonfigurasi, semua endpoint kontrol
# menolak permintaan dengan status 503 (lihat _control_auth).
_CONTROL_KEY = _os.environ.get("AI_SCANNER_API_KEY", "").strip()
_CONTROL_KEY_CONFIGURED = bool(_CONTROL_KEY)


def _audit_control(action: str, detail: str = ""):
    try:
        audit_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "audit_log")
        _os.makedirs(audit_dir, exist_ok=True)
        path = _os.path.join(audit_dir, "app_control.log")
        line = f"{_dt.now(_WIB2).isoformat()} | {action} | {detail}\n"
        with open(path, "a") as f:
            f.write(line)
    except Exception:
        pass


def _control_auth():
    """Autentikasi endpoint kontrol.

    Returns (ok, status_code, message).
    - Key belum dikonfigurasi di server -> 503 (tolak semua).
    - Key salah / tidak ada -> 401.
    - Key benar -> (True, 200, "").
    Key TIDAK pernah dicetak ke log.
    """
    if not _CONTROL_KEY_CONFIGURED:
        return False, 503, "control key not configured on server"
    key = _flask_request.headers.get("X-API-Key", "")
    if key != _CONTROL_KEY:
        return False, 401, "unauthorized"
    return True, 200, ""


def _get_risk_state():
    try:
        from risk_manager import get_risk_status
        return get_risk_status(), None
    except Exception as e:
        return {}, str(e)


@app.route("/api/bot/status")
def api_bot_status():
    risk, err = _get_risk_state()
    try:
        from config import BITGET_MIRROR
    except Exception:
        BITGET_MIRROR = False
    return jsonify({
        "mode": "PAPER TRADING",
        "mirror_enabled": bool(BITGET_MIRROR),
        "running": True,
        "connected": True,
        "last_scan": _dashboard_data.get("last_scan"),
        "bot_start": _dashboard_data.get("bot_start"),
        "health": risk.get("health", "🟢 HEALTHY"),
        "balance": risk.get("balance", 0),
        "peak_balance": risk.get("peak_balance", 0),
        "drawdown_pct": risk.get("drawdown_pct", 0),
        "open_positions": risk.get("open_positions", 0),
        "total_trades": risk.get("total_trades", 0),
        "paused": bool(risk.get("trading_halted", False)),
        "halt_reason": risk.get("halt_reason", ""),
        "error": err,
    })


@app.route("/api/dashboard")
def api_dashboard():
    risk, err = _get_risk_state()
    try:
        from config import BITGET_MIRROR
    except Exception:
        BITGET_MIRROR = False

    result = {
        "bot": {
            "mode": "PAPER TRADING",
            "mirror_enabled": bool(BITGET_MIRROR),
            "running": True,
            "connected": True,
            "last_scan": _dashboard_data.get("last_scan"),
            "health": risk.get("health", "🟢 HEALTHY"),
            "paused": bool(risk.get("trading_halted", False)),
            "halt_reason": risk.get("halt_reason", ""),
        },
        "portfolio": {
            "balance": risk.get("balance", 0),
            "peak_balance": risk.get("peak_balance", 0),
            "drawdown_pct": risk.get("drawdown_pct", 0),
            "daily_pnl": risk.get("daily_pnl", 0),
            "daily_pnl_pct": risk.get("daily_pnl_pct", 0),
            "portfolio_heat": risk.get("portfolio_heat", 0),
            "consecutive_loss": risk.get("consecutive_loss", 0),
            "trading_halted": risk.get("trading_halted", False),
            "open_positions": risk.get("open_positions", 0),
            "max_positions": risk.get("max_positions", 5),
            "total_trades": risk.get("total_trades", 0),
        },
        "performance": {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "total_pnl_usd": 0.0, "profit_factor": 0.0,
            "equity_curve": [], "pnl_pct_7d": 0.0,
        },
        "signals": {
            "total": _dashboard_data.get("stats", {}).get("total", 0),
            "buy": _dashboard_data.get("stats", {}).get("buy", 0),
            "sell": _dashboard_data.get("stats", {}).get("sell", 0),
            "avg_wr": _dashboard_data.get("stats", {}).get("avg_wr", 0.0),
            "avg_score": _dashboard_data.get("stats", {}).get("avg_score", 0.0),
        },
        "error": err,
    }

    # Performance dari virtual_trading.db
    try:
        conn = _sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True, timeout=5)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END),
                   SUM(pnl_usdt),
                   SUM(CASE WHEN pnl_usdt>0 THEN pnl_usdt ELSE 0 END),
                   SUM(CASE WHEN pnl_usdt<0 THEN ABS(pnl_usdt) ELSE 0 END)
            FROM virtual_trades WHERE closed=1
        """)
        row = cur.fetchone()
        total, wins, losses, total_pnl, gp, gl = row
        total = total or 0; wins = wins or 0; losses = losses or 0
        total_pnl = total_pnl or 0.0; gp = gp or 0.0; gl = gl or 0.0
        wr = round(wins / total * 100, 1) if total > 0 else 0.0
        pf = round(gp / gl, 2) if gl > 0 else (round(gp, 2) if gp > 0 else 0.0)
        cutoff = (_dt.now(_WIB2) - _td(days=7)).isoformat()
        cur.execute("""
            SELECT closed_at, balance_after FROM virtual_trades
            WHERE closed=1 AND closed_at>=? ORDER BY closed_at ASC
        """, (cutoff,))
        curve = [{"time": r[0], "balance": r[1]} for r in cur.fetchall() if r[1] is not None]
        conn.close()
        pct = 0.0
        if curve:
            s0, s1 = curve[0]["balance"], curve[-1]["balance"]
            if s0:
                pct = round((s1 - s0) / s0 * 100, 2)
        result["performance"] = {
            "total_trades": total, "wins": wins, "losses": losses,
            "win_rate": wr, "total_pnl_usd": round(total_pnl, 2),
            "profit_factor": pf, "equity_curve": curve, "pnl_pct_7d": pct,
        }
    except Exception as e:
        result["performance"]["error"] = str(e)

    return jsonify(result)


@app.route("/api/trades")
def api_trades():
    """Jurnal trading virtual (trades closed) dari virtual_trading.db."""
    if not _os.path.exists(_DB_PATH):
        return jsonify({"trades": [], "total": 0, "note": "database belum tersedia"})
    try:
        conn = _sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True, timeout=5)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(virtual_trades)")
        cols = [r[1] for r in cur.fetchall()]
        wanted = ["id","timestamp","symbol","signal","entry","sl","tp1","tp2",
                  "tp3","exit_price","pnl_pct","pnl_usd","result","balance_after",
                  "timeframe","closed","closed_at","fees","duration_min",
                  "entry_reason","exit_reason","strategy"]
        sel = [c for c in wanted if c in cols]
        if not sel:
            conn.close()
            return jsonify({"trades": [], "total": 0})
        q = "SELECT " + ", ".join(sel) + " FROM virtual_trades ORDER BY id DESC LIMIT 200"
        cur.execute(q)
        rows = cur.fetchall()
        conn.close()
        trades = []
        for r in rows:
            d = dict(zip(sel, r))
            trades.append({
                "id": d.get("id"),
                "pair": d.get("symbol"),
                "timeframe": d.get("timeframe"),
                "signal": d.get("signal"),
                "entry": d.get("entry"),
                "sl": d.get("sl"),
                "tp1": d.get("tp1"),
                "tp2": d.get("tp2"),
                "tp3": d.get("tp3"),
                "exit_price": d.get("exit_price"),
                "pnl_pct": d.get("pnl_pct"),
                "pnl_usd": d.get("pnl_usd"),
                "result": d.get("result"),
                "balance_after": d.get("balance_after"),
                "opened_at": d.get("timestamp"),
                "closed_at": d.get("closed_at"),
                "fees": d.get("fees", 0),
                "duration_min": d.get("duration_min"),
                "entry_reason": d.get("entry_reason", ""),
                "exit_reason": d.get("exit_reason", ""),
                "strategy": d.get("strategy", d.get("signal", "")),
            })
        return jsonify({"trades": trades, "total": len(trades)})
    except Exception as e:
        return jsonify({"error": str(e), "trades": [], "total": 0}), 500


@app.route("/api/market-analysis")
def api_market_analysis():
    """Analisis market real (regime, BTC trend, fear&greed) + penjelasan AI."""
    try:
        from market_context import get_market_context
        ctx = get_market_context()
    except Exception as e:
        ctx = {"error": str(e)}

    btc = ctx.get("btc_trend", {}) if isinstance(ctx.get("btc_trend"), dict) else {}
    fg = ctx.get("fear_greed", {}) if isinstance(ctx.get("fear_greed"), dict) else {}
    overall = ctx.get("overall", "NEUTRAL")

    ai_text = ""
    try:
        from ai_analyst import analyse_market_sentiment
        sigs = _dashboard_data.get("signals", [])
        if sigs:
            ai_text = analyse_market_sentiment(sigs)
    except Exception:
        ai_text = ""

    return jsonify({
        "regime": overall,
        "bullish": overall == "BULLISH",
        "bearish": overall == "BEARISH",
        "sideways": overall == "NEUTRAL",
        "btc_trend": btc.get("trend", "N/A"),
        "btc_strength": btc.get("strength", "N/A"),
        "btc_price": btc.get("price", 0),
        "btc_adx": btc.get("adx", 0),
        "fear_greed_value": fg.get("value", 50),
        "fear_greed_label": fg.get("label", "Neutral"),
        "allow_buy": ctx.get("allow_buy", True),
        "allow_sell": ctx.get("allow_sell", True),
        "summary": ctx.get("summary", ""),
        "ai_explanation": ai_text,
        "error": ctx.get("error"),
    })


@app.route("/api/risk/status")
def api_risk_status():
    risk, err = _get_risk_state()
    return jsonify({
        "health": risk.get("health", "🟢 HEALTHY"),
        "balance": risk.get("balance", 0),
        "peak_balance": risk.get("peak_balance", 0),
        "drawdown_pct": risk.get("drawdown_pct", 0),
        "daily_pnl": risk.get("daily_pnl", 0),
        "daily_pnl_pct": risk.get("daily_pnl_pct", 0),
        "portfolio_heat": risk.get("portfolio_heat", 0),
        "consecutive_loss": risk.get("consecutive_loss", 0),
        "trading_halted": risk.get("trading_halted", False),
        "halt_reason": risk.get("halt_reason", ""),
        "open_positions": risk.get("open_positions", 0),
        "max_positions": risk.get("max_positions", 5),
        "total_trades": risk.get("total_trades", 0),
        "limits": {
            "max_drawdown_pct": 15.0,
            "max_daily_loss_pct": 5.0,
            "max_heat_pct": 20.0,
            "max_consecutive_loss": 6,
        },
        "error": err,
    })


def _control_action(action: str):
    try:
        from risk_manager import _state, resume_trading
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    if action == "pause":
        with _state._lock:
            _state.trading_halted = True
            _state.halt_reason = "DIJEDA melalui aplikasi AI Scanner"
            _state.save()
    elif action == "resume":
        resume_trading(manual=True)
    elif action == "emergency":
        with _state._lock:
            _state.trading_halted = True
            _state.halt_reason = "EMERGENCY STOP melalui aplikasi AI Scanner"
            _state.save()
    else:
        return jsonify({"ok": False, "error": "unknown action"}), 400

    _audit_control(action, f"ip={_flask_request.remote_addr}")
    return jsonify({"ok": True, "action": action})


@app.route("/api/bot/pause", methods=["POST"])
def api_bot_pause():
    ok, code, msg = _control_auth()
    if not ok:
        return jsonify({"ok": False, "error": msg}), code
    return _control_action("pause")


@app.route("/api/bot/resume", methods=["POST"])
def api_bot_resume():
    ok, code, msg = _control_auth()
    if not ok:
        return jsonify({"ok": False, "error": msg}), code
    return _control_action("resume")


@app.route("/api/bot/emergency-stop", methods=["POST"])
def api_bot_emergency():
    ok, code, msg = _control_auth()
    if not ok:
        return jsonify({"ok": False, "error": msg}), code
    return _control_action("emergency")
