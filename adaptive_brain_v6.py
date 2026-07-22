#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           ADAPTIVE BRAIN V6 — AI Decision Engine for Crypto Scanner         ║
║                                                                              ║
║  Self-learning, regime-aware, penalty/reward system dengan full explainability║
║  Compatible: scanner.py, signal_engine.py, risk_manager.py, main.py         ║
║  Backward compatible dengan adaptive_weights.py API                         ║
╚══════════════════════════════════════════════════════════════════════════════╝

Changelog V6:
  - Self Learning Engine (pair, session, regime)
  - Adaptive Score 0-100 dengan 11 komponen
  - Dynamic Threshold per regime + auto-adjust dari performa
  - Pair Learning: confidence turun jika pair sering loss
  - Session Learning: Asia/London/New York
  - Market Regime Learning: best setup per regime
  - Risk Learning: rekomendasi SL/TP dari historis
  - Confidence Learning: Very Low → Very High
  - Penalty System (10 faktor)
  - Reward System (10 faktor)
  - Auto Weight Optimizer
  - Performance Database (JSON + SQLite)
  - AI Recommendation: ALLOW / CAUTION / SKIP
  - Explainable AI: setiap score ada alasannya
  - Smart Recovery: mode konservatif setelah 5 loss
  - Market Health Score 0-100
  - AI Memory: best/worst pair, session, setup
  - Performance Optimized (vectorized, cache)
  - Full backward compatibility
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ── Optional pandas untuk vectorized ops ──
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("adaptive_brain_v6")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = "6.0.0"

# Session boundaries (UTC hour)
SESSIONS = {
    "ASIA":     (0,  8),
    "LONDON":   (7,  16),
    "NEW_YORK": (13, 22),
    "OFF":      (22, 24),
}

# Base threshold per regime (akan dimodifikasi oleh learning)
BASE_THRESHOLD = {
    "TRENDING":   60.0,
    "RANGING":    80.0,
    "VOLATILE":   70.0,
    "NEUTRAL":    65.0,
    "BREAKOUT":   58.0,
    "WEAK_TREND": 72.0,
}

# Confidence level boundaries
CONFIDENCE_LEVELS = {
    "VERY_HIGH": 80,
    "HIGH":      65,
    "MEDIUM":    50,
    "LOW":       35,
    "VERY_LOW":  0,
}

# Smart recovery: berapa loss berturut sebelum mode konservatif
RECOVERY_LOSS_TRIGGER = 5
RECOVERY_THRESHOLD_BUMP = 10.0   # naikkan threshold sebesar ini
RECOVERY_MIN_WIN_TO_RELAX = 3    # butuh N win untuk relaksasi

# Auto weight optimizer settings
WEIGHT_LEARNING_RATE = 0.15      # seberapa cepat bobot berubah
WEIGHT_MIN = 0.05
WEIGHT_MAX = 0.50

# Cache TTL (detik)
CACHE_TTL = 300

# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class IndicatorWeight:
    """Bobot satu indikator dengan tracking hits/misses."""
    name: str
    weight: float
    hits: int = 0
    misses: int = 0
    last_updated: Optional[datetime] = None

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.5

    @property
    def sample_size(self) -> int:
        return self.hits + self.misses


@dataclass
class PairStats:
    """Statistik per trading pair."""
    symbol: str
    total: int = 0
    wins: int = 0
    losses: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    consecutive_loss: int = 0
    confidence_modifier: float = 0.0   # -20 s/d +20
    last_updated: Optional[str] = None

    @property
    def win_rate(self) -> float:
        return self.wins / self.total * 100 if self.total > 0 else 50.0

    @property
    def profit_factor(self) -> float:
        return self.total_profit / max(abs(self.total_loss), 1e-9)


@dataclass
class SessionStats:
    """Statistik per session trading."""
    session: str
    total: int = 0
    wins: int = 0
    score_modifier: float = 0.0   # -10 s/d +10

    @property
    def win_rate(self) -> float:
        return self.wins / self.total * 100 if self.total > 0 else 50.0


@dataclass
class RegimeStats:
    """Statistik per market regime."""
    regime: str
    total: int = 0
    wins: int = 0
    best_setup: str = ""
    worst_setup: str = ""
    avg_rr: float = 0.0
    threshold_modifier: float = 0.0   # auto-adjust threshold

    @property
    def win_rate(self) -> float:
        return self.wins / self.total * 100 if self.total > 0 else 50.0


@dataclass
class RiskLearning:
    """Belajar dari SL/TP historis."""
    sl_too_tight_count: int = 0
    sl_too_wide_count: int = 0
    tp1_hit_rate: float = 0.5
    tp2_hit_rate: float = 0.3
    trailing_success_rate: float = 0.4
    recommended_sl_mult: float = 1.0
    recommended_tp_mult: float = 1.0


@dataclass
class AIMemory:
    """Memory jangka panjang AI."""
    best_pairs: List[str] = field(default_factory=list)
    worst_pairs: List[str] = field(default_factory=list)
    best_sessions: List[str] = field(default_factory=list)
    worst_sessions: List[str] = field(default_factory=list)
    best_regime: str = "TRENDING"
    best_setups: List[str] = field(default_factory=list)
    worst_setups: List[str] = field(default_factory=list)
    total_decisions: int = 0
    last_updated: Optional[str] = None


@dataclass
class BrainState:
    """State lengkap Adaptive Brain V6."""
    indicator_weights: Dict[str, IndicatorWeight] = field(default_factory=dict)
    pair_stats: Dict[str, PairStats] = field(default_factory=dict)
    session_stats: Dict[str, SessionStats] = field(default_factory=dict)
    regime_stats: Dict[str, RegimeStats] = field(default_factory=dict)
    risk_learning: RiskLearning = field(default_factory=RiskLearning)
    ai_memory: AIMemory = field(default_factory=AIMemory)
    decision_count: int = 0
    last_calibration: Optional[datetime] = None
    conservative_mode: bool = False
    conservative_since: Optional[datetime] = None
    recent_results: deque = field(default_factory=lambda: deque(maxlen=20))
    version: str = VERSION


# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE DATABASE (SQLite + JSON)
# ═══════════════════════════════════════════════════════════════════════════════

class PerformanceMemory:
    """
    SQLite-backed store untuk trade history dan indicator performance.
    JSON sidecar untuk stats cepat tanpa query.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """Inisialisasi semua tabel database."""
        with self._lock:
            c = self.conn.cursor()
            c.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT    NOT NULL,
                    signal      TEXT    NOT NULL,
                    confidence  REAL,
                    regime      TEXT,
                    session     TEXT,
                    setup_type  TEXT,
                    score       REAL,
                    indicators  TEXT,
                    profit      REAL    DEFAULT 0,
                    loss        REAL    DEFAULT 0,
                    rr_actual   REAL    DEFAULT 0,
                    sl_hit      INTEGER DEFAULT 0,
                    tp1_hit     INTEGER DEFAULT 0,
                    tp2_hit     INTEGER DEFAULT 0,
                    timestamp   TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS indicator_weights (
                    name         TEXT PRIMARY KEY,
                    weight       REAL NOT NULL,
                    hits         INTEGER DEFAULT 0,
                    misses       INTEGER DEFAULT 0,
                    last_updated TEXT
                );

                CREATE TABLE IF NOT EXISTS pair_stats (
                    symbol              TEXT PRIMARY KEY,
                    total               INTEGER DEFAULT 0,
                    wins                INTEGER DEFAULT 0,
                    losses              INTEGER DEFAULT 0,
                    total_profit        REAL    DEFAULT 0,
                    total_loss          REAL    DEFAULT 0,
                    consecutive_loss    INTEGER DEFAULT 0,
                    confidence_modifier REAL    DEFAULT 0,
                    last_updated        TEXT
                );

                CREATE TABLE IF NOT EXISTS session_stats (
                    session         TEXT PRIMARY KEY,
                    total           INTEGER DEFAULT 0,
                    wins            INTEGER DEFAULT 0,
                    score_modifier  REAL    DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS regime_stats (
                    regime              TEXT PRIMARY KEY,
                    total               INTEGER DEFAULT 0,
                    wins                INTEGER DEFAULT 0,
                    best_setup          TEXT    DEFAULT '',
                    worst_setup         TEXT    DEFAULT '',
                    avg_rr              REAL    DEFAULT 0,
                    threshold_modifier  REAL    DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    symbol      TEXT,
                    signal      TEXT,
                    score       REAL,
                    threshold   REAL,
                    recommendation TEXT,
                    reasoning   TEXT,
                    context     TEXT
                );
            """)
            self.conn.commit()

    # ── Trade CRUD ──────────────────────────────────────────────────────────

    def save_trade(self, trade: Dict[str, Any]) -> None:
        """Simpan satu trade record."""
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                INSERT INTO trades
                (symbol, signal, confidence, regime, session, setup_type,
                 score, indicators, profit, loss, rr_actual,
                 sl_hit, tp1_hit, tp2_hit, timestamp)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                trade.get("symbol", ""),
                trade.get("signal", ""),
                trade.get("confidence", 0.0),
                trade.get("regime", "NEUTRAL"),
                trade.get("session", ""),
                trade.get("setup_type", ""),
                trade.get("score", 0.0),
                json.dumps(trade.get("indicators", {})),
                trade.get("profit", 0.0),
                trade.get("loss", 0.0),
                trade.get("rr_actual", 0.0),
                int(trade.get("sl_hit", False)),
                int(trade.get("tp1_hit", False)),
                int(trade.get("tp2_hit", False)),
                trade.get("timestamp", datetime.now(timezone.utc).isoformat()),
            ))
            self.conn.commit()

    def load_recent_trades(self, days: int = 30) -> List[Dict[str, Any]]:
        """Load trades N hari terakhir."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute(
                "SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp DESC",
                (cutoff,)
            )
            return [dict(row) for row in c.fetchall()]

    def get_pair_performance(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """Ambil statistik performa satu pair."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                SELECT
                    COUNT(*)                                    AS total,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN loss   > 0 THEN 1 ELSE 0 END) AS losses,
                    AVG(rr_actual)                              AS avg_rr,
                    SUM(profit)                                 AS total_profit,
                    SUM(loss)                                   AS total_loss
                FROM trades
                WHERE symbol = ? AND timestamp >= ?
            """, (symbol, cutoff))
            row = c.fetchone()
            return dict(row) if row else {}

    def get_session_performance(self, session: str, days: int = 30) -> Dict[str, Any]:
        """Ambil statistik performa satu session."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                SELECT
                    COUNT(*)                                    AS total,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) AS wins
                FROM trades
                WHERE session = ? AND timestamp >= ?
            """, (session, cutoff))
            row = c.fetchone()
            return dict(row) if row else {}

    def get_regime_performance(self, regime: str, days: int = 30) -> Dict[str, Any]:
        """Ambil statistik performa satu regime."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                SELECT
                    COUNT(*)                                      AS total,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END)  AS wins,
                    AVG(rr_actual)                                AS avg_rr,
                    setup_type,
                    COUNT(setup_type)                             AS setup_count
                FROM trades
                WHERE regime = ? AND timestamp >= ?
                GROUP BY setup_type
                ORDER BY wins DESC
            """, (regime, cutoff))
            rows = c.fetchall()
            return [dict(r) for r in rows]

    def get_global_stats(self, days: int = 30) -> Dict[str, Any]:
        """Hitung statistik global untuk Performance Database."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                SELECT
                    COUNT(*)                                      AS total_trades,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END)  AS wins,
                    SUM(CASE WHEN loss   > 0 THEN 1 ELSE 0 END)  AS losses,
                    AVG(rr_actual)                                AS avg_rr,
                    SUM(profit)                                   AS total_profit,
                    SUM(loss)                                     AS total_loss,
                    MIN(loss)                                     AS max_single_loss
                FROM trades
                WHERE timestamp >= ?
            """, (cutoff,))
            row = c.fetchone()
            d = dict(row) if row else {}

            total  = d.get("total_trades") or 0
            wins   = d.get("wins") or 0
            tp     = d.get("total_profit") or 0.0
            tl     = abs(d.get("total_loss") or 0.0)

            d["win_rate"]      = round(wins / total * 100, 2) if total > 0 else 0.0
            d["profit_factor"] = round(tp / max(tl, 1e-9), 3)
            d["expectancy"]    = round((tp - tl) / max(total, 1), 4)
            d["avg_profit"]    = round(tp / max(wins, 1), 4)
            d["avg_loss"]      = round(tl / max(total - wins, 1), 4)
            return d

    def get_sl_stats(self, days: int = 30) -> Dict[str, Any]:
        """Analisis berapa sering SL kena untuk Risk Learning."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                SELECT
                    COUNT(*)                                        AS total,
                    SUM(sl_hit)                                     AS sl_hits,
                    SUM(tp1_hit)                                    AS tp1_hits,
                    SUM(tp2_hit)                                    AS tp2_hits,
                    AVG(rr_actual)                                  AS avg_rr
                FROM trades WHERE timestamp >= ?
            """, (cutoff,))
            row = c.fetchone()
            return dict(row) if row else {}

    # ── Indicator Weights ────────────────────────────────────────────────────

    def save_indicator_weights(self, weights: Dict[str, IndicatorWeight]) -> None:
        """Simpan semua bobot indikator ke DB."""
        with self._lock:
            c = self.conn.cursor()
            for name, iw in weights.items():
                c.execute("""
                    INSERT OR REPLACE INTO indicator_weights
                    (name, weight, hits, misses, last_updated)
                    VALUES (?,?,?,?,?)
                """, (
                    name, iw.weight, iw.hits, iw.misses,
                    iw.last_updated.isoformat() if iw.last_updated else None,
                ))
            self.conn.commit()

    def load_indicator_weights(self) -> Dict[str, IndicatorWeight]:
        """Load semua bobot indikator dari DB."""
        with self._lock:
            c = self.conn.cursor()
            c.execute("SELECT * FROM indicator_weights")
            rows = c.fetchall()
            weights = {}
            for row in rows:
                iw = IndicatorWeight(
                    name=row["name"],
                    weight=row["weight"],
                    hits=row["hits"],
                    misses=row["misses"],
                    last_updated=(
                        datetime.fromisoformat(row["last_updated"])
                        if row["last_updated"] else None
                    ),
                )
                weights[row["name"]] = iw
            return weights

    # ── Decisions Log ────────────────────────────────────────────────────────

    def save_decision(self, decision: Dict[str, Any]) -> None:
        """Simpan setiap keputusan AI."""
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                INSERT INTO decisions
                (timestamp, symbol, signal, score, threshold, recommendation, reasoning, context)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                decision.get("timestamp", datetime.now(timezone.utc).isoformat()),
                decision.get("symbol", ""),
                decision.get("signal", ""),
                decision.get("score", 0.0),
                decision.get("threshold", 0.0),
                decision.get("recommendation", ""),
                decision.get("reasoning", ""),
                json.dumps(decision.get("context", {})),
            ))
            self.conn.commit()

    def prune_old_data(self, days: int = 90) -> int:
        """Hapus data lama untuk efisiensi storage."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute("DELETE FROM trades WHERE timestamp < ?", (cutoff,))
            deleted = c.rowcount
            c.execute("DELETE FROM decisions WHERE timestamp < ?", (cutoff,))
            self.conn.commit()
            return deleted


# ═══════════════════════════════════════════════════════════════════════════════
# ADAPTIVE SCORE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class AdaptiveScoreEngine:
    """
    Hitung Adaptive Score 0-100 dari 11 komponen dengan Explainable AI.
    Setiap komponen memiliki reward dan penalty yang transparan.
    """

    def __init__(self, weights: Dict[str, IndicatorWeight]) -> None:
        self.weights = weights

    def _safe(self, v: Any, default: float = 0.0) -> float:
        """Safe float conversion dengan NaN/Inf guard."""
        try:
            val = float(v)
            return default if (val != val or val == float('inf') or val == float('-inf')) else val
        except (TypeError, ValueError):
            return default

    def compute(
        self,
        components: Dict[str, Any],
        regime: str = "NEUTRAL",
    ) -> Tuple[float, List[str], Dict[str, float]]:
        """
        Hitung adaptive score dengan reward + penalty system.

        Returns:
            (score, explanations, breakdown)
            - score: float 0-100
            - explanations: list string ["+ 12.0 Trend kuat (ADX=45)", ...]
            - breakdown: dict komponen → kontribusi
        """
        score = 0.0
        explanations: List[str] = []
        breakdown: Dict[str, float] = {}

        def _w(name: str, default: float = 0.25) -> float:
            """Ambil bobot adaptif satu indikator."""
            iw = self.weights.get(name)
            return iw.weight if iw else default

        # ── 1. TREND ────────────────────────────────────────────────────────
        adx        = self._safe(components.get("adx", 0))
        trend_up   = bool(components.get("trend_up", False))
        trend_dn   = bool(components.get("trend_down", False))
        ema_aligned = bool(components.get("ema_aligned", False))

        trend_score = min(100.0, adx * 2.5)
        if ema_aligned:
            trend_score = min(100.0, trend_score * 1.15)
        if trend_up or trend_dn:
            trend_score = min(100.0, trend_score * 1.10)

        trend_contrib = trend_score * _w("trend", 0.20)
        score += trend_contrib
        breakdown["trend"] = round(trend_contrib, 2)
        if trend_score >= 70:
            explanations.append(f"+{trend_contrib:.1f} Trend kuat (ADX={adx:.0f})")
        elif trend_score <= 30:
            explanations.append(f"+{trend_contrib:.1f} Trend lemah (ADX={adx:.0f})")

        # ── 2. MOMENTUM ──────────────────────────────────────────────────────
        rsi      = self._safe(components.get("rsi", 50))
        macd_h   = self._safe(components.get("macd_hist", 0))
        close    = max(self._safe(components.get("close", 1), 1), 1e-9)
        macd_norm = min(100.0, max(0.0, (macd_h / (close * 0.01 + 1e-9)) * 50 + 50))
        rsi_mom  = abs(rsi - 50) * 2
        mom_score = macd_norm * 0.6 + rsi_mom * 0.4

        mom_contrib = mom_score * _w("momentum", 0.15)
        score += mom_contrib
        breakdown["momentum"] = round(mom_contrib, 2)
        if mom_score >= 70:
            explanations.append(f"+{mom_contrib:.1f} Momentum tinggi (RSI={rsi:.0f})")
        elif mom_score <= 25:
            explanations.append(f"+{mom_contrib:.1f} Momentum lemah")

        # ── 3. VOLUME ────────────────────────────────────────────────────────
        vol_ratio = self._safe(components.get("vol_ratio", 1.0))
        obv_bull  = bool(components.get("obv_bull", False))
        vol_score = min(100.0, vol_ratio * 50.0)
        if obv_bull and vol_ratio > 1.5:
            vol_score = min(100.0, vol_score * 1.2)

        vol_contrib = vol_score * _w("volume", 0.15)
        score += vol_contrib
        breakdown["volume"] = round(vol_contrib, 2)
        if vol_ratio >= 2.0:
            explanations.append(f"+{vol_contrib:.1f} Volume breakout ({vol_ratio:.1f}x)")
        elif vol_ratio <= 0.7:
            explanations.append(f"+{vol_contrib:.1f} Volume rendah ({vol_ratio:.1f}x)")

        # ── 4. VOLATILITY ────────────────────────────────────────────────────
        atr      = self._safe(components.get("atr", 0))
        atr_pct  = (atr / close * 100) if close > 0 else 0
        vol_regime_score = min(100.0, atr_pct * 20)

        vol_regime_contrib = vol_regime_score * _w("volatility", 0.08)
        score += vol_regime_contrib
        breakdown["volatility"] = round(vol_regime_contrib, 2)

        # ── 5. BTC TREND ─────────────────────────────────────────────────────
        btc_aligned = self._safe(components.get("btc_aligned", 0))  # -1, 0, +1
        btc_strength = self._safe(components.get("btc_strength", 50))
        btc_score = 50.0 + btc_aligned * 30.0
        btc_score = min(100.0, max(0.0, btc_score))

        btc_contrib = btc_score * _w("btc_trend", 0.08)
        score += btc_contrib
        breakdown["btc_trend"] = round(btc_contrib, 2)
        if btc_aligned > 0:
            explanations.append(f"+{btc_contrib:.1f} BTC mendukung arah")
        elif btc_aligned < 0:
            explanations.append(f"+{btc_contrib:.1f} BTC berlawanan arah")

        # ── 6. MARKET REGIME ─────────────────────────────────────────────────
        regime_score_map = {
            "TRENDING": 85, "BREAKOUT": 90,
            "RANGING": 50, "VOLATILE": 45,
            "NEUTRAL": 60, "WEAK_TREND": 55,
        }
        regime_score = float(regime_score_map.get(regime.upper(), 60))
        regime_contrib = regime_score * _w("regime", 0.06)
        score += regime_contrib
        breakdown["regime"] = round(regime_contrib, 2)

        # ── 7. CONFIDENCE (dari komponen lain) ───────────────────────────────
        raw_conf = self._safe(components.get("confidence_raw", 50))
        conf_contrib = raw_conf * _w("confidence", 0.08)
        score += conf_contrib
        breakdown["confidence"] = round(conf_contrib, 2)

        # ── 8. INSTITUTIONAL SCORE ───────────────────────────────────────────
        inst_score = self._safe(components.get("institutional_score", 0))
        inst_contrib = inst_score * _w("institutional", 0.06)
        score += inst_contrib
        breakdown["institutional"] = round(inst_contrib, 2)
        if inst_score >= 70:
            explanations.append(f"+{inst_contrib:.1f} Sinyal institusional kuat")

        # ── 9. ORDER BLOCK ───────────────────────────────────────────────────
        ob_score = self._safe(components.get("order_block_score", 0))
        ob_contrib = ob_score * _w("order_block", 0.05)
        score += ob_contrib
        breakdown["order_block"] = round(ob_contrib, 2)
        if ob_score >= 60:
            explanations.append(f"+{ob_contrib:.1f} Order Block terdeteksi")

        # ── 10. FAIR VALUE GAP ───────────────────────────────────────────────
        fvg_score = self._safe(components.get("fvg_score", 0))
        fvg_contrib = fvg_score * _w("fvg", 0.04)
        score += fvg_contrib
        breakdown["fvg"] = round(fvg_contrib, 2)
        if fvg_score >= 60:
            explanations.append(f"+{fvg_contrib:.1f} Fair Value Gap terdeteksi")

        # ── 11. LIQUIDITY SWEEP ──────────────────────────────────────────────
        liq_score = self._safe(components.get("liquidity_sweep_score", 0))
        liq_contrib = liq_score * _w("liquidity_sweep", 0.05)
        score += liq_contrib
        breakdown["liquidity_sweep"] = round(liq_contrib, 2)
        if liq_score >= 60:
            explanations.append(f"+{liq_contrib:.1f} Liquidity Sweep terdeteksi")

        # Clamp 0-100
        score = round(min(100.0, max(0.0, score)), 2)
        return score, explanations, breakdown

    # ── PENALTY SYSTEM ───────────────────────────────────────────────────────

    def compute_penalties(
        self,
        components: Dict[str, Any],
        regime: str = "NEUTRAL",
        signal: str = "",
    ) -> Tuple[float, List[str]]:
        """
        Hitung total penalty berdasarkan 10 kondisi negatif.

        Returns:
            (total_penalty, explanations)  -- penalty adalah angka negatif
        """
        penalty = 0.0
        reasons: List[str] = []
        s = self._safe

        vol_ratio  = s(components.get("vol_ratio", 1.0))
        atr        = s(components.get("atr", 0))
        close      = max(s(components.get("close", 1), 1), 1e-9)
        atr_pct    = atr / close * 100

        # 1. Volume kecil
        if vol_ratio < 0.5:
            p = -8.0
            penalty += p
            reasons.append(f"{p:.1f} Volume sangat kecil ({vol_ratio:.2f}x)")
        elif vol_ratio < 0.8:
            p = -4.0
            penalty += p
            reasons.append(f"{p:.1f} Volume di bawah rata-rata")

        # 2. ATR kecil (market choppy / tidak bergerak)
        if atr_pct < 0.3:
            p = -6.0
            penalty += p
            reasons.append(f"{p:.1f} ATR terlalu kecil ({atr_pct:.2f}%)")

        # 3. Sideways / Ranging
        if regime.upper() in ("RANGING", "SIDEWAYS"):
            p = -5.0
            penalty += p
            reasons.append(f"{p:.1f} Market sideways/ranging")

        # 4. Fake Breakout
        fake_bo = bool(components.get("fake_breakout", False))
        if fake_bo:
            p = -10.0
            penalty += p
            reasons.append(f"{p:.1f} Fake breakout terdeteksi")

        # 5. Resistance/Support terlalu dekat
        sr_pos = s(components.get("sr_pos", 0.5))  # 0=at support, 1=at resistance
        if signal.upper().startswith("BUY") and sr_pos > 0.85:
            p = -7.0
            penalty += p
            reasons.append(f"{p:.1f} Resistance dekat (SR pos={sr_pos:.2f})")
        elif signal.upper().startswith("SELL") and sr_pos < 0.15:
            p = -7.0
            penalty += p
            reasons.append(f"{p:.1f} Support dekat (SR pos={sr_pos:.2f})")

        # 6. BTC berlawanan
        btc_aligned = s(components.get("btc_aligned", 0))
        if btc_aligned < 0:
            p = -6.0
            penalty += p
            reasons.append(f"{p:.1f} BTC berlawanan arah sinyal")

        # 7. Funding rate ekstrem
        funding = s(components.get("funding_rate", 0))
        if abs(funding) > 0.001:
            p = -5.0
            penalty += p
            reasons.append(f"{p:.1f} Funding rate ekstrem ({funding:.4f})")

        # 8. Open Interest turun
        oi_change = s(components.get("oi_change_pct", 0))
        if oi_change < -5.0:
            p = -4.0
            penalty += p
            reasons.append(f"{p:.1f} Open Interest turun ({oi_change:.1f}%)")

        # 9. Divergence berlawanan
        divergence = s(components.get("divergence_bearish" if "BUY" in signal.upper() else "divergence_bullish", 0))
        if divergence > 0.5:
            p = -8.0
            penalty += p
            reasons.append(f"{p:.1f} Divergence berlawanan terdeteksi")

        # 10. RSI overbought/oversold ekstrem berlawanan arah
        rsi = s(components.get("rsi", 50))
        if signal.upper().startswith("BUY") and rsi > 70:
            p = -5.0
            penalty += p
            reasons.append(f"{p:.1f} RSI overbought ({rsi:.0f})")
        elif signal.upper().startswith("SELL") and rsi < 30:
            p = -5.0
            penalty += p
            reasons.append(f"{p:.1f} RSI oversold ({rsi:.0f})")

        # 11. Blow-off top: volume ekstrem + RSI tinggi bersamaan (BUY)
        vol_ratio_p = s(components.get("vol_ratio", 1.0))
        if signal.upper().startswith("BUY") and vol_ratio_p > 4.0 and rsi > 70:
            p = -10.0
            penalty += p
            reasons.append(f"{p:.1f} Blow-off top terdeteksi (Vol={vol_ratio_p:.1f}x, RSI={rsi:.0f})")
        elif signal.upper().startswith("SELL") and vol_ratio_p > 4.0 and rsi < 30:
            p = -10.0
            penalty += p
            reasons.append(f"{p:.1f} Capitulation dump terdeteksi (Vol={vol_ratio_p:.1f}x, RSI={rsi:.0f})")

        return round(penalty, 2), reasons

    # ── REWARD SYSTEM ────────────────────────────────────────────────────────

    def compute_rewards(
        self,
        components: Dict[str, Any],
        regime: str = "NEUTRAL",
        signal: str = "",
    ) -> Tuple[float, List[str]]:
        """
        Hitung total reward berdasarkan 10 kondisi positif.

        Returns:
            (total_reward, explanations)  -- reward adalah angka positif
        """
        reward = 0.0
        reasons: List[str] = []
        s = self._safe

        adx       = s(components.get("adx", 0))
        vol_ratio = s(components.get("vol_ratio", 1.0))
        rsi       = s(components.get("rsi", 50))

        # 1. Strong Trend
        if adx > 40:
            r = 10.0
            reward += r
            reasons.append(f"+{r:.1f} Trend sangat kuat (ADX={adx:.0f})")
        elif adx > 25:
            r = 5.0
            reward += r
            reasons.append(f"+{r:.1f} Trend kuat (ADX={adx:.0f})")

        # 2. Breakout Volume
        if vol_ratio > 3.0:
            r = 12.0
            reward += r
            reasons.append(f"+{r:.1f} Volume breakout ({vol_ratio:.1f}x rata-rata)")
        elif vol_ratio > 2.0:
            r = 7.0
            reward += r
            reasons.append(f"+{r:.1f} Volume tinggi ({vol_ratio:.1f}x)")

        # 3. Liquidity Sweep
        liq_sweep = bool(components.get("liquidity_sweep", False))
        if liq_sweep:
            r = 8.0
            reward += r
            reasons.append(f"+{r:.1f} Liquidity Sweep valid")

        # 4. Order Block
        ob_valid = bool(components.get("order_block_valid", False))
        if ob_valid:
            r = 8.0
            reward += r
            reasons.append(f"+{r:.1f} Order Block valid")

        # 5. Fair Value Gap
        fvg_valid = bool(components.get("fvg_valid", False))
        if fvg_valid:
            r = 6.0
            reward += r
            reasons.append(f"+{r:.1f} Fair Value Gap valid")

        # 6. BTC sama arah
        btc_aligned = s(components.get("btc_aligned", 0))
        if btc_aligned > 0:
            r = 6.0
            reward += r
            reasons.append(f"+{r:.1f} BTC mendukung arah sinyal")

        # 7. ADX tinggi
        if adx > 50:
            r = 5.0
            reward += r
            reasons.append(f"+{r:.1f} ADX sangat tinggi ({adx:.0f})")

        # 8. Momentum tinggi (RSI ideal zone)
        if signal.upper().startswith("BUY") and 50 < rsi < 70:
            r = 4.0
            reward += r
            reasons.append(f"+{r:.1f} RSI di zona ideal BUY ({rsi:.0f})")
        elif signal.upper().startswith("SELL") and 30 < rsi < 50:
            r = 4.0
            reward += r
            reasons.append(f"+{r:.1f} RSI di zona ideal SELL ({rsi:.0f})")

        # 9. Regime mendukung
        if regime.upper() in ("TRENDING", "BREAKOUT"):
            r = 5.0
            reward += r
            reasons.append(f"+{r:.1f} Regime {regime} mendukung sinyal")

        # 10. SMC konfluens (order block + fvg + sweep bersamaan)
        smc_confluence = int(ob_valid) + int(fvg_valid) + int(liq_sweep)
        if smc_confluence >= 2:
            r = 8.0
            reward += r
            reasons.append(f"+{r:.1f} SMC konfluens ({smc_confluence}/3 komponen)")

        return round(reward, 2), reasons


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ADAPTIVE BRAIN V6
# ═══════════════════════════════════════════════════════════════════════════════

class AdaptiveBrainV6:
    """
    Central AI Brain V6 — self-learning, regime-aware, fully explainable.

    Publik API (backward compatible):
        get_threshold(market_context)       → float
        get_confidence(indicators, context) → float
        get_risk_params(context)            → dict
        update_weights(result, indicators, context) → None
        calibrate()                         → dict
        learn()                             → dict
        save() / load()
        get_brain()                         → dict

    API Baru V6:
        get_adaptive_score(components, regime, signal, symbol) → dict
        get_recommendation(score, context)                     → dict
        get_market_health(context)                             → dict
        get_ai_memory()                                        → dict
        get_performance_stats(days)                            → dict
        record_trade_result(trade_data)                        → None
    """

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        if state_dir is None:
            state_dir = Path(__file__).resolve().parent
        self.state_dir = state_dir
        self.memory    = PerformanceMemory(state_dir / "brain_memory.db")
        self.state     = BrainState()
        self._load_state()
        self.score_engine = AdaptiveScoreEngine(self.state.indicator_weights)
        self.lock = threading.RLock()

        # Cache untuk threshold per regime (TTL-based)
        self._threshold_cache: Dict[str, Tuple[float, float]] = {}  # regime → (threshold, ts)
        self._health_cache: Optional[Tuple[Dict, float]] = None

        logger.info(f"[BrainV6] Initialized v{VERSION} | "
                    f"Conservative={self.state.conservative_mode} | "
                    f"Weights={len(self.state.indicator_weights)}")

    # ═══════════════════════════════════════════════════════════════════════
    # STATE PERSISTENCE
    # ═══════════════════════════════════════════════════════════════════════

    def _state_file(self) -> Path:
        return self.state_dir / "brain_state.json"

    def _load_state(self) -> None:
        """Load state dari JSON + SQLite."""
        sf = self._state_file()
        if sf.exists():
            try:
                with open(sf, "r") as f:
                    data = json.load(f)
                self.state.decision_count    = data.get("decision_count", 0)
                self.state.version           = data.get("version", VERSION)
                self.state.conservative_mode = data.get("conservative_mode", False)

                lc = data.get("last_calibration")
                self.state.last_calibration = datetime.fromisoformat(lc) if lc else None

                cs = data.get("conservative_since")
                self.state.conservative_since = datetime.fromisoformat(cs) if cs else None

                # Load pair stats
                for sym, ps_data in data.get("pair_stats", {}).items():
                    self.state.pair_stats[sym] = PairStats(**{
                        k: v for k, v in ps_data.items()
                        if k in PairStats.__dataclass_fields__
                    })

                # Load session stats
                for sess, ss_data in data.get("session_stats", {}).items():
                    self.state.session_stats[sess] = SessionStats(**{
                        k: v for k, v in ss_data.items()
                        if k in SessionStats.__dataclass_fields__
                    })

                # Load regime stats
                for reg, rs_data in data.get("regime_stats", {}).items():
                    self.state.regime_stats[reg] = RegimeStats(**{
                        k: v for k, v in rs_data.items()
                        if k in RegimeStats.__dataclass_fields__
                    })

                # Load risk learning
                rl_data = data.get("risk_learning", {})
                if rl_data:
                    self.state.risk_learning = RiskLearning(**{
                        k: v for k, v in rl_data.items()
                        if k in RiskLearning.__dataclass_fields__
                    })

                # Load AI memory
                am_data = data.get("ai_memory", {})
                if am_data:
                    self.state.ai_memory = AIMemory(**{
                        k: v for k, v in am_data.items()
                        if k in AIMemory.__dataclass_fields__
                    })

                # Load recent results
                recent = data.get("recent_results", [])
                self.state.recent_results = deque(recent, maxlen=20)

            except Exception as e:
                logger.warning(f"[BrainV6] Load state error: {e}")

        # Load indicator weights dari SQLite
        db_weights = self.memory.load_indicator_weights()
        if db_weights:
            self.state.indicator_weights = db_weights
        else:
            self._init_default_weights()

    def _save_state(self) -> None:
        """Simpan state lengkap ke JSON + SQLite."""
        try:
            data = {
                "decision_count":    self.state.decision_count,
                "version":           self.state.version,
                "conservative_mode": self.state.conservative_mode,
                "last_calibration":  (
                    self.state.last_calibration.isoformat()
                    if self.state.last_calibration else None
                ),
                "conservative_since": (
                    self.state.conservative_since.isoformat()
                    if self.state.conservative_since else None
                ),
                "pair_stats": {
                    sym: {f: getattr(ps, f) for f in PairStats.__dataclass_fields__}
                    for sym, ps in self.state.pair_stats.items()
                },
                "session_stats": {
                    sess: {f: getattr(ss, f) for f in SessionStats.__dataclass_fields__}
                    for sess, ss in self.state.session_stats.items()
                },
                "regime_stats": {
                    reg: {f: getattr(rs, f) for f in RegimeStats.__dataclass_fields__}
                    for reg, rs in self.state.regime_stats.items()
                },
                "risk_learning": {
                    f: getattr(self.state.risk_learning, f)
                    for f in RiskLearning.__dataclass_fields__
                },
                "ai_memory": {
                    f: getattr(self.state.ai_memory, f)
                    for f in AIMemory.__dataclass_fields__
                },
                "recent_results": list(self.state.recent_results),
            }
            with open(self._state_file(), "w") as f:
                json.dump(data, f, indent=2, default=str)

            self.memory.save_indicator_weights(self.state.indicator_weights)
        except Exception as e:
            logger.error(f"[BrainV6] Save state error: {e}")

    def _init_default_weights(self) -> None:
        """Inisialisasi bobot default semua indikator."""
        defaults = {
            "trend":          0.20,
            "momentum":       0.15,
            "volume":         0.15,
            "volatility":     0.08,
            "btc_trend":      0.08,
            "regime":         0.06,
            "confidence":     0.08,
            "institutional":  0.06,
            "order_block":    0.05,
            "fvg":            0.04,
            "liquidity_sweep":0.05,
            # Indikator teknikal individual
            "ema":            0.50,
            "rsi":            0.40,
            "macd":           0.45,
            "vwap":           0.35,
            "adx":            0.40,
            "supertrend":     0.35,
            "atr":            0.30,
            "bos":            0.25,
            "choch":          0.25,
            "breakout":       0.35,
            "volume_spike":   0.40,
        }
        now = datetime.now(timezone.utc)
        for name, w in defaults.items():
            self.state.indicator_weights[name] = IndicatorWeight(
                name=name, weight=w, last_updated=now
            )

    # ═══════════════════════════════════════════════════════════════════════
    # SESSION DETECTION
    # ═══════════════════════════════════════════════════════════════════════

    def _get_current_session(self, hour: Optional[int] = None) -> str:
        """Deteksi session trading berdasarkan jam UTC."""
        if hour is None:
            hour = datetime.now(timezone.utc).hour
        if 0 <= hour < 8:
            return "ASIA"
        elif 7 <= hour < 16:
            return "LONDON"
        elif 13 <= hour < 22:
            return "NEW_YORK"
        return "OFF"

    # ═══════════════════════════════════════════════════════════════════════
    # 3. DYNAMIC THRESHOLD
    # ═══════════════════════════════════════════════════════════════════════

    def get_threshold(self, market_context: Dict[str, Any]) -> float:
        """
        Hitung threshold dinamis berdasarkan regime + learning history.
        Threshold berubah otomatis mengikuti performa.

        Backward compatible dengan API lama.
        """
        regime = ""
        raw_regime = market_context.get("regime", "NEUTRAL")
        if isinstance(raw_regime, dict):
            regime = raw_regime.get("trend", raw_regime.get("regime", "NEUTRAL"))
        else:
            regime = str(raw_regime)
        regime = regime.upper()

        # Cache check
        cache_key = regime
        cached = self._threshold_cache.get(cache_key)
        if cached and (time.time() - cached[1]) < CACHE_TTL:
            base_threshold = cached[0]
        else:
            # Base threshold per regime
            base_threshold = BASE_THRESHOLD.get(regime, 65.0)

            # Modifier dari regime learning
            rs = self.state.regime_stats.get(regime)
            if rs and rs.total >= 10:
                base_threshold += rs.threshold_modifier

            self._threshold_cache[cache_key] = (base_threshold, time.time())

        threshold = base_threshold

        # Conservative mode: naikkan threshold
        if self.state.conservative_mode:
            threshold += RECOVERY_THRESHOLD_BUMP
            logger.debug(f"[BrainV6] Conservative mode aktif, threshold +{RECOVERY_THRESHOLD_BUMP}")

        # Fear & Greed modifier
        fg = market_context.get("fear_greed", 50)
        if isinstance(fg, dict):
            fg = fg.get("value", 50)
        fg = float(fg) if fg else 50.0
        if fg <= 20:
            threshold -= 12
        elif fg <= 40:
            threshold -= 6
        elif fg >= 80:
            threshold += 5

        # BTC Trend modifier
        btc_trend = market_context.get("btc_trend", "NEUTRAL")
        btc_str = (btc_trend.get("trend", "") if isinstance(btc_trend, dict) else str(btc_trend)).upper()
        if "UP" in btc_str:
            threshold -= 3
        elif "DOWN" in btc_str:
            threshold -= 8

        # ATR ratio
        atr_ratio = float(market_context.get("atr_ratio", 1.0) or 1.0)
        if atr_ratio > 1.5:
            threshold += 5
        elif atr_ratio < 0.7:
            threshold -= 3

        # Session modifier
        session = self._get_current_session()
        ss = self.state.session_stats.get(session)
        if ss and ss.total >= 5:
            # Session dengan win_rate < 40% → threshold naik
            if ss.win_rate < 40:
                threshold += 8
            elif ss.win_rate > 65:
                threshold -= 5

        return round(min(90.0, max(30.0, threshold)), 1)

    # ═══════════════════════════════════════════════════════════════════════
    # 8. CONFIDENCE LEARNING
    # ═══════════════════════════════════════════════════════════════════════

    def get_confidence(
        self,
        indicators: Dict[str, Any],
        market_context: Dict[str, Any],
    ) -> float:
        """
        Hitung confidence score 0-100 dari multiple faktor.
        Backward compatible dengan API lama.
        """
        regime = ""
        raw_regime = market_context.get("regime", "NEUTRAL")
        if isinstance(raw_regime, dict):
            regime = raw_regime.get("trend", "NEUTRAL")
        else:
            regime = str(raw_regime)
        regime = regime.upper()

        def _s(v, d=0.0):
            try:
                val = float(v)
                return d if (val != val or abs(val) == float('inf')) else val
            except:
                return d

        rsi      = _s(indicators.get("rsi", 50))
        adx      = _s(indicators.get("adx", 0))
        vol_r    = _s(indicators.get("vol_ratio", 1.0))
        macd_h   = _s(indicators.get("macd_hist", 0))
        close    = max(_s(indicators.get("close", 1), 1), 1e-9)
        sr_pos   = _s(indicators.get("sr_pos", 0.5))
        liquidity = _s(indicators.get("liquidity_score", 50))
        smc      = _s(indicators.get("smc_score", 0))
        inst     = _s(indicators.get("institutional_score", 0))

        # Hitung komponen
        trend_score  = min(100.0, adx * 2.5)
        volume_score = min(100.0, vol_r * 50)
        macd_norm    = min(100.0, max(0.0, (macd_h / (close * 0.01 + 1e-9)) * 50 + 50))
        momentum     = macd_norm * 0.6 + abs(rsi - 50) * 2 * 0.4
        sr_score     = round(abs(sr_pos - 0.5) * 200, 1)
        atr_pct      = (_s(indicators.get("atr", 0)) / close * 100)
        volatility   = min(100.0, atr_pct * 20)

        weights_map = {
            "TRENDING": {"trend": 0.35, "volume": 0.20, "momentum": 0.20,
                         "sr": 0.10, "liquidity": 0.08, "smc": 0.07},
            "RANGING":  {"sr": 0.30, "volume": 0.20, "trend": 0.15,
                         "momentum": 0.15, "liquidity": 0.12, "smc": 0.08},
            "VOLATILE": {"volatility": 0.25, "volume": 0.20, "trend": 0.20,
                         "momentum": 0.15, "sr": 0.12, "smc": 0.08},
            "NEUTRAL":  {"trend": 0.25, "sr": 0.20, "volume": 0.20,
                         "momentum": 0.15, "liquidity": 0.12, "smc": 0.08},
        }
        w = weights_map.get(regime, weights_map["NEUTRAL"])

        confidence = (
            trend_score  * w.get("trend",      0.25) +
            volume_score * w.get("volume",      0.20) +
            momentum     * w.get("momentum",    0.15) +
            sr_score     * w.get("sr",          0.15) +
            liquidity    * w.get("liquidity",   0.10) +
            smc          * w.get("smc",         0.10) +
            volatility   * w.get("volatility",  0.00) +
            inst         * 0.05
        )

        # Pair confidence modifier
        symbol = market_context.get("symbol", "")
        if symbol:
            ps = self.state.pair_stats.get(symbol)
            if ps and ps.total >= 5:
                confidence += ps.confidence_modifier

        # Session modifier
        session = self._get_current_session()
        ss = self.state.session_stats.get(session)
        if ss and ss.total >= 5:
            confidence += ss.score_modifier

        return round(min(100.0, max(0.0, confidence)), 2)

    def get_confidence_level(self, confidence: float) -> str:
        """Konversi confidence float → label string."""
        if confidence >= CONFIDENCE_LEVELS["VERY_HIGH"]:
            return "VERY_HIGH"
        elif confidence >= CONFIDENCE_LEVELS["HIGH"]:
            return "HIGH"
        elif confidence >= CONFIDENCE_LEVELS["MEDIUM"]:
            return "MEDIUM"
        elif confidence >= CONFIDENCE_LEVELS["LOW"]:
            return "LOW"
        return "VERY_LOW"

    # ═══════════════════════════════════════════════════════════════════════
    # 2. ADAPTIVE SCORE (NEW V6 - Main Scoring)
    # ═══════════════════════════════════════════════════════════════════════

    def get_adaptive_score(
        self,
        components: Dict[str, Any],
        regime: str = "NEUTRAL",
        signal: str = "",
        symbol: str = "",
        hour: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Hitung Adaptive Score lengkap dengan Penalty + Reward + Explainable AI.

        Returns dict dengan:
            score_raw        : float (sebelum penalty/reward)
            score_final      : float (setelah penalty/reward, 0-100)
            penalty_total    : float (negatif)
            reward_total     : float (positif)
            explanations     : list[str] (setiap langkah ada alasannya)
            breakdown        : dict (kontribusi per komponen)
            confidence       : float
            confidence_level : str
            session          : str
            pair_modifier    : float
            session_modifier : float
        """
        with self.lock:
            engine = self.score_engine

            # Score dasar dari 11 komponen
            score_raw, base_explains, breakdown = engine.compute(components, regime)

            # Penalty
            penalty, penalty_reasons = engine.compute_penalties(components, regime, signal)

            # Reward
            reward, reward_reasons  = engine.compute_rewards(components, regime, signal)

            # Gabung
            score_final = score_raw + penalty + reward

            # Pair modifier
            pair_modifier = 0.0
            if symbol:
                ps = self.state.pair_stats.get(symbol)
                if ps and ps.total >= 5:
                    pair_modifier = ps.confidence_modifier
                    score_final += pair_modifier
                    if pair_modifier < -5:
                        base_explains.append(f"{pair_modifier:.1f} Pair {symbol} sering loss")
                    elif pair_modifier > 5:
                        base_explains.append(f"+{pair_modifier:.1f} Pair {symbol} performa bagus")

            # Session modifier
            session = self._get_current_session(hour)
            session_modifier = 0.0
            ss = self.state.session_stats.get(session)
            if ss and ss.total >= 5:
                session_modifier = ss.score_modifier
                score_final += session_modifier
                if session_modifier < -3:
                    base_explains.append(f"{session_modifier:.1f} Session {session} kurang optimal")
                elif session_modifier > 3:
                    base_explains.append(f"+{session_modifier:.1f} Session {session} performa baik")

            # Conservative mode penalty
            if self.state.conservative_mode:
                score_final -= 10.0
                base_explains.append("-10.0 Mode konservatif aktif (recovery mode)")

            score_final = round(min(100.0, max(0.0, score_final)), 2)

            # Confidence
            confidence = self.get_confidence(components, {
                "regime": regime,
                "symbol": symbol,
            })
            conf_level = self.get_confidence_level(confidence)

            # Semua penjelasan digabung
            all_explanations = base_explains + penalty_reasons + reward_reasons

            return {
                "score_raw":        round(score_raw, 2),
                "score_final":      score_final,
                "penalty_total":    penalty,
                "reward_total":     reward,
                "explanations":     all_explanations,
                "breakdown":        breakdown,
                "confidence":       confidence,
                "confidence_level": conf_level,
                "session":          session,
                "pair_modifier":    round(pair_modifier, 2),
                "session_modifier": round(session_modifier, 2),
                "regime":           regime,
                "conservative_mode": self.state.conservative_mode,
            }

    # ═══════════════════════════════════════════════════════════════════════
    # 13. AI RECOMMENDATION
    # ═══════════════════════════════════════════════════════════════════════

    def get_recommendation(
        self,
        score: float,
        market_context: Dict[str, Any],
        symbol: str = "",
        signal: str = "",
    ) -> Dict[str, Any]:
        """
        Berikan rekomendasi: ALLOW / CAUTION / SKIP dengan alasan jelas.
        """
        threshold = self.get_threshold(market_context)
        regime    = str(market_context.get("regime", "NEUTRAL"))
        if isinstance(market_context.get("regime"), dict):
            regime = market_context["regime"].get("trend", "NEUTRAL")
        regime = regime.upper()

        reasons: List[str] = []
        caution_reasons: List[str] = []

        # Cek pair stats
        skip_pair = False
        if symbol:
            ps = self.state.pair_stats.get(symbol)
            if ps and ps.total >= 5:
                if ps.win_rate < 30:
                    skip_pair = True
                    reasons.append(f"Win rate {symbol} hanya {ps.win_rate:.0f}% (threshold: 30%)")
                elif ps.consecutive_loss >= 4:
                    skip_pair = True
                    reasons.append(f"{symbol} consecutive loss: {ps.consecutive_loss}")
                elif ps.win_rate < 45:
                    caution_reasons.append(f"Win rate {symbol} rendah: {ps.win_rate:.0f}%")

        # Cek session
        session = self._get_current_session()
        ss = self.state.session_stats.get(session)
        if ss and ss.total >= 10 and ss.win_rate < 35:
            caution_reasons.append(f"Session {session} win rate rendah: {ss.win_rate:.0f}%")

        # Cek conservative mode
        if self.state.conservative_mode:
            caution_reasons.append("Mode konservatif aktif karena 5+ loss berturut")

        # Cek score vs threshold
        score_gap = score - threshold
        if score < threshold - 15:
            reasons.append(f"Score {score:.1f} jauh di bawah threshold {threshold:.1f}")

        # Tentukan rekomendasi
        if skip_pair or score < threshold - 10:
            recommendation = "SKIP"
            if not reasons:
                reasons.append(f"Score {score:.1f} < threshold {threshold:.1f}")
        elif len(caution_reasons) > 0 or (score < threshold + 5):
            recommendation = "CAUTION"
            reasons.extend(caution_reasons)
            if not reasons:
                reasons.append(f"Score {score:.1f} mendekati threshold {threshold:.1f}")
        else:
            recommendation = "ALLOW"
            reasons.append(f"Score {score:.1f} melebihi threshold {threshold:.1f} dengan margin {score_gap:.1f}")

        return {
            "recommendation": recommendation,
            "score":          round(score, 2),
            "threshold":      round(threshold, 1),
            "score_gap":      round(score_gap, 2),
            "regime":         regime,
            "session":        session,
            "reasons":        reasons,
            "conservative":   self.state.conservative_mode,
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 17. MARKET HEALTH SCORE
    # ═══════════════════════════════════════════════════════════════════════

    def get_market_health(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hitung Market Health Score 0-100 dari 6 faktor.
        Cache 5 menit untuk performa.
        """
        now = time.time()
        if self._health_cache and (now - self._health_cache[1]) < CACHE_TTL:
            return self._health_cache[0]

        def _s(v, d=50.0):
            try:
                val = float(v)
                return d if (val != val or abs(val) == float('inf')) else val
            except:
                return d

        # 1. Trend (dari ADX)
        adx = _s(context.get("adx", 25))
        trend_health = min(100.0, adx * 2.5)

        # 2. Volume
        vol_ratio = _s(context.get("vol_ratio", 1.0))
        volume_health = min(100.0, vol_ratio * 50)

        # 3. ATR (volatility dalam range sehat)
        atr_ratio = _s(context.get("atr_ratio", 1.0))
        if 0.7 <= atr_ratio <= 1.5:
            atr_health = 80.0
        elif atr_ratio > 2.0:
            atr_health = 40.0
        else:
            atr_health = 60.0

        # 4. BTC
        btc_strength = _s(context.get("btc_strength", 50))
        btc_health   = btc_strength

        # 5. Funding rate (semakin jauh dari 0 = kurang sehat)
        funding = abs(_s(context.get("funding_rate", 0), 0.0))
        funding_health = max(0.0, 100.0 - funding * 50000)

        # 6. Open Interest
        oi_change = _s(context.get("oi_change_pct", 0), 0.0)
        oi_health  = 60.0 + min(40.0, max(-60.0, oi_change * 5))

        # Weighted average
        health_score = (
            trend_health   * 0.25 +
            volume_health  * 0.20 +
            atr_health     * 0.15 +
            btc_health     * 0.20 +
            funding_health * 0.10 +
            oi_health      * 0.10
        )
        health_score = round(min(100.0, max(0.0, health_score)), 1)

        # Label
        if health_score >= 75:
            label = "SEHAT"
        elif health_score >= 55:
            label = "NORMAL"
        elif health_score >= 35:
            label = "LEMAH"
        else:
            label = "BAHAYA"

        result = {
            "health_score":  health_score,
            "label":         label,
            "components": {
                "trend":   round(trend_health, 1),
                "volume":  round(volume_health, 1),
                "atr":     round(atr_health, 1),
                "btc":     round(btc_health, 1),
                "funding": round(funding_health, 1),
                "oi":      round(oi_health, 1),
            }
        }
        self._health_cache = (result, now)
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # RISK PARAMS (backward compatible + V6 risk learning)
    # ═══════════════════════════════════════════════════════════════════════

    def get_risk_params(self, market_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return parameter risk termasuk rekomendasi SL/TP dari risk learning.
        """
        regime = ""
        raw_regime = market_context.get("regime", "NEUTRAL")
        if isinstance(raw_regime, dict):
            regime = raw_regime.get("trend", "NEUTRAL")
        else:
            regime = str(raw_regime)
        regime = regime.upper()

        confidence = float(market_context.get("confidence", 50) or 50)

        # Base dari regime
        regime_params = {
            "TRENDING":   {"sl_mult": 1.2, "tp_mult": 1.3, "pos_mult": 1.0},
            "RANGING":    {"sl_mult": 0.8, "tp_mult": 0.9, "pos_mult": 0.8},
            "VOLATILE":   {"sl_mult": 1.5, "tp_mult": 1.2, "pos_mult": 0.5},
            "BREAKOUT":   {"sl_mult": 1.3, "tp_mult": 1.5, "pos_mult": 1.0},
            "WEAK_TREND": {"sl_mult": 1.0, "tp_mult": 1.0, "pos_mult": 0.7},
            "NEUTRAL":    {"sl_mult": 1.0, "tp_mult": 1.0, "pos_mult": 0.8},
        }
        params = regime_params.get(regime, regime_params["NEUTRAL"]).copy()

        # Risk learning overlay
        rl = self.state.risk_learning
        params["sl_mult"] *= rl.recommended_sl_mult
        params["tp_mult"] *= rl.recommended_tp_mult

        # Confidence-based position sizing
        if confidence >= 80:
            params["pos_mult"] = min(1.0, params["pos_mult"] * 1.0)
        elif confidence >= 65:
            params["pos_mult"] = min(0.8, params["pos_mult"] * 0.9)
        else:
            params["pos_mult"] = min(0.5, params["pos_mult"] * 0.7)

        # Conservative mode
        if self.state.conservative_mode:
            params["pos_mult"] *= 0.5
            params["sl_mult"]  *= 1.2

        params["max_positions"] = 3 if self.state.conservative_mode else 5
        params["regime"]        = regime
        params["conservative"]  = self.state.conservative_mode
        params["sl_recommendation"] = (
            "Perlebar SL" if rl.sl_too_tight_count > rl.sl_too_wide_count * 2
            else "SL normal"
        )

        return params

    # ═══════════════════════════════════════════════════════════════════════
    # 1. SELF LEARNING ENGINE — update_weights
    # ═══════════════════════════════════════════════════════════════════════

    def update_weights(
        self,
        result: str,                        # "WIN" atau "LOSS"
        indicators: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        profit: float = 0.0,
        loss: float = 0.0,
    ) -> None:
        """
        Update bobot indikator berdasarkan hasil trade (WIN/LOSS).
        Backward compatible dengan API lama.
        """
        with self.lock:
            success  = result.upper() == "WIN"
            context  = context or {}
            symbol   = context.get("symbol", "")
            regime   = context.get("regime", "NEUTRAL")
            if isinstance(regime, dict):
                regime = regime.get("trend", regime.get("regime", "NEUTRAL"))
            regime = str(regime).upper()

            # ── Update indicator weights (Auto Weight Optimizer) ──
            for name in indicators:
                iw = self.state.indicator_weights.get(name)
                if iw is None:
                    iw = IndicatorWeight(name=name, weight=0.3)
                    self.state.indicator_weights[name] = iw

                iw.hits   += 1 if success else 0
                iw.misses += 0 if success else 1

                total = iw.hits + iw.misses
                if total >= 3:
                    hit_rate = iw.hits / total
                    target   = max(WEIGHT_MIN, min(WEIGHT_MAX, hit_rate * WEIGHT_MAX * 2))
                    iw.weight = iw.weight * (1 - WEIGHT_LEARNING_RATE) + target * WEIGHT_LEARNING_RATE
                iw.last_updated = datetime.now(timezone.utc)

            # ── Update Pair Stats ──
            if symbol:
                ps = self.state.pair_stats.get(symbol)
                if ps is None:
                    ps = PairStats(symbol=symbol)
                    self.state.pair_stats[symbol] = ps

                ps.total += 1
                if success:
                    ps.wins           += 1
                    ps.consecutive_loss = 0
                    ps.total_profit   += profit
                    # Confidence naik pelan-pelan
                    ps.confidence_modifier = min(20.0, ps.confidence_modifier + 1.0)
                else:
                    ps.losses           += 1
                    ps.consecutive_loss += 1
                    ps.total_loss       += loss
                    # Confidence turun sesuai consecutive loss
                    ps.confidence_modifier = max(-20.0, ps.confidence_modifier - 2.0)

                ps.last_updated = datetime.now(timezone.utc).isoformat()

            # ── Update Session Stats ──
            session = context.get("session", self._get_current_session())
            ss = self.state.session_stats.get(session)
            if ss is None:
                ss = SessionStats(session=session)
                self.state.session_stats[session] = ss
            ss.total += 1
            if success:
                ss.wins += 1

            if ss.total >= 5:
                # Modifier: -10 s/d +10 berdasarkan win rate vs 50%
                wr_delta = (ss.win_rate - 50.0) / 5.0
                ss.score_modifier = round(max(-10.0, min(10.0, wr_delta)), 2)

            # ── Update Regime Stats ──
            rs = self.state.regime_stats.get(regime)
            if rs is None:
                rs = RegimeStats(regime=regime)
                self.state.regime_stats[regime] = rs
            rs.total += 1
            if success:
                rs.wins += 1

            if rs.total >= 10:
                # Auto-adjust threshold modifier berdasarkan win rate
                if rs.win_rate > 65:
                    rs.threshold_modifier = max(-10.0, rs.threshold_modifier - 0.5)
                elif rs.win_rate < 40:
                    rs.threshold_modifier = min(15.0, rs.threshold_modifier + 1.0)

            # ── Update Risk Learning ──
            sl_hit  = bool(context.get("sl_hit", False))
            tp1_hit = bool(context.get("tp1_hit", False))
            tp2_hit = bool(context.get("tp2_hit", False))
            rl = self.state.risk_learning

            if sl_hit:
                rl.sl_too_tight_count += 1
            if not sl_hit and not success:
                rl.sl_too_wide_count += 1

            # Update TP hit rates (running average)
            n = max(self.state.decision_count, 1)
            rl.tp1_hit_rate = rl.tp1_hit_rate * 0.95 + int(tp1_hit) * 0.05
            rl.tp2_hit_rate = rl.tp2_hit_rate * 0.95 + int(tp2_hit) * 0.05

            # Rekomendasi SL multiplier
            if rl.sl_too_tight_count > 10 and rl.sl_too_tight_count > rl.sl_too_wide_count * 2:
                rl.recommended_sl_mult = min(1.5, rl.recommended_sl_mult + 0.05)
            elif rl.sl_too_wide_count > rl.sl_too_tight_count * 2:
                rl.recommended_sl_mult = max(0.8, rl.recommended_sl_mult - 0.03)

            # ── Smart Recovery ──
            self.state.recent_results.append(1 if success else 0)
            self._check_smart_recovery()

            # ── Save trade to memory ──
            trade_record = {
                "symbol":     symbol,
                "signal":     context.get("signal", ""),
                "confidence": context.get("confidence", 0.0),
                "regime":     regime,
                "session":    session,
                "setup_type": context.get("setup_type", ""),
                "score":      context.get("score", 0.0),
                "indicators": indicators,
                "profit":     profit,
                "loss":       loss,
                "rr_actual":  context.get("rr_actual", 0.0),
                "sl_hit":     sl_hit,
                "tp1_hit":    tp1_hit,
                "tp2_hit":    tp2_hit,
            }
            self.memory.save_trade(trade_record)

            self.state.decision_count += 1
            self._save_state()

    def record_trade_result(self, trade_data: Dict[str, Any]) -> None:
        """
        Alias untuk update_weights — interface V6 yang lebih ekspresif.

        trade_data keys:
            result, symbol, signal, regime, session, confidence, score,
            profit, loss, rr_actual, sl_hit, tp1_hit, tp2_hit,
            indicators, setup_type
        """
        self.update_weights(
            result     = trade_data.get("result", "LOSS"),
            indicators = trade_data.get("indicators", {}),
            context    = trade_data,
            profit     = trade_data.get("profit", 0.0),
            loss       = trade_data.get("loss", 0.0),
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 15. SMART RECOVERY
    # ═══════════════════════════════════════════════════════════════════════

    def _check_smart_recovery(self) -> None:
        """
        Aktifkan/deaktifkan mode konservatif berdasarkan 5 trade terakhir.
        """
        recent = list(self.state.recent_results)
        if len(recent) < 5:
            return

        last_5  = recent[-5:]
        last_3  = recent[-3:]
        n_loss  = last_5.count(0)
        n_win_3 = last_3.count(1)

        if n_loss >= RECOVERY_LOSS_TRIGGER and not self.state.conservative_mode:
            self.state.conservative_mode  = True
            self.state.conservative_since = datetime.now(timezone.utc)
            # Clear threshold cache
            self._threshold_cache.clear()
            logger.warning(
                f"[BrainV6] 🚨 SMART RECOVERY AKTIF — {n_loss}/5 loss terakhir. "
                "Mode konservatif diaktifkan."
            )
        elif self.state.conservative_mode and n_win_3 >= RECOVERY_MIN_WIN_TO_RELAX:
            self.state.conservative_mode  = False
            self.state.conservative_since = None
            self._threshold_cache.clear()
            logger.info(
                f"[BrainV6] ✅ Smart Recovery selesai — {n_win_3}/3 win terakhir. "
                "Kembali ke mode normal."
            )

    # ═══════════════════════════════════════════════════════════════════════
    # 12. PERFORMANCE DATABASE
    # ═══════════════════════════════════════════════════════════════════════

    def get_performance_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Ambil statistik performa lengkap dari database.
        Returns Performance Database per spec:
            total_trades, wins, losses, win_rate, avg_rr,
            avg_profit, avg_loss, profit_factor, expectancy, max_drawdown
        """
        stats = self.memory.get_global_stats(days)

        # Max Drawdown (simplified: worst consecutive loss * avg_loss)
        trades = self.memory.load_recent_trades(days)
        max_dd = self._calc_max_drawdown(trades)
        stats["max_drawdown"] = round(max_dd, 4)

        # Top pairs
        pair_perf = {}
        for sym, ps in self.state.pair_stats.items():
            if ps.total >= 3:
                pair_perf[sym] = {
                    "total": ps.total,
                    "win_rate": round(ps.win_rate, 1),
                    "consecutive_loss": ps.consecutive_loss,
                    "confidence_modifier": round(ps.confidence_modifier, 2),
                }
        stats["pair_performance"]   = pair_perf
        stats["session_performance"] = {
            sess: {"total": ss.total, "win_rate": round(ss.win_rate, 1),
                   "score_modifier": round(ss.score_modifier, 2)}
            for sess, ss in self.state.session_stats.items()
        }
        stats["regime_performance"] = {
            reg: {"total": rs.total, "win_rate": round(rs.win_rate, 1),
                  "threshold_modifier": round(rs.threshold_modifier, 2)}
            for reg, rs in self.state.regime_stats.items()
        }
        stats["conservative_mode"]  = self.state.conservative_mode
        stats["sl_rec"]             = self.state.risk_learning.recommended_sl_mult

        return stats

    def _calc_max_drawdown(self, trades: List[Dict]) -> float:
        """Hitung max drawdown dari daftar trades."""
        if not trades:
            return 0.0
        equity = 0.0
        peak   = 0.0
        max_dd = 0.0
        for t in reversed(trades):  # reversed = chronological
            pnl     = float(t.get("profit", 0) or 0) - abs(float(t.get("loss", 0) or 0))
            equity += pnl
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        return max_dd

    # ═══════════════════════════════════════════════════════════════════════
    # 18. AI MEMORY
    # ═══════════════════════════════════════════════════════════════════════

    def get_ai_memory(self) -> Dict[str, Any]:
        """
        Return AI Memory: best/worst pairs, sessions, setups, regime.
        """
        self._refresh_ai_memory()
        am = self.state.ai_memory
        return {
            "best_pairs":    am.best_pairs[:5],
            "worst_pairs":   am.worst_pairs[:5],
            "best_sessions": am.best_sessions,
            "worst_sessions":am.worst_sessions,
            "best_regime":   am.best_regime,
            "best_setups":   am.best_setups[:3],
            "worst_setups":  am.worst_setups[:3],
            "total_decisions": am.total_decisions,
            "last_updated":  am.last_updated,
        }

    def _refresh_ai_memory(self) -> None:
        """Perbarui AI Memory dari statistik terkini."""
        am = self.state.ai_memory
        am.total_decisions = self.state.decision_count

        # Best/worst pairs
        pairs_by_wr = sorted(
            [(sym, ps.win_rate) for sym, ps in self.state.pair_stats.items() if ps.total >= 5],
            key=lambda x: x[1], reverse=True
        )
        am.best_pairs  = [p[0] for p in pairs_by_wr[:5]]
        am.worst_pairs = [p[0] for p in pairs_by_wr[-5:]]

        # Best/worst sessions
        sess_by_wr = sorted(
            [(sess, ss.win_rate) for sess, ss in self.state.session_stats.items() if ss.total >= 5],
            key=lambda x: x[1], reverse=True
        )
        am.best_sessions  = [s[0] for s in sess_by_wr if s[1] >= 55]
        am.worst_sessions = [s[0] for s in sess_by_wr if s[1] < 45]

        # Best regime
        regimes_by_wr = sorted(
            [(reg, rs.win_rate) for reg, rs in self.state.regime_stats.items() if rs.total >= 5],
            key=lambda x: x[1], reverse=True
        )
        if regimes_by_wr:
            am.best_regime = regimes_by_wr[0][0]

        am.last_updated = datetime.now(timezone.utc).isoformat()

    # ═══════════════════════════════════════════════════════════════════════
    # 6. CALIBRATION
    # ═══════════════════════════════════════════════════════════════════════

    def calibrate(self) -> Dict[str, Any]:
        """
        Kalibrasi harian: normalisasi bobot, prune memory, refresh stats.
        """
        now = datetime.now(timezone.utc)
        if (
            self.state.last_calibration
            and (now - self.state.last_calibration) < timedelta(hours=23)
        ):
            return {"status": "skipped", "reason": "already calibrated within 24h"}

        with self.lock:
            # Prune old data
            deleted = self.memory.prune_old_data(90)

            # Normalisasi bobot (clamp, tidak reset)
            for iw in self.state.indicator_weights.values():
                iw.weight = max(WEIGHT_MIN, min(WEIGHT_MAX, iw.weight))

            # Stats global
            stats = self.memory.get_global_stats(30)

            # Refresh AI memory
            self._refresh_ai_memory()

            # Update risk learning dari DB
            sl_stats = self.memory.get_sl_stats(30)
            total_t  = sl_stats.get("total") or 1
            rl = self.state.risk_learning
            rl.tp1_hit_rate = (sl_stats.get("tp1_hits") or 0) / total_t
            rl.tp2_hit_rate = (sl_stats.get("tp2_hits") or 0) / total_t

            self.state.last_calibration = now
            self._save_state()

            result = {
                "status":            "calibrated",
                "deleted_records":   deleted,
                "active_weights":    len(self.state.indicator_weights),
                "recent_trades_30d": stats.get("total_trades", 0),
                "win_rate_30d":      stats.get("win_rate", 0.0),
                "conservative_mode": self.state.conservative_mode,
                "last_calibration":  now.isoformat(),
            }
            logger.info(
                f"[BrainV6] Calibrated — {stats.get('total_trades',0)} trades, "
                f"WR={stats.get('win_rate',0):.1f}%, pruned={deleted}"
            )
            return result

    def learn(self) -> Dict[str, Any]:
        """Orchestrator — trigger calibration + memory refresh."""
        self._refresh_ai_memory()
        return self.calibrate()

    # ═══════════════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════════════

    def save(self) -> None:
        """Simpan state Brain."""
        self._save_state()
        logger.debug("[BrainV6] State saved.")

    def load(self) -> None:
        """Load state Brain."""
        self._load_state()
        self.score_engine = AdaptiveScoreEngine(self.state.indicator_weights)
        logger.debug("[BrainV6] State loaded.")

    # ═══════════════════════════════════════════════════════════════════════
    # GET FULL SNAPSHOT
    # ═══════════════════════════════════════════════════════════════════════

    def get_brain(self) -> Dict[str, Any]:
        """Return snapshot lengkap state Brain V6."""
        return {
            "version":          self.state.version,
            "decision_count":   self.state.decision_count,
            "conservative_mode":self.state.conservative_mode,
            "last_calibration": (
                self.state.last_calibration.isoformat()
                if self.state.last_calibration else None
            ),
            "indicator_count":  len(self.state.indicator_weights),
            "weights": {
                name: {
                    "weight":    round(iw.weight, 4),
                    "hits":      iw.hits,
                    "misses":    iw.misses,
                    "hit_rate":  round(iw.hit_rate, 3),
                }
                for name, iw in self.state.indicator_weights.items()
            },
            "pair_stats_count":    len(self.state.pair_stats),
            "session_stats":       {
                sess: {"wr": round(ss.win_rate, 1), "mod": ss.score_modifier}
                for sess, ss in self.state.session_stats.items()
            },
            "regime_stats": {
                reg: {"wr": round(rs.win_rate, 1), "mod": rs.threshold_modifier}
                for reg, rs in self.state.regime_stats.items()
            },
            "risk_learning": {
                "sl_mult_rec":  self.state.risk_learning.recommended_sl_mult,
                "tp1_hit_rate": round(self.state.risk_learning.tp1_hit_rate, 3),
                "tp2_hit_rate": round(self.state.risk_learning.tp2_hit_rate, 3),
            },
            "ai_memory": self.get_ai_memory(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON + BACKWARD COMPATIBLE CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

_brain_instance: Optional[AdaptiveBrainV6] = None
_brain_lock = threading.Lock()


def get_brain() -> AdaptiveBrainV6:
    """Singleton accessor — thread-safe."""
    global _brain_instance
    with _brain_lock:
        if _brain_instance is None:
            _brain_instance = AdaptiveBrainV6()
        return _brain_instance


# ── Backward compatible module-level functions ───────────────────────────────

def get_threshold(market_context: Dict[str, Any]) -> float:
    """Backward compatible: get dynamic threshold."""
    return get_brain().get_threshold(market_context)


def get_confidence(
    indicators: Dict[str, Any],
    market_context: Dict[str, Any],
) -> float:
    """Backward compatible: get confidence score."""
    return get_brain().get_confidence(indicators, market_context)


def get_risk_params(market_context: Dict[str, Any]) -> Dict[str, Any]:
    """Backward compatible: get risk parameters."""
    return get_brain().get_risk_params(market_context)


def update_weights(
    result: str,
    indicators: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    profit: float = 0.0,
    loss: float = 0.0,
) -> None:
    """Backward compatible: update indicator weights after trade."""
    get_brain().update_weights(result, indicators, context, profit, loss)


def calibrate_brain() -> Dict[str, Any]:
    """Backward compatible: run daily calibration."""
    return get_brain().calibrate()


# ── New V6 module-level functions ─────────────────────────────────────────────

def get_adaptive_score(
    components: Dict[str, Any],
    regime: str = "NEUTRAL",
    signal: str = "",
    symbol: str = "",
    hour: Optional[int] = None,
) -> Dict[str, Any]:
    """V6: Hitung Adaptive Score lengkap dengan penalty/reward/explanations."""
    return get_brain().get_adaptive_score(components, regime, signal, symbol, hour)


def get_recommendation(
    score: float,
    market_context: Dict[str, Any],
    symbol: str = "",
    signal: str = "",
) -> Dict[str, Any]:
    """V6: ALLOW / CAUTION / SKIP recommendation."""
    return get_brain().get_recommendation(score, market_context, symbol, signal)


def get_market_health(context: Dict[str, Any]) -> Dict[str, Any]:
    """V6: Market Health Score 0-100."""
    return get_brain().get_market_health(context)


def get_ai_memory() -> Dict[str, Any]:
    """V6: AI Memory — best/worst pairs, sessions, setups."""
    return get_brain().get_ai_memory()


def get_performance_stats(days: int = 30) -> Dict[str, Any]:
    """V6: Full Performance Database stats."""
    return get_brain().get_performance_stats(days)


def record_trade_result(trade_data: Dict[str, Any]) -> None:
    """V6: Record trade result untuk self-learning."""
    get_brain().record_trade_result(trade_data)


def get_confidence_level(confidence: float) -> str:
    """V6: Konversi confidence float → Very Low/Low/Medium/High/Very High."""
    return get_brain().get_confidence_level(confidence)


# ── adaptive_weights.py BACKWARD COMPATIBILITY ───────────────────────────────
# Semua fungsi dari adaptive_weights.py tetap tersedia di sini

WEIGHT_PROFILES = {
    "TRENDING": {
        "trend_strength": 0.40, "breakout": 0.25,
        "volume": 0.15, "momentum": 0.10, "volatility": 0.10,
    },
    "RANGING": {
        "support_resistance": 0.40, "rsi": 0.20,
        "rejection_candle": 0.20, "volume": 0.20,
    },
    "VOLATILE": {
        "trend_strength": 0.20, "volume": 0.20, "momentum": 0.20,
        "support_resistance": 0.20, "volatility": 0.20,
    },
    "NEUTRAL": {
        "trend_strength": 0.25, "support_resistance": 0.25,
        "momentum": 0.20, "volume": 0.15, "volatility": 0.15,
    },
}

VOLATILE_RULES = {
    "min_confidence":     70,
    "position_size_mult": 0.5,
    "sl_mult":            1.5,
    "tp_mult":            1.2,
    "skip_if_below":      65,
}

CONFIDENCE_THRESHOLD = {
    "TRENDING": 50,
    "RANGING":  48,
    "VOLATILE": 65,
    "NEUTRAL":  48,
}


def get_weight_profile(regime: str) -> dict:
    """Backward compatible: return weight profile per regime."""
    return WEIGHT_PROFILES.get(regime, WEIGHT_PROFILES["NEUTRAL"])


def compute_adaptive_score(components: dict, regime: str) -> tuple:
    """
    Backward compatible dengan adaptive_weights.py.
    Returns (score, breakdown, reason).
    """
    weights  = get_weight_profile(regime)
    score    = 0.0
    breakdown = {}
    missing  = []

    for key, weight in weights.items():
        val = components.get(key)
        if val is None:
            missing.append(key)
            val = 0.0
        contribution = round(float(val) * weight, 2)
        breakdown[key] = {
            "value": round(float(val), 1),
            "weight": weight,
            "contribution": contribution,
        }
        score += contribution

    score  = round(min(100.0, max(0.0, score)), 1)
    reason = f"Regime={regime}"
    if missing:
        reason += f" | Missing: {', '.join(missing)}"
    return score, breakdown, reason


def compute_confidence(
    regime: str,
    trend_score: float,
    volume_score: float,
    volatility: float,
    sr_score: float,
    liquidity: float,
    smc_score: float = 0.0,
) -> tuple:
    """Backward compatible dengan adaptive_weights.py compute_confidence."""
    weights_map = {
        "TRENDING": {"trend": 0.35, "volume": 0.25, "sr": 0.15,
                     "volatility": 0.10, "liquidity": 0.10, "smc": 0.05},
        "RANGING":  {"sr": 0.35, "volume": 0.20, "trend": 0.15,
                     "volatility": 0.10, "liquidity": 0.10, "smc": 0.10},
        "VOLATILE": {"volatility": 0.30, "volume": 0.25, "trend": 0.20,
                     "sr": 0.15, "liquidity": 0.05, "smc": 0.05},
        "NEUTRAL":  {"trend": 0.25, "sr": 0.25, "volume": 0.20,
                     "volatility": 0.15, "liquidity": 0.10, "smc": 0.05},
    }
    w = weights_map.get(regime, weights_map["NEUTRAL"])
    confidence = (
        trend_score  * w["trend"]      +
        volume_score * w["volume"]     +
        sr_score     * w["sr"]         +
        volatility   * w["volatility"] +
        liquidity    * w["liquidity"]  +
        smc_score    * w["smc"]
    )
    confidence = round(min(100.0, max(0.0, confidence)), 1)
    reasons = []
    if trend_score  < 40: reasons.append("trend lemah")
    if volume_score < 40: reasons.append("volume rendah")
    if volatility   > 80: reasons.append("volatilitas tinggi")
    if sr_score     < 30: reasons.append("SR tidak jelas")
    if liquidity    < 30: reasons.append("likuiditas rendah")
    reason = f"Confidence={confidence}"
    if reasons:
        reason += f" | Peringatan: {', '.join(reasons)}"
    return confidence, reason


def should_skip_volatile(confidence: float) -> bool:
    """Backward compatible: skip volatile jika confidence < threshold."""
    return confidence < VOLATILE_RULES["skip_if_below"]


def get_position_size_multiplier(regime: str, confidence: float) -> float:
    """Backward compatible: position size multiplier."""
    if regime == "VOLATILE":
        return VOLATILE_RULES["position_size_mult"]
    if confidence >= 80:
        return 1.0
    if confidence >= 65:
        return 0.75
    return 0.5


def get_sl_tp_multiplier(regime: str) -> tuple:
    """Backward compatible: (sl_mult, tp_mult)."""
    if regime == "VOLATILE":
        return VOLATILE_RULES["sl_mult"], VOLATILE_RULES["tp_mult"]
    if regime == "TRENDING":
        return 1.2, 1.3
    if regime == "RANGING":
        return 0.8, 0.9
    return 1.0, 1.0


def extract_components_from_last(last: dict, df=None) -> dict:
    """Backward compatible: ekstrak komponen dari row indikator terakhir."""
    def sf(v, default=0.0):
        try:
            val = float(v)
            return default if (val != val or abs(val) == float('inf')) else val
        except:
            return default

    rsi      = sf(last.get("rsi", 50))
    adx      = sf(last.get("adx", 0))
    vol_r    = sf(last.get("vol_ratio", 1))
    macd_h   = sf(last.get("macd_hist", 0))
    bb_pct   = sf(last.get("bb_pct", 0.5))
    sr_pos   = sf(last.get("sr_pos", 0.5))
    atr      = sf(last.get("atr", 0))
    close    = sf(last.get("close", 1), 1)
    obv_bull = bool(last.get("obv_bull", False))
    trend_up = bool(last.get("trend_up", False))
    trend_dn = bool(last.get("trend_down", False))
    squeeze  = sf(last.get("squeeze_score", 0))

    trend_strength = min(100, adx * 2.5)
    if trend_up or trend_dn:
        trend_strength = min(100, trend_strength * 1.2)

    breakout = 0.0
    if sf(last.get("broke_resistance", 0)):
        breakout = min(100, 60 + vol_r * 20)
    elif squeeze > 70:
        breakout = squeeze * 0.8

    volume   = min(100, vol_r * 50)

    close_safe  = max(close, 1e-9)
    macd_norm   = min(100, max(0, (macd_h / (close_safe * 0.01 + 1e-9)) * 50 + 50))
    rsi_mom     = abs(rsi - 50) * 2
    momentum    = round(macd_norm * 0.6 + rsi_mom * 0.4, 1)

    atr_pct     = (atr / close_safe * 100) if close_safe > 0 else 0
    volatility  = min(100, atr_pct * 20)

    sr_quality  = round(abs(sr_pos - 0.5) * 200, 1)
    rsi_score   = round(abs(rsi - 50) * 2, 1)

    hammer  = bool(last.get("hammer", 0))
    engulf  = bool(last.get("bull_engulf", 0)) or bool(last.get("bear_engulf", 0))
    doji    = bool(last.get("doji", 0))
    rejection = 100 if engulf else (80 if hammer else (50 if doji else 0))

    return {
        "trend_strength":     round(trend_strength, 1),
        "breakout":           round(breakout, 1),
        "volume":             round(volume, 1),
        "momentum":           round(momentum, 1),
        "volatility":         round(volatility, 1),
        "support_resistance": round(sr_quality, 1),
        "rsi":                round(rsi_score, 1),
        "rejection_candle":   float(rejection),
        # V6 extras
        "adx":                round(adx, 2),
        "vol_ratio":          round(vol_r, 3),
        "macd_hist":          round(macd_h, 6),
        "rsi_raw":            round(rsi, 2),
        "close":              round(close, 6),
        "sr_pos":             round(sr_pos, 3),
        "atr":                round(atr, 6),
        "obv_bull":           obv_bull,
        "trend_up":           trend_up,
        "trend_down":         trend_dn,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    brain = get_brain()
    print(f"\n{'='*60}")
    print(f"  Adaptive Brain V6 — {VERSION}")
    print(f"{'='*60}")

    # Test adaptive score
    test_components = {
        "adx": 42, "rsi": 62, "vol_ratio": 2.1, "macd_hist": 0.0015,
        "close": 100.0, "atr": 1.5, "trend_up": True, "ema_aligned": True,
        "obv_bull": True, "sr_pos": 0.4, "btc_aligned": 1,
        "order_block_score": 75, "fvg_score": 60, "liquidity_sweep_score": 50,
        "institutional_score": 65, "liquidity_sweep": True,
        "order_block_valid": True, "fvg_valid": True,
        "confidence_raw": 70,
    }

    result = get_adaptive_score(test_components, regime="TRENDING",
                                signal="BUY (SETUP)", symbol="BTCUSDT")
    print(f"\n📊 Adaptive Score:")
    print(f"   Raw    : {result['score_raw']}")
    print(f"   Final  : {result['score_final']}")
    print(f"   Penalty: {result['penalty_total']}")
    print(f"   Reward : {result['reward_total']}")
    print(f"   Conf   : {result['confidence']} ({result['confidence_level']})")
    print(f"   Session: {result['session']}")
    print(f"\n📝 Explanations:")
    for e in result["explanations"]:
        print(f"   {e}")

    # Test recommendation
    rec = get_recommendation(result["score_final"], {"regime": "TRENDING"},
                              symbol="BTCUSDT", signal="BUY (SETUP)")
    print(f"\n🤖 Recommendation: {rec['recommendation']}")
    for r in rec["reasons"]:
        print(f"   → {r}")

    # Test market health
    health = get_market_health({
        "adx": 38, "vol_ratio": 1.8, "atr_ratio": 1.1,
        "btc_strength": 65, "funding_rate": 0.0001, "oi_change_pct": 3.2,
    })
    print(f"\n💚 Market Health: {health['health_score']} ({health['label']})")

    # Performance stats
    stats = get_performance_stats(30)
    print(f"\n📈 Performance (30d):")
    print(f"   Trades     : {stats.get('total_trades', 0)}")
    print(f"   Win Rate   : {stats.get('win_rate', 0):.1f}%")
    print(f"   Prof Factor: {stats.get('profit_factor', 0):.2f}")
    print(f"   Expectancy : {stats.get('expectancy', 0):.4f}")

    print(f"\n✅ Adaptive Brain V6 siap digunakan!")
