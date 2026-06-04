import logging
import threading
import time
import requests
from datetime import datetime
from database import update_signal_result

logger = logging.getLogger(__name__)
_active_trades = {}
_lock = threading.Lock()

def add_trade(signal: dict):
    symbol = signal.get("symbol")
    if not symbol:
        return
    with _lock:
        _active_trades[symbol] = {
            "entry": signal.get("entry", 0),
            "sl": signal.get("sl", 0),
            "tp1": signal.get("tp1", 0),
            "tp2": signal.get("tp2", 0),
            "tp3": signal.get("tp3", 0),
            "signal": signal.get("signal", ""),
            "timeframe": signal.get("timeframe", ""),
        }
    logger.info(f"Monitoring exit: {symbol}")

def get_current_price(symbol: str) -> float:
    try:
        pair = symbol[:-4] + "_USDT"
        r = requests.get("https://api.gateio.ws/api/v4/spot/tickers", params={"currency_pair": pair}, timeout=5)
        data = r.json()
        if data:
            return float(data[0].get("last", 0))
    except:
        pass
    return 0.0

def check_exits(send_alert_fn):
    with _lock:
        trades = dict(_active_trades)
    for symbol, trade in trades.items():
        price = get_current_price(symbol)
        if not price:
            continue
        is_buy = trade["signal"].startswith("BUY")
        hit = None
        if is_buy:
            if price <= trade["sl"]:
                hit = ("STOP LOSS", trade["sl"])
            elif price >= trade["tp3"] > 0:
                hit = ("TP3 HIT", trade["tp3"])
            elif price >= trade["tp2"] > 0:
                hit = ("TP2 HIT", trade["tp2"])
            elif price >= trade["tp1"] > 0:
                hit = ("TP1 HIT", trade["tp1"])
        else:
            if price >= trade["sl"]:
                hit = ("STOP LOSS", trade["sl"])
            elif price <= trade["tp3"] > 0:
                hit = ("TP3 HIT", trade["tp3"])
            elif price <= trade["tp2"] > 0:
                hit = ("TP2 HIT", trade["tp2"])
            elif price <= trade["tp1"] > 0:
                hit = ("TP1 HIT", trade["tp1"])
        if hit:
            label, target = hit
            is_profit = "SL" not in label
            emoji_result = "✅" if is_profit else "❌"
            pnl_pct = round((price - trade["entry"]) / trade["entry"] * 100, 2)
            if not trade["signal"].startswith("BUY"):
                pnl_pct = -pnl_pct

            msg = (
                f"{emoji_result} <b>{label}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>{symbol}</b> | {trade['timeframe']}\n"
                f"📊 Sinyal : {trade['signal']}\n"
                f"💰 Entry  : {trade['entry']}\n"
                f"🎯 Target : {target}\n"
                f"📈 Harga  : {price}\n"
                f"{'🟢' if is_profit else '🔴'} PnL    : {'+' if pnl_pct > 0 else ''}{pnl_pct}%\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 AI Signal Bot"
            )
            send_alert_fn(msg)
            # Simpan hasil ke database
            try:
                update_signal_result(
                    symbol     = symbol,
                    signal     = trade["signal"],
                    entry      = trade["entry"],
                    exit_price = price,
                )
                logger.info(f"✅ Performance tersimpan: {symbol} {label} @ {price}")
            except Exception as e:
                logger.warning(f"Gagal simpan performance: {e}")
            with _lock:
                if symbol in _active_trades:
                    del _active_trades[symbol]

def start_exit_monitor(send_alert_fn, interval: int = 60):
    def _run():
        while True:
            try:
                check_exits(send_alert_fn)
            except Exception as e:
                logger.warning(f"exit_monitor error: {e}")
            time.sleep(interval)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info("Exit monitor started")
