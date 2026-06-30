#!/usr/bin/env python3
"""
Adaptive Brain V6 – AI Decision Engine for Crypto Trading Scanner.
Replaces static thresholds with self‑learning, context‑aware logic.
Compatible with config.py, market_context.py, risk_manager.py, scanner.py.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    from config import BASE_DIR  # optional, fallback to local dir
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("adaptive_brain_v6")


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class IndicatorWeight:
    name: str
    weight: float
    hits: int = 0
    misses: int = 0
    last_updated: Optional[datetime] = None


@dataclass
class BrainState:
    """Persistent state of the adaptive brain."""
    indicator_weights: Dict[str, IndicatorWeight] = field(default_factory=dict)
    decision_count: int = 0
    last_calibration: Optional[datetime] = None
    trade_memory: List[Dict[str, Any]] = field(default_factory=list)
    version: str = "6.0.0"


# ---------------------------------------------------------------------------
# Performance Memory (SQLite)
# ---------------------------------------------------------------------------

class PerformanceMemory:
    """SQLite-backed store for historical trades and indicator performance."""

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
        with self._lock:
            c = self.conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    confidence REAL,
                    regime TEXT,
                    indicators TEXT,
                    profit REAL,
                    loss REAL,
                    timestamp TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS indicator_weights (
                    name TEXT PRIMARY KEY,
                    weight REAL NOT NULL,
                    hits INTEGER DEFAULT 0,
                    misses INTEGER DEFAULT 0,
                    last_updated TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    context TEXT,
                    threshold REAL,
                    risk REAL,
                    max_positions INTEGER,
                    reasoning TEXT
                )
            """)
            self.conn.commit()

    def save_trade(self, trade: Dict[str, Any]) -> None:
        with self._lock:
            c = self.conn.cursor()
            c.execute(
                """INSERT INTO trades
                   (symbol, signal, confidence, regime, indicators, profit, loss, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.get("symbol"),
                    trade.get("signal"),
                    trade.get("confidence"),
                    trade.get("regime"),
                    json.dumps(trade.get("indicators", {})),
                    trade.get("profit", 0.0),
                    trade.get("loss", 0.0),
                    trade.get("timestamp", datetime.now(timezone.utc).isoformat()),
                ),
            )
            self.conn.commit()

    def save_indicator_weights(self, weights: Dict[str, IndicatorWeight]) -> None:
        with self._lock:
            c = self.conn.cursor()
            for name, iw in weights.items():
                c.execute(
                    """INSERT OR REPLACE INTO indicator_weights
                       (name, weight, hits, misses, last_updated)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        name,
                        iw.weight,
                        iw.hits,
                        iw.misses,
                        iw.last_updated.isoformat() if iw.last_updated else None,
                    ),
                )
            self.conn.commit()

    def load_indicator_weights(self) -> Dict[str, IndicatorWeight]:
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
                        if row["last_updated"]
                        else None
                    ),
                )
                weights[row["name"]] = iw
            return weights

    def load_recent_trades(self, days: int = 30) -> List[Dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute(
                "SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp DESC",
                (cutoff,),
            )
            return [dict(row) for row in c.fetchall()]

    def prune_old_data(self, days: int = 90) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            c = self.conn.cursor()
            c.execute("DELETE FROM trades WHERE timestamp < ?", (cutoff,))
            deleted = c.rowcount
            self.conn.commit()
            return deleted


# ---------------------------------------------------------------------------
# Decision Logger
# ---------------------------------------------------------------------------

class DecisionLogger:
    """Writes every AI decision into a dedicated log file."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._lock = threading.Lock()

    def log_decision(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            except Exception as exc:
                logger.warning(f"DecisionLogger write failed: {exc}")


# ---------------------------------------------------------------------------
# Main Engine
# ---------------------------------------------------------------------------

class AdaptiveBrainV6:
    """Central AI brain that adapts thresholds, risk, and indicator weights."""

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        if state_dir is None:
            state_dir = Path(__file__).resolve().parent
        self.state_dir = state_dir
        self.memory = PerformanceMemory(state_dir / "brain_memory.db")
        self.decision_log = DecisionLogger(state_dir / "brain_decisions.log")
        self.state = BrainState()
        self._load_state()
        self.lock = threading.RLock()

    # -----------------------------------------------------------------------
    # State Persistence
    # -----------------------------------------------------------------------
    def _state_file(self) -> Path:
        return self.state_dir / "brain_state.json"

    def _load_state(self) -> None:
        sf = self._state_file()
        if sf.exists():
            try:
                with open(sf, "r") as f:
                    data = json.load(f)
                self.state.decision_count = data.get("decision_count", 0)
                self.state.version = data.get("version", "6.0.0")
                lc = data.get("last_calibration")
                self.state.last_calibration = (
                    datetime.fromisoformat(lc) if lc else None
                )
            except Exception as e:
                logger.warning(f"Failed to load brain state: {e}")
        # Load indicator weights from SQLite (more reliable)
        db_weights = self.memory.load_indicator_weights()
        if db_weights:
            self.state.indicator_weights = db_weights
        else:
            self._init_default_weights()

    def _save_state(self) -> None:
        with open(self._state_file(), "w") as f:
            json.dump(
                {
                    "decision_count": self.state.decision_count,
                    "last_calibration": (
                        self.state.last_calibration.isoformat()
                        if self.state.last_calibration
                        else None
                    ),
                    "version": self.state.version,
                },
                f,
                indent=2,
                default=str,
            )
        self.memory.save_indicator_weights(self.state.indicator_weights)

    def _init_default_weights(self) -> None:
        defaults = {
            "ema": 0.5, "rsi": 0.4, "macd": 0.5, "vwap": 0.3,
            "order_block": 0.2, "fvg": 0.2, "liquidity_sweep": 0.25,
            "breakout": 0.3, "bos": 0.2, "choch": 0.2, "volume_spike": 0.35,
            "atr": 0.3, "adx": 0.35, "supertrend": 0.3,
        }
        for name, w in defaults.items():
            self.state.indicator_weights[name] = IndicatorWeight(
                name=name, weight=w, last_updated=datetime.now(timezone.utc)
            )

    # -----------------------------------------------------------------------
    # 1. Adaptive Threshold
    # -----------------------------------------------------------------------
    def get_threshold(self, market_context: Dict[str, Any]) -> float:
        fg = market_context.get("fear_greed", 50)
        btc_trend = market_context.get("btc_trend", "NEUTRAL")
        regime = market_context.get("regime", "NEUTRAL")
        atr_ratio = market_context.get("atr_ratio", 1.0)
        volatility = market_context.get("volatility", "medium")
        liquidity = market_context.get("liquidity", "medium")
        vol_spike = market_context.get("volume_spike", False)

        threshold = 50.0

        # Fear & Greed
        if isinstance(fg, dict): fg = fg.get('value', 0)
        if fg <= 20:
            threshold -= 12
        elif fg <= 40:
            threshold -= 6
        elif fg >= 80:
            threshold += 5

        # BTC Trend
        btc_up = "UP" in (str(btc_trend.get("trend","") if isinstance(btc_trend, dict) else btc_trend).upper())
        btc_down = "DOWN" in (str(btc_trend.get("trend","") if isinstance(btc_trend, dict) else btc_trend).upper())
        if btc_up:
            threshold -= 3
        elif btc_down:
            threshold -= 8

        # Regime
        regime_map = {"TRENDING": -5, "BREAKOUT": -3, "RANGING": +5, "VOLATILE": +10}
        threshold += regime_map.get((str(regime.get("trend","") if isinstance(regime, dict) else regime).upper()), 0)

        # ATR ratio (wider ATR => higher uncertainty)
        if atr_ratio > 1.5:
            threshold += 5
        elif atr_ratio < 0.7:
            threshold -= 3

        # Volatility
        vol_map = {"low": -3, "medium": 0, "high": 8}
        threshold += vol_map.get(volatility, 0)

        # Liquidity
        liq_map = {"low": 5, "medium": 0, "high": -2}
        threshold += liq_map.get(liquidity, 0)

        # Volume spike => lower threshold (higher conviction signals)
        if vol_spike:
            threshold -= 4

        return max(25.0, min(70.0, threshold))

    # -----------------------------------------------------------------------
    # 2. Confidence Engine
    # -----------------------------------------------------------------------
    def get_confidence(
        self, indicators: Dict[str, Any], market_context: Dict[str, Any]
    ) -> float:
        score = 0.0
        total_weight = 0.0

        for ind_name, value in indicators.items():
            iw = self.state.indicator_weights.get(ind_name)
            if iw is None:
                continue
            w = iw.weight
            # Normalise indicator value between 0 and 1 (if not already)
            norm = self._normalise_indicator(ind_name, value)
            score += norm * w
            total_weight += w

        if total_weight > 0:
            score /= total_weight

        # Modulate by market context
        fg = market_context.get("fear_greed", 50)
        regime = market_context.get("regime", "NEUTRAL")
        btc_trend = market_context.get("btc_trend", "NEUTRAL")

        # Fear = slightly lower confidence
        if isinstance(fg, dict): fg = fg.get('value', 0)
        if fg <= 20:
            score *= 0.85
        elif fg <= 40:
            score *= 0.92

        # Volatile regime = lower confidence
        if (str(regime.get("trend","") if isinstance(regime, dict) else regime).upper()) == "VOLATILE":
            score *= 0.8

        # Strong BTC trend can boost confidence for aligned signals
        # (caller can override, here we just neutral)
        return max(0.0, min(100.0, score * 100.0))

    def _normalise_indicator(self, name: str, value: float) -> float:
        """Convert raw indicator value to 0..1 where 1 = bullish / strong signal."""
        if name in {"rsi"}:
            # 50 = 0.5, 0 = 0, 100 = 1
            return max(0.0, min(1.0, value / 100.0))
        if name in {"macd", "macd_hist"}:
            return 1.0 / (1.0 + np.exp(-value / 0.01))  # sigmoid
        if name in {"volume_spike"}:
            return 0.8 if value else 0.2
        if name in {"adx"}:
            return min(1.0, value / 50.0)
        if name in {"atr"}:
            # ATR relative to price – assume value is ratio
            return 0.5 if 0.7 <= value <= 1.3 else (0.2 if value > 1.5 else 0.8)
        # fallback: assume value is already 0..1
        return max(0.0, min(1.0, float(value)))

    # -----------------------------------------------------------------------
    # 3. Adaptive Risk Engine
    # -----------------------------------------------------------------------
    def get_risk(self, risk_status: Dict[str, Any]) -> Dict[str, Any]:
        drawdown = risk_status.get("drawdown_pct", 0)
        streak_loss = risk_status.get("consecutive_loss", 0)
        streak_win = risk_status.get("consecutive_win", 0)
        heat = risk_status.get("portfolio_heat", 0)
        win_rate = risk_status.get("win_rate", 50)

        # Base risk
        risk = 2.0
        if drawdown > 10 or streak_loss >= 5:
            risk = 0.5
        elif drawdown > 5 or streak_loss >= 3:
            risk = 1.0
        elif win_rate > 60 and drawdown < 3:
            risk = 2.5
        elif streak_win >= 3:
            risk = 2.2

        # Max positions
        max_pos = 5
        if heat > 10:
            max_pos = 2
        elif heat > 7:
            max_pos = 3
        elif heat > 5:
            max_pos = 4
        if drawdown > 10:
            max_pos = min(max_pos, 2)
        if streak_loss >= 3:
            max_pos = min(max_pos, 3)

        # Cooldown (minutes)
        cooldown = 45
        if streak_loss >= 3:
            cooldown += 30
        if drawdown > 5:
            cooldown += 15

        # Stop multiplier (wider stop in high vol)
        stop_mult = 1.0
        if drawdown > 5:
            stop_mult = 0.8  # tighter stops when losing
        elif win_rate > 55:
            stop_mult = 1.2  # allow more room when winning

        # TP multiplier
        tp_mult = 1.0
        if streak_loss >= 3:
            tp_mult = 0.8  # take profit earlier
        elif win_rate > 60:
            tp_mult = 1.3

        return {
            "risk_per_trade": risk,
            "max_positions": max_pos,
            "cooldown_minutes": cooldown,
            "stop_multiplier": stop_mult,
            "tp_multiplier": tp_mult,
        }

    # -----------------------------------------------------------------------
    # 4. Position Engine
    # -----------------------------------------------------------------------
    def get_position_advice(
        self, risk_status: Dict[str, Any], risk_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Returns position size, exposure and multiplier based on risk appetite."""
        heat = risk_status.get("portfolio_heat", 0)
        balance = risk_status.get("balance", 100.0)
        risk_per_trade = risk_params["risk_per_trade"]
        max_pos = risk_params["max_positions"]
        open_pos = risk_status.get("open_positions", 0)

        can_open = min(max_pos - open_pos, max_pos)
        if can_open < 0:
            can_open = 0

        position_risk_pct = risk_per_trade / max(1, max_pos)
        position_size = balance * position_risk_pct / 100.0

        return {
            "can_open": can_open,
            "position_risk_pct": round(position_risk_pct, 2),
            "position_size": round(position_size, 2),
            "total_exposure_pct": round(position_risk_pct * can_open, 2),
        }

    # -----------------------------------------------------------------------
    # 5. Indicator Learning
    # -----------------------------------------------------------------------
    def update_trade_result(
        self,
        indicators: Dict[str, float],
        profit: float,
        loss: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Learn from a completed trade: update indicator weights."""
        success = profit > 0
        for name, value in indicators.items():
            iw = self.state.indicator_weights.get(name)
            if iw is None:
                iw = IndicatorWeight(name=name, weight=0.3)
                self.state.indicator_weights[name] = iw

            # Weight update rule: reinforce if indicator was "correct"
            # Here correctness is proxied by trade success.
            iw.hits += 1 if success else 0
            iw.misses += 0 if success else 1

            total = iw.hits + iw.misses
            if total > 0:
                hit_rate = iw.hits / total
                # Weight moves towards hit_rate * 2 (scaled between 0.1 and 0.9)
                target = max(0.1, min(0.9, hit_rate * 2))
                iw.weight = iw.weight * 0.7 + target * 0.3

            iw.last_updated = datetime.now(timezone.utc)

        # Save trade to memory
        trade_record = {
            "symbol": context.get("symbol", "unknown") if context else "unknown",
            "signal": context.get("signal", "unknown") if context else "unknown",
            "confidence": context.get("confidence", 0) if context else 0,
            "regime": context.get("regime", "unknown") if context else "unknown",
            "indicators": indicators,
            "profit": profit,
            "loss": loss,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.memory.save_trade(trade_record)
        self._save_state()

    # -----------------------------------------------------------------------
    # 6. Self Calibration
    # -----------------------------------------------------------------------
    def calibrate(self) -> Dict[str, Any]:
        """Run daily calibration: normalise weights, prune memory, log stats."""
        now = datetime.now(timezone.utc)
        if (
            self.state.last_calibration
            and (now - self.state.last_calibration) < timedelta(hours=23)
        ):
            logger.debug("Calibration skipped – already calibrated within 24h")
            return {"status": "skipped", "reason": "too_soon"}

        # Prune old trades (keep 90 days)
        deleted = self.memory.prune_old_data(90)

        # Normalise indicator weights (sum not required, but keep between 0.1 and 0.9)
        for iw in self.state.indicator_weights.values():
            iw.weight = max(0.1, min(0.9, iw.weight))

        # Recalculate statistics
        trades = self.memory.load_recent_trades(30)
        wins = sum(1 for t in trades if t["profit"] > 0)
        total = len(trades)
        win_rate = wins / max(1, total) * 100

        stats = {
            "status": "calibrated",
            "deleted_records": deleted,
            "active_weights": len(self.state.indicator_weights),
            "recent_trades_30d": total,
            "win_rate_30d": round(win_rate, 2),
            "last_calibration": now.isoformat(),
        }

        self.state.last_calibration = now
        self._save_state()
        self.decision_log.log_decision(
            {"event": "calibration", **stats}
        )
        logger.info(
            "Brain calibrated: %d trades pruned, win_rate %.1f%%",
            deleted,
            win_rate,
        )
        return stats

    # -----------------------------------------------------------------------
    # 7. Learning (orchestrator)
    # -----------------------------------------------------------------------
    def learn(self) -> Dict[str, Any]:
        """Placeholder for additional ML logic (feature importance, regime clustering, etc)."""
        # For now, just trigger calibration if needed.
        return self.calibrate()

    # -----------------------------------------------------------------------
    # 8. Persistence Helpers
    # -----------------------------------------------------------------------
    def save(self) -> None:
        self._save_state()
        logger.debug("Brain state saved.")

    def load(self) -> None:
        self._load_state()
        logger.debug("Brain state loaded.")

    # -----------------------------------------------------------------------
    # 9. Get Full Brain Snapshot
    # -----------------------------------------------------------------------
    def get_brain(self) -> Dict[str, Any]:
        return {
            "version": self.state.version,
            "decision_count": self.state.decision_count,
            "last_calibration": (
                self.state.last_calibration.isoformat()
                if self.state.last_calibration
                else None
            ),
            "indicator_count": len(self.state.indicator_weights),
            "weights": {
                name: {
                    "weight": iw.weight,
                    "hits": iw.hits,
                    "misses": iw.misses,
                }
                for name, iw in self.state.indicator_weights.items()
            },
        }


# ---------------------------------------------------------------------------
# Singleton & Convenience Functions
# ---------------------------------------------------------------------------

_brain_instance: Optional[AdaptiveBrainV6] = None
_brain_lock = threading.Lock()


def get_brain() -> AdaptiveBrainV6:
    global _brain_instance
    with _brain_lock:
        if _brain_instance is None:
            _brain_instance = AdaptiveBrainV6()
        return _brain_instance


def get_threshold(market_context: Dict[str, Any]) -> float:
    return get_brain().get_threshold(market_context)


def get_confidence(
    indicators: Dict[str, Any], market_context: Dict[str, Any]
) -> float:
    return get_brain().get_confidence(indicators, market_context)


def get_risk(risk_status: Dict[str, Any]) -> Dict[str, Any]:
    return get_brain().get_risk(risk_status)


def update_trade_result(
    indicators: Dict[str, float],
    profit: float,
    loss: float,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    get_brain().update_trade_result(indicators, profit, loss, context)


def learn() -> Dict[str, Any]:
    return get_brain().learn()


def calibrate() -> Dict[str, Any]:
    return get_brain().calibrate()


def save() -> None:
    get_brain().save()


def load() -> None:
    get_brain().load()
