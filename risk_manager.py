# ============================================================
#  risk_manager.py  – Risk Management Otomatis
#  PERBAIKAN v2:
#  1. ACCOUNT_BALANCE diimport dari config (tidak hardcode)
#  2. Filter win rate skip jika is_default=True (data tidak cukup)
#  3. Win rate threshold diturunkan sedikit: 35 → 30
#  4. Tambah "skip_wr_filter" di return agar scanner tahu
#  5. Portfolio heat dihitung ulang saat check (bukan stale)
#  6. Tambah reset_positions() untuk debugging
# ============================================================
import logging
import json
import threading
import os
import sqlite3
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Optional

# Path ke database virtual trading (untuk persistensi)
VIRTUAL_TRADING_DB = os.path.join(os.path.dirname(__file__), "virtual_trading.db")
WIB = timezone(timedelta(hours=7))

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
#  Import konfigurasi dari config.py (TIDAK hardcode lagi)
# ------------------------------------------------------------------
try:
    from config import ACCOUNT_BALANCE, RISK_PER_TRADE
except ImportError:
    ACCOUNT_BALANCE  = 100.0
    RISK_PER_TRADE   = 1.0
    logger.warning("config.py tidak ditemukan, pakai nilai default")

# ------------------------------------------------------------------
#  Konfigurasi risk
# ------------------------------------------------------------------
MAX_RISK_PER_TRADE   = 2.0
MIN_RISK_PER_TRADE   = 0.25
KELLY_FRACTION       = 0.25
MAX_PORTFOLIO_HEAT   = 20.0  # 10 trades × 2% untuk uji bot
MAX_DAILY_LOSS_PCT   = 5.0
MAX_CONSECUTIVE_LOSS = 3
MAX_DRAWDOWN_PCT     = 15.0
STATE_FILE           = "risk_state.json"

# [FIX] Win rate threshold diturunkan sedikit
MIN_WIN_RATE_HARD    = 20.0   # reject jika win rate < 20% DAN data valid
MIN_WIN_RATE_WARN    = 45.0   # warning jika win rate < 45%


# ------------------------------------------------------------------
#  State Manager (persistent)
# ------------------------------------------------------------------
class RiskState:
    def __init__(self):
        self.balance          : float = ACCOUNT_BALANCE
        self.peak_balance     : float = ACCOUNT_BALANCE
        self.daily_pnl        : float = 0.0
        self.daily_date       : str   = str(date.today())
        self.consecutive_loss : int   = 0
        self.open_positions   : Dict  = {}
        self.total_trades     : int   = 0
        self.total_wins       : int   = 0
        self.total_losses     : int   = 0
        self.trade_history    : List  = []
        self.trading_halted   : bool  = False
        self.halt_reason      : str   = ""
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        """Load state dari database (prioritas) atau JSON fallback"""
        loaded = False
        # ── PRIORITAS: Load dari database virtual_trading ──
        try:
            if os.path.exists(VIRTUAL_TRADING_DB):
                conn = sqlite3.connect(VIRTUAL_TRADING_DB)
                cur = conn.cursor()
                cur.execute("SELECT balance, peak_balance, total_trades, total_wins, total_losses FROM virtual_balance WHERE id=1")
                row = cur.fetchone()
                if row:
                    self.balance = float(row[0])
                    self.peak_balance = float(row[1])
                    self.daily_pnl = 0.0  # reset daily dihitung ulang
                    self.daily_date = str(date.today())
                    self.consecutive_loss = 0
                    self.open_positions = {}
                    self.trading_halted = False
                    self.halt_reason = ""
                    
                    # [PATCH] Perhitungan ulang consecutive_loss dari DB dinonaktifkan
                    # consecutive_loss akan menggunakan nilai dari risk_state.json
                    # Hitung total win/loss langsung dari DB
                    cur.execute("SELECT COUNT(*), SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END), SUM(CASE WHEN pnl_usdt < 0 THEN 1 ELSE 0 END) FROM virtual_trades WHERE closed=1")
                    total, wins, losses = cur.fetchone()
                    self.total_trades = total or 0
                    self.total_wins = wins or 0
                    self.total_losses = losses or 0
                    self.trade_history = []  # akan diisi per-trade jika diperlukan nanti
                    
                    # Ambil open positions dari database
                    cur.execute("SELECT symbol, timeframe, signal, entry, sl FROM virtual_trades WHERE closed=0")
                    for sym, tf, sig, entry, sl in cur.fetchall():
                        key = f"{sym}_{tf}_{sig}"
                        # FIX: simpan risk_pct (float) bukan dict, biar konsisten dgn add_position()
                        try:
                            risk_pct = abs(entry - sl) / entry * 100 if entry else 0.0
                        except (TypeError, ZeroDivisionError):
                            risk_pct = 0.0
                        self.open_positions[key] = risk_pct
                    
                    conn.close()
                    loaded = True
                    logger.info(f"Risk state loaded from DB — Balance: ${self.balance:.2f} | Trades: {total or 0} | Open: {len(self.open_positions)}")
        except Exception as e:
            logger.warning(f"DB load failed, fallback ke JSON: {e}")
        
        # ── FALLBACK: Load dari JSON ──
        if not loaded:
            try:
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, "r") as f:
                        data = json.load(f)
                    self.balance          = data.get("balance",          ACCOUNT_BALANCE)
                    self.peak_balance     = data.get("peak_balance",     ACCOUNT_BALANCE)
                    self.daily_pnl        = data.get("daily_pnl",        0.0)
                    self.daily_date       = data.get("daily_date",       str(date.today()))
                    self.consecutive_loss = data.get("consecutive_loss", 0)
                    self.open_positions   = data.get("open_positions",   {})
                    self.trade_history    = data.get("trade_history",    [])
                    self.trading_halted   = data.get("trading_halted",   False)
                    self.halt_reason      = data.get("halt_reason",      "")
                    logger.info(f"Risk state loaded from JSON — Balance: ${self.balance:.2f}")
            except Exception as e:
                logger.warning(f"Risk state load error: {e}")

    def save(self):
        """Simpan state ke JSON + database"""
        # ── Simpan ke JSON ──
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "balance": self.balance,
                    "peak_balance": self.peak_balance,
                    "daily_pnl": self.daily_pnl,
                    "daily_date": self.daily_date,
                    "consecutive_loss": self.consecutive_loss,
                    "open_positions": self.open_positions,
                    "trade_history": self.trade_history,
                    "trading_halted": self.trading_halted,
                    "halt_reason": self.halt_reason,
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Risk state JSON save error: {e}")

        # ── Simpan ke database ──
        try:
            if os.path.exists(VIRTUAL_TRADING_DB):
                conn = sqlite3.connect(VIRTUAL_TRADING_DB)
                cur = conn.cursor()
                total_wins = 0
                total_losses = 0
                total_trades = 0
                if self.trade_history:
                    total_trades = len(self.trade_history)
                    total_wins = sum(1 for t in self.trade_history if isinstance(t, dict) and t.get("win"))
                    total_losses = total_trades - total_wins
                cur.execute("""
                    UPDATE virtual_balance SET
                        balance=?,
                        peak_balance=?,
                        total_trades=?,
                        total_wins=?,
                        total_losses=?,
                        updated_at=?
                    WHERE id=1
                """, (
                    self.balance,
                    self.peak_balance,
                    total_trades,
                    total_wins,
                    total_losses,
                    datetime.now(WIB).isoformat()
                ))
                conn.commit()
                conn.close()
        except Exception as e:
            logger.warning(f"Risk state DB save error: {e}")
    def reset_daily(self):
        with self._lock:
            today = str(date.today())
            if self.daily_date != today:
                self.daily_pnl  = 0.0
                self.daily_date = today
                if "daily" in self.halt_reason.lower():
                    self.trading_halted = False
                    self.halt_reason    = ""
                self.save()

    def update_balance(self, pnl_usdt: float, win: bool):
        with self._lock:
            self.balance   += pnl_usdt
            self.daily_pnl += pnl_usdt
            if self.balance > self.peak_balance:
                self.peak_balance = self.balance
            if win:
                self.consecutive_loss = 0
            else:
                self.consecutive_loss += 1
            self.trade_history.append({
                "time"   : datetime.now().isoformat(),
                "pnl"    : round(pnl_usdt, 4),
                "win"    : win,
                "balance": round(self.balance, 2),
            })
            self.save()

    @property
    def current_drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.balance) / self.peak_balance * 100

    @property
    def portfolio_heat(self) -> float:
        return sum(self.open_positions.values())

    def add_position(self, key: str, risk_pct: float):
        with self._lock:
            self.open_positions[key] = round(risk_pct, 2)  # fix floating point
            self.save()

    def remove_position(self, key: str):
        with self._lock:
            self.open_positions.pop(key, None)
            self.save()

    def reset_positions(self):
        """[FIX] Reset semua posisi terbuka (untuk debugging)."""
        with self._lock:
            self.open_positions = {}
            self.save()
        logger.info("Open positions di-reset.")


# Singleton state
_state = RiskState()


# ------------------------------------------------------------------
#  Kelly Criterion
# ------------------------------------------------------------------
def kelly_criterion(win_rate_pct: float, avg_win_pct: float,
                    avg_loss_pct: float) -> float:
    if avg_win_pct <= 0 or avg_loss_pct <= 0:
        return MIN_RISK_PER_TRADE

    w = win_rate_pct / 100.0
    b = avg_win_pct / avg_loss_pct
    kelly = w - (1 - w) / b
    fractional = kelly * KELLY_FRACTION * 100

    return round(max(MIN_RISK_PER_TRADE, min(fractional, MAX_RISK_PER_TRADE)), 2)


# ------------------------------------------------------------------
#  Cek semua kondisi risk sebelum trade
# ------------------------------------------------------------------
def check_risk_approval(
    symbol      : str,
    timeframe   : str,
    signal      : str,
    entry       : float,
    sl          : float,
    win_rate    : float = 50.0,
    avg_pnl     : float = 1.0,
    wr_is_default: bool = False,   # [FIX] tambahan: True jika win rate tidak valid
    similar_cases: int  = 0,       # [FIX] tambahan: jumlah kasus mirip
) -> dict:
    _state.reset_daily()

    reasons  = []
    warnings = []
    approved = True

    # ── 1. Trading halted ─────────────────────────────────
    if _state.trading_halted:
        return {
            "approved"      : False,
            "risk_pct"      : 0,
            "position_size" : 0,
            "risk_usdt"     : 0,
            "kelly_risk"    : 0,
            "reasons"       : [f"❌ Trading dihentikan: {_state.halt_reason}"],
            "warnings"      : [],
            "report"        : f"HALT: {_state.halt_reason}",
            "balance"       : _state.balance,
            "drawdown_pct"  : round(_state.current_drawdown_pct, 2),
            "daily_pnl"     : round(_state.daily_pnl, 2),
            "streak_loss"   : _state.consecutive_loss,
            "portfolio_heat": round(_state.portfolio_heat, 2),
            "skip_wr_filter": False,
        }

    # ── 2. Max Drawdown ───────────────────────────────────
    dd = _state.current_drawdown_pct
    if dd >= MAX_DRAWDOWN_PCT:
        _state.trading_halted = True
        _state.halt_reason    = f"Max drawdown {dd:.1f}% tercapai"
        _state.save()
        reasons.append(f"❌ Drawdown {dd:.1f}% melebihi batas {MAX_DRAWDOWN_PCT}%")
        approved = False
    elif dd >= MAX_DRAWDOWN_PCT * 0.7:
        warnings.append(f"⚠️ Drawdown {dd:.1f}% mendekati batas maksimal")

    # ── 3. Daily loss limit ───────────────────────────────
    daily_loss_pct = (_state.daily_pnl / _state.balance * 100) if _state.balance > 0 else 0
    if daily_loss_pct <= -MAX_DAILY_LOSS_PCT:
        _state.trading_halted = True
        _state.halt_reason    = f"Daily loss limit tercapai"
        _state.save()
        reasons.append(f"❌ Daily loss {abs(daily_loss_pct):.1f}% melebihi batas {MAX_DAILY_LOSS_PCT}%")
        approved = False
    elif daily_loss_pct <= -MAX_DAILY_LOSS_PCT * 0.6:
        warnings.append(f"⚠️ Daily loss sudah {abs(daily_loss_pct):.1f}%, mendekati batas")

    # ── 3b. Consecutive loss hard halt ─────────────────────
    # FIX: penalty Kelly saja tidak cukup — tetap ada MIN_RISK_PER_TRADE
    # yang membuat bot terus entry walau sudah kalah berkali-kali.
    MAX_CONSECUTIVE_LOSS_HALT = 6
    if _state.consecutive_loss >= MAX_CONSECUTIVE_LOSS_HALT:
        _state.trading_halted = True
        _state.halt_reason    = f"{_state.consecutive_loss} kali kalah beruntun — trading dihentikan sementara"
        _state.save()
        reasons.append(f"❌ {_state.consecutive_loss} kali kalah beruntun — melebihi batas {MAX_CONSECUTIVE_LOSS_HALT}")
        approved = False
    elif _state.consecutive_loss >= MAX_CONSECUTIVE_LOSS_HALT - 2:
        warnings.append(f"⚠️ {_state.consecutive_loss} kali kalah beruntun — mendekati batas halt")

    # ── 4. Portfolio heat ─────────────────────────────────
    heat = _state.portfolio_heat
    if heat >= MAX_PORTFOLIO_HEAT:
        reasons.append(f"❌ Portfolio heat {heat:.1f}% sudah penuh (max: {MAX_PORTFOLIO_HEAT}%)")
        approved = False
    elif heat >= MAX_PORTFOLIO_HEAT * 0.75:
        warnings.append(f"⚠️ Portfolio heat {heat:.1f}% mendekati batas")

    # ── 5. Win rate check (PERBAIKAN UTAMA) ──────────────
    # [FIX] Hanya filter win rate jika data VALID (bukan default)
    skip_wr = wr_is_default or similar_cases == 0
    if not skip_wr:
        if win_rate < MIN_WIN_RATE_HARD:
            reasons.append(f"❌ Win rate {win_rate}% terlalu rendah (min: {MIN_WIN_RATE_HARD}%)")
            approved = False
        elif win_rate < MIN_WIN_RATE_WARN:
            warnings.append(f"⚠️ Win rate {win_rate}% cukup rendah, hati-hati")
    else:
        # Data tidak cukup — beri warning tapi jangan reject
        warnings.append(f"ℹ️ Win rate tidak tersedia (data historis kurang), pakai default risk")

    # ── 6. Hitung ukuran posisi dengan Kelly ─────────────
    avg_win_pct  = abs(avg_pnl) if avg_pnl > 0 else 1.5
    avg_loss_pct = abs(sl - entry) / entry * 100 if entry > 0 else 1.0

    # [FIX] Jika win rate tidak valid, pakai win rate konservatif 50%
    effective_wr = win_rate if not skip_wr else 50.0
    kelly_risk   = kelly_criterion(effective_wr, avg_win_pct, avg_loss_pct)

    # ── 7. Consecutive loss penalty ──────────────────────
    streak = _state.consecutive_loss
    if streak >= MAX_CONSECUTIVE_LOSS:
        penalty    = 0.5 ** (streak - MAX_CONSECUTIVE_LOSS + 1)
        kelly_risk = round(kelly_risk * penalty, 2)
        kelly_risk = max(kelly_risk, MIN_RISK_PER_TRADE)
        warnings.append(f"⚠️ {streak} kalah berturut — ukuran posisi dikurangi ke {kelly_risk}%")

    # ── 8. Final risk ─────────────────────────────────────
    final_risk_pct = min(kelly_risk, MAX_RISK_PER_TRADE)
    risk_usdt      = _state.balance * final_risk_pct / 100.0
    stop_dist      = abs(entry - sl)
    pos_size       = round(risk_usdt / stop_dist, 6) if stop_dist > 0 else 0.0

    # ── 9. Report ─────────────────────────────────────────
    wr_info = f"{win_rate}% ({'no data' if skip_wr else f'{similar_cases} cases'})"
    report_lines = [
        f"Symbol      : {symbol} / {timeframe}",
        f"Signal      : {signal}",
        f"Balance     : ${_state.balance:.2f}",
        f"Drawdown    : {dd:.1f}%",
        f"Daily PnL   : ${_state.daily_pnl:.2f} ({daily_loss_pct:.1f}%)",
        f"Port. Heat  : {heat:.1f}%",
        f"Consec Loss : {streak}",
        f"Win Rate    : {wr_info}",
        f"Kelly Risk  : {kelly_risk}% → Final: {final_risk_pct}%",
        f"Risk USDT   : ${risk_usdt:.2f}",
        f"Status      : {'✅ APPROVED' if approved else '❌ REJECTED'}",
    ]
    if reasons:
        report_lines.append(f"Reasons     : {' | '.join(reasons)}")
    if warnings:
        report_lines.append(f"Warnings    : {' | '.join(warnings)}")

    return {
        "approved"      : approved,
        "risk_pct"      : final_risk_pct if approved else 0,
        "position_size" : pos_size if approved else 0,
        "risk_usdt"     : round(risk_usdt, 2) if approved else 0,
        "kelly_risk"    : kelly_risk,
        "reasons"       : reasons,
        "warnings"      : warnings,
        "report"        : "\n".join(report_lines),
        "balance"       : _state.balance,
        "drawdown_pct"  : round(dd, 2),
        "daily_pnl"     : round(_state.daily_pnl, 2),
        "streak_loss"   : streak,
        "portfolio_heat": round(heat, 2),
        "skip_wr_filter": skip_wr,   # [FIX] info untuk debugging
    }


# ------------------------------------------------------------------
#  Update setelah trade selesai
# ------------------------------------------------------------------
def record_trade_result(symbol: str, timeframe: str, signal: str,
                        pnl_usdt: float, win: bool):
    key = f"{symbol}_{timeframe}_{signal}"
    _state.remove_position(key)
    _state.update_balance(pnl_usdt, win)
    status = "✅ WIN" if win else "❌ LOSS"
    logger.info(
        f"Trade recorded: {symbol}/{timeframe} {signal} | "
        f"{status} | PnL: ${pnl_usdt:.2f} | Balance: ${_state.balance:.2f}"
    )


def open_position(symbol: str, timeframe: str, signal: str, risk_pct: float):
    key = f"{symbol}_{timeframe}_{signal}"
    _state.add_position(key, risk_pct)


def reset_positions():
    """[FIX] Reset semua open positions (pakai jika portfolio heat stuck)."""
    _state.reset_positions()


# ------------------------------------------------------------------
#  Status summary
# ------------------------------------------------------------------
def get_risk_status() -> dict:
    _state.reset_daily()
    dd        = _state.current_drawdown_pct
    daily_pct = (_state.daily_pnl / _state.balance * 100) if _state.balance > 0 else 0
    heat      = _state.portfolio_heat

    if _state.trading_halted:
        health = "🔴 HALTED"
    elif dd > MAX_DRAWDOWN_PCT * 0.7 or daily_pct < -MAX_DAILY_LOSS_PCT * 0.6:
        health = "🟡 CAUTION"
    else:
        health = "🟢 HEALTHY"

    return {
        "health"          : health,
        "balance"         : round(_state.balance, 2),
        "peak_balance"    : round(_state.peak_balance, 2),
        "drawdown_pct"    : round(dd, 2),
        "daily_pnl"       : round(_state.daily_pnl, 2),
        "daily_pnl_pct"   : round(daily_pct, 2),
        "portfolio_heat"  : round(heat, 2),
        "consecutive_loss": _state.consecutive_loss,
        "trading_halted"  : _state.trading_halted,
        "halt_reason"     : _state.halt_reason,
        "open_positions"  : len(_state.open_positions),
        "total_trades"    : _state.total_trades,
    }


def resume_trading(manual: bool = False):
    if manual:
        _state.trading_halted = False
        _state.halt_reason    = ""
        _state.save()
        logger.info("Trading di-resume secara manual.")
    else:
        logger.warning("Gunakan resume_trading(manual=True) untuk override halt.")



def reset_streak_loss():
    """Reset consecutive_loss ke 0 secara in-memory + persist ke JSON/DB.
    Dipanggil dari /reset_streak agar _state (RAM) dan risk_state.json selalu sinkron."""
    with _state._lock:
        old_streak = _state.consecutive_loss
        _state.consecutive_loss = 0
        _state.trading_halted   = False
        _state.halt_reason      = ""
        _state.save()
    logger.info(f"Streak loss direset manual: {old_streak} -> 0")
    return old_streak


def print_risk_status():
    s = get_risk_status()
    print(f"\n{'='*50}")
    print(f"  RISK MANAGEMENT STATUS  {s['health']}")
    print(f"{'='*50}")
    print(f"  Balance        : ${s['balance']:.2f} (peak: ${s['peak_balance']:.2f})")
    print(f"  Drawdown       : {s['drawdown_pct']:.1f}% (max: {MAX_DRAWDOWN_PCT}%)")
    print(f"  Daily PnL      : ${s['daily_pnl']:.2f} ({s['daily_pnl_pct']:.1f}%)")
    print(f"  Portfolio Heat : {s['portfolio_heat']:.1f}% (max: {MAX_PORTFOLIO_HEAT}%)")
    print(f"  Streak Loss    : {s['consecutive_loss']}")
    print(f"  Open Positions : {s['open_positions']}")
    print(f"  Total Trades   : {_state.total_trades}")
    if s["trading_halted"]:
        print(f"\n  ⛔ TRADING HALTED: {s['halt_reason']}")
    print(f"{'='*50}\n")
