from flask import Flask, jsonify
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)

@app.route("/status")
def status():
    return jsonify({
        "bot_status": "ONLINE",
        "market_regime": "BULLISH",
        "open_positions": 4,
        "portfolio_heat": 3.2,
        "streak_loss": 0
    })

@app.route("/signals")
def signals():
    with open("signals.json") as f:
        data = json.load(f)
    return jsonify(data)

@app.route("/logs")
def logs():
    with open("logs.json") as f:
        data = json.load(f)
    return jsonify(data)

@app.route("/progress")
def progress():
    with open("progress.json") as f:
        data = json.load(f)
    return jsonify(data)

app.run(host="0.0.0.0", port=5001)
