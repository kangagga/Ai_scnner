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
