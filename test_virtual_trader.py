"""
test_virtual_trader.py — Test suite untuk fungsi kritis di virtual_trader.py

Cara jalankan: python3 test_virtual_trader.py
Semua test pakai database SEMENTARA (temp file), TIDAK PERNAH menyentuh
virtual_trading.db yang asli. Aman dijalankan kapan saja, termasuk saat
bot production sedang jalan.
"""
import unittest
import sqlite3
import tempfile
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import virtual_trader


# Skema PERSIS sama seperti virtual_trading.db production (termasuk kolom
# yang ditambahkan lewat ALTER TABLE, bukan cuma dari init_virtual_db()).
SCHEMA = """
CREATE TABLE virtual_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    symbol TEXT,
    signal TEXT,
    entry REAL,
    sl REAL,
    tp1 REAL,
    tp2 REAL,
    tp3 REAL,
    exit_price REAL,
    pnl_pct REAL,
    pnl_usd REAL,
    result TEXT,
    balance_after REAL,
    timeframe TEXT,
    closed INTEGER DEFAULT 0,
    exit REAL DEFAULT 0,
    pnl_usdt REAL DEFAULT 0,
    closed_at TEXT
);
CREATE TABLE virtual_trade_partials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    tp_level TEXT,
    exit_price REAL,
    pct_closed REAL,
    pnl_pct REAL,
    pnl_usdt REAL,
    closed_at TEXT
);
"""


class TestIsDuplicatePosition(unittest.TestCase):
    """Test untuk is_duplicate_position() -- fungsi ini yang kena bug
    2026-08-26: dulu cek exact match symbol+timeframe+signal, sehingga
    BUY dan SELL di pair+timeframe yang sama dianggap 'tidak duplicate'
    dan bisa terbuka bersamaan (saling bertentangan)."""

    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmpfile.close()
        conn = sqlite3.connect(self.tmpfile.name)
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()
        # Monkey-patch VIRTUAL_DB supaya fungsi baca dari temp db, bukan
        # database production.
        self._original_db = virtual_trader.VIRTUAL_DB
        virtual_trader.VIRTUAL_DB = self.tmpfile.name

    def tearDown(self):
        virtual_trader.VIRTUAL_DB = self._original_db
        os.unlink(self.tmpfile.name)

    def _insert_trade(self, symbol, timeframe, signal, closed=0):
        conn = sqlite3.connect(self.tmpfile.name)
        conn.execute(
            "INSERT INTO virtual_trades (symbol, timeframe, signal, entry, closed) "
            "VALUES (?, ?, ?, 100.0, ?)",
            (symbol, timeframe, signal, closed)
        )
        conn.commit()
        conn.close()

    def test_no_position_returns_false(self):
        """Tidak ada posisi sama sekali -> bukan duplicate."""
        result = virtual_trader.is_duplicate_position("BTCUSDT", "1h", "BUY (SR BOUNCE)")
        self.assertFalse(result)

    def test_exact_same_signal_is_duplicate(self):
        """Posisi identik (symbol+timeframe+signal sama) -> duplicate."""
        self._insert_trade("BTCUSDT", "1h", "BUY (SR BOUNCE)", closed=0)
        result = virtual_trader.is_duplicate_position("BTCUSDT", "1h", "BUY (SR BOUNCE)")
        self.assertTrue(result)

    def test_opposite_direction_same_pair_timeframe_is_duplicate(self):
        """[REGRESI BUG 2026-08-26] BUY sudah terbuka, sinyal SELL masuk
        untuk pair+timeframe yang sama -> HARUS dianggap duplicate (dulu
        ini yang gagal, menyebabkan AMZNGUSDT punya posisi BUY dan SELL
        bersamaan)."""
        self._insert_trade("AMZNGUSDT", "1h", "BUY (SR BOUNCE)", closed=0)
        result = virtual_trader.is_duplicate_position("AMZNGUSDT", "1h", "SELL (SR BOUNCE)")
        self.assertTrue(result, "BUG REGRESI: posisi berlawanan arah di pair+timeframe sama lolos sebagai bukan duplicate!")

    def test_different_strategy_same_pair_timeframe_is_duplicate(self):
        """BOUNCE sudah terbuka, sinyal BREAKOUT masuk untuk pair+timeframe
        sama -> tetap dianggap duplicate (1 pair+timeframe = 1 posisi)."""
        self._insert_trade("ETHUSDT", "4h", "BUY (SR BOUNCE)", closed=0)
        result = virtual_trader.is_duplicate_position("ETHUSDT", "4h", "BUY (SR BREAKOUT)")
        self.assertTrue(result)

    def test_different_timeframe_same_pair_not_duplicate(self):
        """Timeframe beda dianggap posisi independen -- 1h dan 4h boleh
        jalan bersamaan untuk pair yang sama."""
        self._insert_trade("XAUTUSDT", "1h", "SELL (SR BOUNCE)", closed=0)
        result = virtual_trader.is_duplicate_position("XAUTUSDT", "4h", "SELL (SR BOUNCE)")
        self.assertFalse(result)

    def test_closed_position_not_duplicate(self):
        """Posisi yang sudah closed=1 tidak menghalangi posisi baru."""
        self._insert_trade("SOLUSDT", "1h", "BUY (SR BOUNCE)", closed=1)
        result = virtual_trader.is_duplicate_position("SOLUSDT", "1h", "SELL (SR BOUNCE)")
        self.assertFalse(result)

    def test_different_symbol_not_duplicate(self):
        """Symbol beda tidak saling mempengaruhi."""
        self._insert_trade("BTCUSDT", "1h", "BUY (SR BOUNCE)", closed=0)
        result = virtual_trader.is_duplicate_position("ETHUSDT", "1h", "BUY (SR BOUNCE)")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
