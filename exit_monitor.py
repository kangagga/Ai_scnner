import logging
import threading
import time
import requests
from datetime import datetime
from database import update_signal_result

logger = logging.getLogger(__name__)
_active_trades = {}
_lock = threading.Lock()
_TRADES_FILE = "active_trades.json"

def _save_trades():
    import json
    try:
        with open(_TRADES_FILE, "w") as f:
            json.dump(_active_trades, f)
    except: pass

def _load_trades():
    import json, os
    global _active_trades
    if os.path.exists(_TRADES_FILE):
        try:
            with open(_TRADES_FILE) as f:
                _active_trades = json.load(f)
            logger.info(f"✅ {len(_active_trades)} trade dimuat dari file")
        except: pass

_load_trades()

def add_trade(signal: dict):
    symbol = signal.get("symbol")
    tf = signal.get("timeframe", "")
    if not symbol:
        return
    key = f"{symbol}_{tf}"
    with _lock:
        _active_trades[key] = {
            "entry": signal.get("entry", 0),
            "sl": signal.get("sl", 0),
            "tp1": signal.get("tp1", 0),
            "tp2": signal.get("tp2", 0),
            "tp3": signal.get("tp3", 0),
            "signal": signal.get("signal", ""),
            "timeframe": signal.get("timeframe", ""),
            "symbol": symbol,
        }
    logger.info(f"Monitoring exit: {symbol}")
    _save_trades()

    # Simpan ke virtual trading
    try:
        from virtual_trader import add_virtual_trade
        add_virtual_trade(signal)
    except Exception as e:
        logger.warning(f"Virtual add trade error: {e}")

def get_current_price(symbol: str) -> float:
    try:
        # Deteksi format pair — BTC pair atau USDT pair
        if symbol.endswith("BTC"):
            pair = symbol[:-3] + "_BTC"
        elif symbol.endswith("ETH"):
            pair = symbol[:-3] + "_ETH"
        elif symbol.endswith("USDT"):
            pair = symbol[:-4] + "_USDT"
        else:
            pair = symbol[:-4] + "_USDT"  # fallback
        r = requests.get("https://api.gateio.ws/api/v4/spot/tickers", params={"currency_pair": pair}, timeout=5)
        data = r.json()
        if data:
            return float(data[0].get("last", 0))
    except:
        pass
    return 0.0

_sent_exit_notif = set()  # tracking notif sudah dikirim

def check_exits(send_alert_fn):
    import copy
    with _lock:
        trades = copy.deepcopy(_active_trades)
    for key, trade in trades.items():
        symbol = trade.get("symbol", key.split("_")[0])
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

                # Normalisasi label
                if abs(pnl_pct) < 0.1:
                    label = "BREAKEVEN"
                    pnl_pct = 0.0
                elif "TP" in label and is_profit:
                    emoji_result = "💰"
                elif "STOP LOSS" in label and pnl_pct > 0:
                    label = "TRAILING STOP"
                    emoji_result = "✅"

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
            # Cek duplikat notif
            notif_key = f"{symbol}:{trade['entry']}:{label}"
            if notif_key in _sent_exit_notif:
                logger.debug(f"[EXIT DEDUP] Skip duplikat notif {notif_key}")
                continue
            _sent_exit_notif.add(notif_key)

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
                # Auto-blacklist setelah SL
                if "STOP LOSS" in label:
                    try:
                        from blacklist import report_false_signal
                        report_false_signal(symbol)
                        logger.info(f"⚠️ {symbol} dilaporkan ke blacklist setelah SL")
                    except: pass
            except Exception as e:
                logger.warning(f"Gagal simpan performance: {e}")

            # Update virtual trading
            try:
                from virtual_trader import close_virtual_trade
                new_bal, pnl_usd = close_virtual_trade(symbol, trade["signal"], price, pnl_pct)
                logger.info(f"💰 Virtual balance: ${new_bal:.2f}")
            except Exception as e:
                logger.warning(f"Virtual trade error: {e}")

            # Cooldown setelah loss
            try:
                if not is_profit:
                    from blacklist import add_loss_cooldown
                    add_loss_cooldown(symbol)
            except Exception as e:
                logger.warning(f"Cooldown error: {e}")
            with _lock:
                if key in _active_trades:
                    if "TP1" in label:
                        # Setelah TP1 kena — pindah SL ke entry (breakeven), aktifkan TP2
                        _active_trades[key]["sl"] = trade["entry"]
                        if "tp1_original" not in _active_trades[key]:
                            _active_trades[key]["tp1_original"] = trade["tp1"]  # simpan hanya sekali
                        _active_trades[key]["tp1"] = trade["tp2"]  # aktifkan TP2 sebagai target
                        _active_trades[key]["monitoring_tp"] = "TP2"
                        _save_trades()
                        logger.info(f"TP1 hit {symbol} — SL dipindah ke entry, pantau TP2")
                    elif "TP2" in label:
                        # Setelah TP2 kena — pindah SL ke TP1 lama, aktifkan TP3
                        _active_trades[key]["sl"] = trade.get("tp1_original", trade["entry"])
                        _active_trades[key]["tp1"] = trade["tp3"]  # aktifkan TP3 sebagai target
                        _active_trades[key]["monitoring_tp"] = "TP3"
                        _active_trades[key]["tp2"] = 0
                        _save_trades()
                        logger.info(f"TP2 hit {symbol} — lanjut pantau TP3")
                    else:
                        # TP3 atau SL — hapus trade
                        del _active_trades[key]
                        _save_trades()

def start_exit_monitor(send_alert_fn, interval: int = 15):
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
