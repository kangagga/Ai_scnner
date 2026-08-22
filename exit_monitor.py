import logging
import threading
import time
import requests
from datetime import datetime


logger = logging.getLogger(__name__)
_active_trades = {}
_lock = threading.Lock()
_TRADES_FILE = "active_trades.json"

def _save_trades():
    import json
    try:
        with open(_TRADES_FILE, "w") as f:
            json.dump(_active_trades, f)
    except (OSError, TypeError) as e:
        logger.warning(f"Gagal simpan {_TRADES_FILE}: {e}")

def _load_trades():
    import json, os
    global _active_trades
    if os.path.exists(_TRADES_FILE):
        try:
            with open(_TRADES_FILE) as f:
                _active_trades = json.load(f)
            logger.info(f"✅ {len(_active_trades)} trade dimuat dari file")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Gagal load {_TRADES_FILE}: {e}")

    # FIX: reconcile dengan database - tambahkan posisi yang closed=0 di DB
    # tapi hilang dari active_trades.json (misal karena crash/restart yang tidak sinkron)
    try:
        import sqlite3
        from virtual_trader import VIRTUAL_DB
        conn = sqlite3.connect(VIRTUAL_DB)
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, timeframe, signal, entry, sl, tp1, tp2, tp3, timestamp
            FROM virtual_trades WHERE closed=0
        """)
        rows = cur.fetchall()
        conn.close()

        recovered = 0
        for symbol, tf, sig, entry, sl, tp1, tp2, tp3, ts in rows:
            key = f"{symbol}_{tf}"
            if key not in _active_trades:
                _active_trades[key] = {
                    "entry": entry, "sl": sl,
                    "tp1": tp1, "tp2": tp2, "tp3": tp3,
                    "signal": sig, "timeframe": tf, "symbol": symbol,
                    "opened_at": ts or datetime.now().astimezone().isoformat(),
                }
                recovered += 1
            elif "opened_at" not in _active_trades[key]:
                _active_trades[key]["opened_at"] = ts or datetime.now().astimezone().isoformat()
        valid_keys = {f"{symbol}_{tf}" for symbol, tf, sig, entry, sl, tp1, tp2, tp3, ts in rows}
        stale_keys = [k for k in list(_active_trades.keys()) if k not in valid_keys]
        for k in stale_keys:
            del _active_trades[k]
        if stale_keys:
            logger.info(f"[RECONCILE] {len(stale_keys)} posisi basi dihapus dari active_trades: {stale_keys}")
        if recovered or stale_keys:
            logger.info(f"🔧 [RECONCILE] {recovered} posisi dipulihkan dari DB ke active_trades")
            _save_trades()
    except Exception as _e:
        logger.warning(f"[RECONCILE] Gagal sinkronisasi dengan DB: {_e}")

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
            "atr": signal.get("atr", 0),
            "trailing_stop": round(
                signal.get("entry", 0) - 2.0 * signal.get("atr", 0)
                if signal.get("signal", "").startswith("BUY")
                else signal.get("entry", 0) + 2.0 * signal.get("atr", 0), 8
            ) if signal.get("atr", 0) > 0 else signal.get("sl", 0),
            "highest_price": signal.get("entry", 0),
            "lowest_price": signal.get("entry", 0),
            "opened_at": datetime.now().astimezone().isoformat(),
        }
    logger.info(f"Monitoring exit: {symbol}")
    _save_trades()

    # Simpan ke virtual trading
    try:
        from virtual_trader import add_virtual_trade
        add_virtual_trade(signal)
    except Exception as e:
        logger.warning(f"Virtual add trade error: {e}")

def remove_trade(symbol: str, timeframe: str = ""):
    """[ADDED 2026-08-21] Hapus trade dari _active_trades saat ditutup manual
    lewat Telegram (Close Posisi). Tanpa ini, exit_monitor tetap memonitor
    harga posisi yang sudah closed=1 di virtual_trades, dan bisa mengirim
    notifikasi TP/SL palsu untuk posisi yang sudah tidak ada."""
    removed = []
    with _lock:
        if timeframe:
            key = f"{symbol}_{timeframe}"
            if key in _active_trades:
                del _active_trades[key]
                removed.append(key)
        else:
            # Timeframe tidak diketahui -> hapus semua key yang berawalan symbol_
            for key in list(_active_trades.keys()):
                if key == symbol or key.startswith(f"{symbol}_"):
                    del _active_trades[key]
                    removed.append(key)
    if removed:
        _save_trades()
        logger.info(f"[SYNC_CLOSE] Dihapus dari monitoring: {removed}")
    return removed

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
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        logger.debug(f"Gagal ambil harga: {e}")
    return 0.0

_sent_exit_notif = set()  # tracking notif sudah dikirim

def check_exits(send_alert_fn):
    import copy
    with _lock:
        trades = copy.deepcopy(_active_trades)
    MAX_HOLD_HOURS = 72  # posisi yang menggantung lebih dari ini akan dipaksa keluar

    for key, trade in trades.items():
        symbol = trade.get("symbol", key.split("_")[0])

        # [FIX 2026-07-07] Guard data korup — trade dengan signal/entry/sl kosong
        # (contoh: BTCUSDT_None yang semua field-nya null) menyebabkan
        # AttributeError berulang setiap siklus. Bersihkan otomatis + skip.
        if not trade.get("signal") or trade.get("entry") is None or trade.get("sl") is None:
            logger.warning(f"[EXIT_MONITOR] Data trade korup terdeteksi untuk key={key}, dihapus dari active_trades")
            with _lock:
                if key in _active_trades:
                    del _active_trades[key]
            _save_trades()
            continue

        price = get_current_price(symbol)
        if not price:
            logger.warning(f"[EXIT_MONITOR] Gagal ambil harga {symbol}, skip siklus ini")
            continue
        is_buy = trade["signal"].startswith("BUY")

        # Update trailing stop dinamis
        _atr = trade.get("atr", 0)
        if _atr > 0 and key in _active_trades:
            with _lock:
                if is_buy:
                    prev_high = _active_trades[key].get("highest_price", trade["entry"])
                    if price > prev_high:
                        _active_trades[key]["highest_price"] = price
                        new_trail = round(price - 2.0 * _atr, 8)
                        if new_trail > _active_trades[key]["sl"]:
                            _active_trades[key]["sl"] = new_trail
                            logger.info("[TRAIL] " + symbol + " BUY SL naik ke " + str(new_trail))
                else:
                    prev_low = _active_trades[key].get("lowest_price", trade["entry"])
                    if price < prev_low:
                        _active_trades[key]["lowest_price"] = price
                        new_trail = round(price + 2.0 * _atr, 8)
                        if new_trail < _active_trades[key]["sl"]:
                            _active_trades[key]["sl"] = new_trail
                            logger.info("[TRAIL] " + symbol + " SELL SL turun ke " + str(new_trail))
                trade = dict(_active_trades[key])

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

        # [FIX 2026-07-06] Time-based exit: posisi yang menggantung terlalu lama
        # (contoh: ACN1USDT 5 hari, XAUTUSDT/PAXGUSDT 3 hari) mengunci symbol
        # dari sinyal baru via DUPLICATE check. Paksa keluar di harga pasar
        # kalau sudah melebihi MAX_HOLD_HOURS dan belum kena SL/TP manapun.
        if hit is None:
            opened_at_str = trade.get("opened_at")
            if opened_at_str:
                try:
                    opened_at = datetime.fromisoformat(opened_at_str)
                    age_hours = (datetime.now().astimezone() - opened_at).total_seconds() / 3600
                    if age_hours >= MAX_HOLD_HOURS:
                        hit = ("TIME EXIT", price)
                        logger.info(f"[TIME EXIT] {symbol} sudah {age_hours:.1f} jam terbuka, force close")
                except ValueError as e:
                    logger.warning(f"[TIME EXIT] Gagal parse opened_at {symbol}: {e}")
        if hit:
            label, target = hit
            is_profit = False  # placeholder, dihitung ulang di bawah setelah pnl_pct final
            emoji_result = "❌"  # placeholder, dihitung ulang di bawah
            pnl_pct = round((price - trade["entry"]) / trade["entry"] * 100, 2)
            if not trade["signal"].startswith("BUY"):
                pnl_pct = -pnl_pct
            if abs(pnl_pct) < 0.1:
                label = "BREAKEVEN"
                pnl_pct = 0.0
            elif "TP" in label and is_profit:
                emoji_result = "💰"
            elif "STOP LOSS" in label and pnl_pct > 0:
                label = "TRAILING STOP"
                emoji_result = "✅"
            # FIX: hitung ulang is_profit & emoji_result dari pnl_pct AKTUAL
            is_profit = pnl_pct > 0
            if "TP" in label and is_profit:
                emoji_result = "💰"
            elif is_profit:
                emoji_result = "✅"
            else:
                emoji_result = "❌"

            # [FIX 2026-07-13] Precompute pct_closed lebih awal supaya tersedia
            # saat msg (notifikasi) dibangun; logic identik dengan blok di bawah.
            monitoring_tp = trade.get("monitoring_tp")
            if "TP1" in label:
                pct_closed = 50.0
            elif "TP2" in label:
                pct_closed = 30.0
            elif "TP3" in label:
                pct_closed = 20.0
            else:
                if monitoring_tp == "TP3":
                    pct_closed = 20.0
                elif monitoring_tp == "TP2":
                    pct_closed = 50.0
                else:
                    pct_closed = 100.0

            msg = (
                f"{emoji_result} <b>{label}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>{symbol}</b> | {trade['timeframe']}\n"
                f"📊 Sinyal : {trade['signal']}\n"
                f"💰 Entry  : {trade['entry']}\n"
                f"🎯 Target : {target}\n"
                f"📈 Harga  : {price}\n"
                f"{'🟢' if is_profit else '🔴'} PnL    : {'+' if pnl_pct > 0 else ''}{pnl_pct}% (${'+' if pnl_pct > 0 else ''}{round(25.0 * (pct_closed / 100.0) * pnl_pct / 100.0, 2)})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 AI Signal Bot"
            )

            notif_key = f"{symbol}:{trade['entry']}:{label}"
            if notif_key in _sent_exit_notif:
                logger.debug(f"[EXIT DEDUP] Skip duplikat notif {notif_key}")
                continue
            _sent_exit_notif.add(notif_key)

            send_alert_fn(msg)

            # Auto-blacklist setelah SL
            if "STOP LOSS" in label:
                try:
                    from blacklist import report_false_signal
                    report_false_signal(symbol)
                    logger.info(f"⚠️ {symbol} dilaporkan ke blacklist setelah SL")
                except Exception as e:
                    logger.warning(f"Gagal lapor blacklist {symbol}: {e}")

            # Tentukan porsi close & status final berdasarkan label & state monitoring TP
            monitoring_tp = trade.get("monitoring_tp")
            if "TP1" in label:
                pct_closed, tp_level_leg, is_final_leg = 50.0, "TP1", False
            elif "TP2" in label:
                pct_closed, tp_level_leg, is_final_leg = 30.0, "TP2", False
            elif "TP3" in label:
                pct_closed, tp_level_leg, is_final_leg = 20.0, "TP3", True
            else:
                # SL / TRAILING STOP / TIME EXIT / BREAKEVEN - tutup sisa posisi yang masih berjalan
                if monitoring_tp == "TP3":
                    pct_closed = 20.0
                elif monitoring_tp == "TP2":
                    pct_closed = 50.0
                else:
                    pct_closed = 100.0
                tp_level_leg, is_final_leg = label, True

            # Update virtual trading (balance & record otomatis)
            try:
                from virtual_trader import close_virtual_trade
                close_virtual_trade(
                    symbol=symbol,
                    timeframe=trade.get("timeframe", ""),
                    signal=trade["signal"],
                    pnl_pct=pnl_pct,
                    pct_closed=pct_closed,
                    tp_level=tp_level_leg,
                    is_final=is_final_leg
                )
                logger.info(f"💰 Trade closed: {symbol} {trade['signal']} | PnL: {pnl_pct:.2f}% | leg={tp_level_leg} pct={pct_closed}% final={is_final_leg}")
            except (ImportError, sqlite3.Error, KeyError, ValueError) as e:
                logger.error(f"Virtual trade error: {e}", exc_info=True)

            # FIX: post-mortem AI singkat untuk pembelajaran pola (non-blocking, gagal diam-diam)
            try:
                from ai_analyst import analyse_trade_postmortem
                pm_data = {
                    "symbol": symbol,
                    "timeframe": trade.get("timeframe", ""),
                    "signal": trade.get("signal", ""),
                    "entry": trade.get("entry", 0),
                    "sl": trade.get("sl", 0),
                    "exit_price": price,
                    "pnl_pct": pnl_pct,
                }
                pm_result = analyse_trade_postmortem(pm_data)
                if pm_result:
                    logger.info(f"[POSTMORTEM] {symbol}: {pm_result}")
            except Exception as _e:
                logger.warning(f"[POSTMORTEM] Error {symbol}: {_e}")

            # Cooldown setelah loss
            try:
                if not is_profit:
                    from blacklist import add_loss_cooldown
                    add_loss_cooldown(symbol)
            except (ImportError, sqlite3.Error, KeyError) as e:
                logger.warning(f"Cooldown error: {e}", exc_info=True)

            with _lock:
                if key in _active_trades:
                    if "TP1" in label:
                        _active_trades[key]["sl"] = trade["entry"]
                        if "tp1_original" not in _active_trades[key]:
                            _active_trades[key]["tp1_original"] = trade["tp1"]
                        _active_trades[key]["tp1"] = trade["tp2"]
                        _active_trades[key]["monitoring_tp"] = "TP2"
                        _save_trades()
                        logger.info(f"TP1 hit {symbol} — SL dipindah ke entry, pantau TP2")
                    elif "TP2" in label:
                        _active_trades[key]["sl"] = trade.get("tp1_original", trade["entry"])
                        _active_trades[key]["tp1"] = trade["tp3"]
                        _active_trades[key]["monitoring_tp"] = "TP3"
                        _active_trades[key]["tp2"] = 0
                        _save_trades()
                        logger.info(f"TP2 hit {symbol} — lanjut pantau TP3")
                    else:
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
