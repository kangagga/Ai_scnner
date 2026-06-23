#!/usr/bin/env python3
# ============================================================
#  main.py  –  AI Crypto Signal Bot  (+ Position Sizing v2)
# ============================================================

import logging
import os
import sys
import time
import schedule
from datetime import datetime, timezone

# ── PID LOCK — cegah 2 instance bot jalan bersamaan ──
LOCK_FILE = "/home/userland/ai-scanner/bot.lock"

def _check_single_instance():
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r") as f:
            old_pid = f.read().strip()
        try:
            os.kill(int(old_pid), 0)  # cek apakah PID masih hidup
            print(f"❌ Bot sudah jalan dengan PID {old_pid}. Hentikan dulu sebelum menjalankan instance baru.")
            sys.exit(1)
        except (OSError, ValueError):
            pass  # PID lama tidak aktif, lock basi — boleh lanjut
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def _release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass

import atexit
_check_single_instance()
atexit.register(_release_lock)

from config          import SCAN_INTERVAL, SIGNAL_THRESHOLD, MIN_SCORE, MAX_SIGNALS_PER_DAY, \
                             DAILY_REPORT_HOUR, DAILY_REPORT_MINUTE
from scanner         import scan_all, scan_all_fast, get_top_signals, get_dynamic_threshold
from backtester      import run_backtest_multi
from ai_analyst      import analyse_market_sentiment, filter_signals_ai
from market_context  import get_market_context
from telegram_sender import send_top_signals, send_daily_report, send_test_message, send_alert, handle_commands, \
                             LAST_SIGNALS, COOLDOWN_MINUTES
from email_reporter  import send_email_report
from database        import save_signal, get_today_signals
from exit_monitor    import add_trade, start_exit_monitor
from api_server      import start_api, update_signals, add_log, \
                             update_cooldowns, set_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("signal_bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("main")

_last_signals: list = []
_daily_signal_count: int = 0
_daily_reset_date = datetime.now().date()


# ════════════════════════════════════════════════════════════
# POSITION SIZING & CORRELATION FILTER FUNCTIONS
# ════════════════════════════════════════════════════════════

def filter_correlated_signals(signals, max_total=5, max_same_direction=3):
    """
    Filter signals:
    1. Max 5 posisi aktif total
    2. Max 3 arah sama (BUY atau SELL)
    3. Hindari pair highly correlated (cluster)
    4. Prioritas score tertinggi
    """
    if not signals:
        return []

    CORR_CLUSTERS = {
        "L1":     ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","AVAXUSDT","DOTUSDT"],
        "DEFI":   ["AAVEUSDT","UNIUSDT","CRVUSDT","MKRUSDT","COMPUSDT"],
        "MEME":   ["DOGEUSDT","SHIBUSDT","PEPEUSDT","FLOKIUSDT"],
        "LAYER2": ["MATICUSDT","ARBUSDT","OPUSDT","LRCUSDT"],
    }
    MAX_PER_CLUSTER = 2

    signals = sorted(signals, key=lambda x: x.get("score", x.get("confidence", 0)), reverse=True)

    selected = []
    cluster_count = {k: 0 for k in CORR_CLUSTERS}
    buy_count = 0
    sell_count = 0

    for sig in signals:
        if len(selected) >= max_total:
            break

        sym = sig.get("symbol", "").replace("/", "")
        direction = "BUY" if sig.get("signal", "").startswith("BUY") else "SELL"

        if direction == "BUY" and buy_count >= max_same_direction:
            continue
        if direction == "SELL" and sell_count >= max_same_direction:
            continue

        in_cluster = None
        for cname, members in CORR_CLUSTERS.items():
            if sym in members:
                in_cluster = cname
                break

        if in_cluster and cluster_count[in_cluster] >= MAX_PER_CLUSTER:
            continue

        selected.append(sig)
        if in_cluster:
            cluster_count[in_cluster] += 1
        if direction == "BUY":
            buy_count += 1
        else:
            sell_count += 1

    logger.info(f"[CORR] {len(selected)}/{len(signals)} sinyal lolos korelasi filter")
    return selected

def calculate_correlation_exposure(signals):
    """Hitung exposure weight berdasarkan confidence & jumlah signals"""
    if not signals:
        return {}
    
    num_signals = len(signals)
    confidences = [s.get("confidence", 0) for s in signals]
    max_conf = max(confidences) if confidences else 1
    min_conf = min(confidences) if confidences else 0
    conf_range = max_conf - min_conf if max_conf > min_conf else 1
    
    sizing = {}
    total_weight = 0
    
    for signal in signals:
        symbol = signal["symbol"]
        conf = signal.get("confidence", 0)
        
        norm_conf = (conf - min_conf) / conf_range if conf_range > 0 else 0.5
        weight = norm_conf / (num_signals ** 0.5)
        sizing[symbol] = weight
        total_weight += weight
    
    if total_weight > 0:
        sizing = {k: v / total_weight for k, v in sizing.items()}
    
    return sizing


def calculate_position_sizes(signals, total_risk_capital=100, min_size=1.0):
    """Convert correlation exposure ke actual position sizes (dollar amount)"""
    exposure = calculate_correlation_exposure(signals)
    
    positions = {}
    for symbol, weight in exposure.items():
        size = max(total_risk_capital * weight, min_size)
        positions[symbol] = size
    
    return positions


# ════════════════════════════════════════════════════════════
# DYNAMIC RISK ADJUSTMENT PER MARKET REGIME
# ════════════════════════════════════════════════════════════

def get_regime_risk_multiplier(market_context):
    """
    Get position size multiplier based on market regime
    
    Args:
        market_context: dict dari get_market_context()
    
    Return: float multiplier (0.25 to 1.0)
    """
    
    if not market_context:
        return 1.0
    
    btc_trend = market_context.get('btc_trend', 'RANGING')
    volatility = market_context.get('volatility', 'NORMAL')
    
    if btc_trend == 'UPTREND':
        multiplier = 1.0
    elif btc_trend == 'DOWNTREND':
        multiplier = 1.0
    else:
        multiplier = 0.5
    
    if volatility == 'HIGH':
        multiplier *= 0.5
    elif volatility == 'EXTREME':
        multiplier *= 0.25
    
    multiplier = max(0.1, min(1.0, multiplier))
    
    return multiplier


def apply_regime_risk_adjustment(positions, market_context):
    """
    Apply regime-based risk adjustment ke position sizes
    """
    
    multiplier = get_regime_risk_multiplier(market_context)
    
    if multiplier == 1.0:
        return positions
    
    adjusted = {}
    for symbol, size in positions.items():
        adjusted[symbol] = size * multiplier
    
    logger.info(f"🎚️  Regime Risk Multiplier: {multiplier:.1%}")
    
    return adjusted


# ════════════════════════════════════════════════════════════
# MAIN JOB FUNCTIONS
# ════════════════════════════════════════════════════════════

def _build_cooldown_info() -> dict:
    """Ambil sisa cooldown per simbol"""
    from datetime import timedelta
    now  = datetime.now(timezone.utc)
    result = {}
    for sym, data in LAST_SIGNALS.items():
        elapsed  = (now - data["time"]).total_seconds() / 60.0
        remaining = round(COOLDOWN_MINUTES - elapsed)
        if remaining > 0:
            result[sym] = remaining
    return result


def job_scan():
    """Main scanning job dengan correlation filter + position sizing + regime adjustment"""
    global _last_signals, _daily_signal_count, _daily_reset_date
    
    now_str = datetime.now().strftime("%H:%M:%S")
    logger.info(f"🔍 Scan dimulai — {now_str}")
    add_log("🔍", f"Scan dimulai — {now_str}")

    # ── Self-Learning: retrain XGB + update analysis setiap 20 trade baru ──
    try:
        from self_learning import run_self_learning
        run_self_learning(retrain_every_n=20)
    except Exception as _sl_e:
        logger.debug(f"[SELF-LEARN] error: {_sl_e}")


    try:
        # GET MARKET CONTEXT
        market_ctx = get_market_context()
        
        # STEP 1: Scan semua signals
        all_sig = scan_all_fast(min_score=MIN_SCORE)

        # Auto-Adaptive: filter per signal_type
        filtered_by_threshold = []
        for _s in all_sig:
            sig_type = _s.get("signal", "")
            dyn_thr  = get_dynamic_threshold(market_ctx, signal_type=sig_type)
            _s["dynamic_threshold"] = dyn_thr
            if _s.get("confidence", 0) >= dyn_thr:
                filtered_by_threshold.append(_s)

        dyn_threshold = get_dynamic_threshold(market_ctx)
        top_sig = get_top_signals(filtered_by_threshold, threshold=0)

        for _s in top_sig:
            _s["dynamic_threshold"] = _s.get("dynamic_threshold", dyn_threshold)

        if not top_sig:
            logger.info("⚠️  Tidak ada signals")
            update_signals([])
            return

        # STEP 2: Filter correlation — Trend-Following Strategy
        btc_raw = market_ctx.get("btc_trend", {})
        btc_trend = btc_raw.get("trend", "") if isinstance(btc_raw, dict) else str(btc_raw)
        btc_upper = btc_trend.upper()

        if "UPTREND" in btc_upper:
            # BTC naik → dominan BUY, SELL hanya kalau score sangat tinggi
            top_sig = [s for s in top_sig if
                       s.get("signal","").startswith("BUY") or
                       s.get("confidence", 0) >= 80]
            max_buy, max_sell = 3, 1
        elif "DOWNTREND" in btc_upper:
            # BTC turun → dominan SELL, BUY hanya kalau score sangat tinggi
            top_sig = [s for s in top_sig if
                       s.get("signal","").startswith("SELL") or
                       s.get("confidence", 0) >= 80]
            max_buy, max_sell = 1, 3
        else:
            # SIDEWAYS → seimbang tapi ketat
            max_buy, max_sell = 2, 2

        # Apply rasio BUY/SELL
        buys  = [s for s in top_sig if s.get("signal","").startswith("BUY")][:max_buy]
        sells = [s for s in top_sig if s.get("signal","").startswith("SELL")][:max_sell]
        top_sig = buys + sells

        filtered_sig = filter_correlated_signals(top_sig, max_total=max_buy+max_sell)
        logger.info(f"📊 Signal Filter: {len(top_sig)} -> {len(filtered_sig)}")
        
        # STEP 3: Calculate position sizes (base)
        positions = calculate_position_sizes(filtered_sig, total_risk_capital=100, min_size=1.0)
        
        # STEP 4: Apply regime-based risk adjustment
        positions = apply_regime_risk_adjustment(positions, market_ctx)
        
        # STEP 5: Attach position size ke setiap signal
        for sig in filtered_sig:
            sig['position_size'] = positions.get(sig['symbol'], 0)
        
        # Log position sizing
        logger.info("📈 POSITION SIZING:")
        total_size = 0
        for sig in filtered_sig:
            symbol = sig['symbol']
            conf = sig['confidence']
            size = sig['position_size']
            pct = (size / 100) * 100
            logger.info(f"  {symbol:12} | Conf: {conf:6.2f} | Size: ${size:7.2f} ({pct:5.1f}%)")
            total_size += size
        logger.info(f"  Total Allocated: ${total_size:.2f}")

        _last_signals = filtered_sig
        update_signals(filtered_sig if filtered_sig else [])
        update_cooldowns(_build_cooldown_info())

        today = datetime.now().date()
        if _daily_reset_date != today:
            _daily_signal_count = 0
            _daily_reset_date = today

        if filtered_sig:
#            sisa = MAX_SIGNALS_PER_DAY - _daily_signal_count
#            if sisa <= 0:
#                logger.warning(f"⚠️ Max sinyal harian ({MAX_SIGNALS_PER_DAY}) tercapai, skip.")
#                filtered_sig = []
#            else:
#                filtered_sig = filtered_sig[:sisa]
            
            _daily_signal_count += len(filtered_sig)  # unlimited
            logger.info(f"📊 Sinyal hari ini: {_daily_signal_count}/{MAX_SIGNALS_PER_DAY}")

            if filtered_sig:
                # Filter sinyal untuk virtual trade dulu
                trade_sigs = [s for s in filtered_sig if s.get('confidence', 0) >= 55 and (s.get('win_rate', 0) >= 45 or s.get('win_rate', 0) == 0)]

                # FIX: tandai sinyal yang sebenarnya duplicate (posisi sudah terbuka) SEBELUM kirim notif
                try:
                    from virtual_trader import is_duplicate_position
                    for _sig in trade_sigs:
                        _sig['is_duplicate'] = is_duplicate_position(
                            _sig.get('symbol'), _sig.get('timeframe'), _sig.get('signal')
                        )
                except Exception as _e:
                    logger.warning(f"[DUP_CHECK] Error tandai duplicate: {_e}")
                logger.info(f"📡 {len(trade_sigs)}/{len(filtered_sig)} sinyal memenuhi syarat trade")
                if trade_sigs:
                    add_log("📡", f"{len(trade_sigs)} sinyal dikirim ke Telegram (conf>=60, WR>=50%)")
                    send_top_signals(trade_sigs)
                else:
                    logger.info("Tidak ada sinyal yang memenuhi syarat trade, skip Telegram")

                # Simpan sinyal ke database agar histori tidak hilang
                for sig in filtered_sig:
                    try:
                        save_signal(sig)
                    except Exception as e:
                        logger.warning(f"[SAVE_SIGNAL] Error simpan {sig.get('symbol','?')}: {e}")
            # Virtual Trade - eksekusi sinyal yang memenuhi threshold
            # Threshold: conf >= 55, WR >= 45% ATAU WR == 0 (data tidak cukup)
            try:
                from virtual_trader import add_virtual_trade
                from exit_monitor import add_trade as exit_add_trade
                from risk_manager import check_risk_approval
                for sig in filtered_sig:
                    conf = sig.get("confidence", 0)
                    wr = sig.get("win_rate", 0)
                    if conf >= 55 and (wr >= 45 or wr == 0):
                        risk_check = check_risk_approval(
                            symbol=sig.get("symbol"),
                            timeframe=sig.get("timeframe"),
                            signal=sig.get("signal"),
                            entry=sig.get("entry", 0),
                            sl=sig.get("sl", 0),
                            win_rate=wr,
                            wr_is_default=(wr == 0),
                        )
                        if not risk_check.get("approved"):
                            logger.info(f"[RISK_BLOCKED] {sig.get('symbol')}: {risk_check.get('reasons')}")
                            continue
                        add_virtual_trade(sig)
                        exit_add_trade(sig)  # pantau TP/SL oleh exit_monitor
                        logger.info(f"[TRADE] {sig["symbol"]} {sig["signal"]} conf={conf} WR={wr}%")
            except Exception as e:
                logger.warning(f"[TRADE] Error: {e}")

    except Exception as e:
        logger.error(f"❌ Error di job_scan: {e}", exc_info=True)
        add_log("❌", f"Error: {e}")


def job_daily_report():
    """Generate daily report"""
    logger.info("📊 Generating daily report...")
    try:
        signals = get_today_signals()
        try:
            ai_analysis = analyse_market_sentiment(signals) if signals else "Tidak ada sinyal aktif hari ini."
        except Exception as _e:
            logger.warning(f"[DAILY_REPORT] ai_analysis gagal: {_e}")
            ai_analysis = "Analisa AI tidak tersedia."

        send_daily_report(signals, ai_analysis)

        try:
            send_email_report(signals, ai_analysis)
            logger.info("📧 Email report terkirim")
        except Exception as _e:
            logger.error(f"❌ Error kirim email report: {_e}")
    except Exception as e:
        logger.error(f"❌ Error di job_daily_report: {e}")


def job_weekly_report():
    """Generate weekly report"""
    logger.info("📈 Generating weekly report...")
    try:
        send_alert("📈 Weekly Report Generated")
    except Exception as e:
        logger.error(f"❌ Error di job_weekly_report: {e}")


def job_health_check():
    """Health check every 6 hours - jalankan audit lengkap"""
    logger.info("💚 Health check dimulai...")
    try:
        from bot_auditor import run_audit
        run_audit()
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")

    # Auto-blacklist pair konsisten loss
    try:
        from auto_blacklist import run_auto_blacklist
        bl_result = run_auto_blacklist()
        if bl_result["blacklisted"]:
            logger.warning(f"[AUTO-BL] Diblacklist: {bl_result['blacklisted']}")
    except Exception as e:
        logger.error(f"❌ Auto-blacklist error: {e}")


def run_startup_backtest(send_telegram: bool = True):
    """Jalankan backtest 30 hari untuk top 10 pair saat bot start."""
    from config import WATCHLIST

    symbols = WATCHLIST[:10]
    print("\n🔬 Menjalankan backtest startup...")

    try:
        df = run_backtest_multi(symbols, timeframe="1h", days=30, min_confidence=45)
        
        if df is None or len(df) == 0:
            print("⚠️  Backtest: tidak ada trade ditemukan")
            return

        avg_wr  = round(df["win_rate"].mean(), 1)
        avg_pnl = round(df["total_pnl_pct"].mean(), 2)
        best    = df.sort_values("win_rate", ascending=False).iloc[0]
        worst   = df.sort_values("win_rate").iloc[0]

        report = (
            f"🔬 *Backtest Startup (30 hari, 1h)*\n"
            f"{'─'*30}\n"
            f"📊 Pair diuji : {len(df)}\n"
            f"🎯 Avg Win Rate : {avg_wr}%\n"
            f"💰 Avg PnL : {avg_pnl:+.2f}%\n\n"
            f"🏆 Best : {best['symbol']} WR={best['win_rate']}% PnL={best['total_pnl_pct']:+.2f}%\n"
            f"⚠️  Worst: {worst['symbol']} WR={worst['win_rate']}% PnL={worst['total_pnl_pct']:+.2f}%\n"
            f"{'─'*30}\n"
        )

        report += "*Top 5 Pair:*\n"
        for _, row in df.sort_values("win_rate", ascending=False).head(5).iterrows():
            report += f"  • {row['symbol']}: WR={row['win_rate']}% | {row['total_trades']} trades | PnL={row['total_pnl_pct']:+.2f}%\n"

        print(report)

        if send_telegram:
            send_alert(report)

    except Exception as e:
        print(f"❌ Backtest error: {e}")


def main():
    """Main bot"""
    logger.info("="*60)
    logger.info("🤖 AI Crypto Signal Bot STARTED (v2 + Dynamic Risk)")
    logger.info("="*60)

    import threading
    
    em_thread = threading.Thread(target=start_exit_monitor, args=(send_alert,), daemon=True)
    em_thread.start()

    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    logger.info("🌐 Dashboard: http://localhost:5000")
    add_log("🌐", "Dashboard API aktif di port 5000")

    send_test_message()
    add_log("✅", "Bot aktif, Telegram terhubung")

    bt_thread = threading.Thread(target=run_startup_backtest, args=(True,), daemon=True)
    bt_thread.start()
    add_log("🔬", "Backtest startup berjalan di background")

    schedule.every(SCAN_INTERVAL).seconds.do(job_scan)
    daily_time = f"{DAILY_REPORT_HOUR:02d}:{DAILY_REPORT_MINUTE:02d}"
    schedule.every().day.at(daily_time).do(job_daily_report)
    schedule.every().monday.at("08:00").do(job_weekly_report)
    schedule.every(6).hours.do(job_health_check)
    schedule.every().day.at("03:00").do(lambda: __import__("database").cleanup_old_data())

    logger.info("🔄 Bot berjalan. Ctrl+C untuk stop.")
    
    try:
        import telegram_sender as _ts
        import requests as _req

        try:
            _r = _req.get(f"https://api.telegram.org/bot{__import__('config').BOT_TOKEN}/getUpdates", 
                          params={"limit": 1, "offset": -1})
            _res = _r.json().get("result", [])
            if _res:
                _ts._last_update_id = _res[-1]["update_id"]
        except Exception:
            pass

        def _cmd_loop():
            while True:
                try:
                    handle_commands(scan_fn=job_scan)
                except Exception:
                    pass
                time.sleep(5)

        threading.Thread(target=_cmd_loop, daemon=True).start()

        while True:
            schedule.run_pending()
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Bot dihentikan.")


if __name__ == "__main__":
    main()
