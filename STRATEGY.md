# Strategi Trading Bot — S/R-Only Mode

**Terakhir diupdate:** 09-10 Juli 2026

## Ringkasan
Bot ini menggunakan sinyal berbasis **Support/Resistance + Volume + Candlestick Pattern**.
RSI, MACD, dan EMA **tidak lagi dipakai** sebagai trigger sinyal (per 9 Juli 2026).

## Riwayat Perubahan
1. **9 Juli 2026** — Nonaktifkan sinyal `BUY`/`SELL` polos. Data historis
   (`virtual_trading.db`, 210 trades) menunjukkan WR 23-30%, PnL -$25.93.
   Kategori `SETUP`/`REVERSAL` jauh lebih baik (WR 46-56%, PnL +$6.03).
2. **9 Juli 2026** — Fix bug urutan `data.loc[...]` di `indicators.py`: sinyal
   SETUP yang valid sempat tertimpa BUY/SELL polos yang sudah dinonaktifkan.
3. **9 Juli 2026** — Ganti total ke strategi S/R-only (menggantikan semua
   kondisi lama: SETUP, MOMENTUM, BREAKOUT, CONFIRM, REVERSAL berbasis trend).
4. **9 Juli 2026** — Blacklist SOLUSDT & LTCUSDT 30 hari (konsisten rugi
   di backtest 90 hari).

## Jenis Sinyal Aktif

| Sinyal | Kondisi | Konfirmasi |
|---|---|---|
| `BUY (SR BOUNCE)` | Harga dekat support | Candle bullish reversal + rvol > 0.8 + bukan fake breakdown |
| `SELL (SR BOUNCE)` | Harga dekat resistance | Candle bearish reversal + rvol > 0.8 + bukan fake breakout |
| `BUY (SR BREAKOUT)` | Breakout resistance | rvol > 1.3 + bukan fake breakout + candle konfirmasi |
| `SELL (SR BREAKDOWN)` | Breakdown support | rvol > 1.3 + bukan fake breakdown + candle konfirmasi |

## Hasil Backtest (90 hari, 9 pair, sebelum live)
- Total trades: 156
- Overall Win Rate: 40.4%
- Total PnL: +36.26%
- Pairs profitable: 7/9 (BTC, ETH, XRP, ADA, AVAX, BCH, BNB)
- Pairs rugi: SOL (-13.64%), LTC (-5.66%) → keduanya diblacklist

## Pair Terbaik (dari backtest)
1. AVAXUSDT — WR 61.1%, PnL +19.66%
2. XRPUSDT — WR 50.0%, PnL +5.18%
3. BTCUSDT — WR 45.5%, PnL +8.07%

## Command Telegram Terkait
- /analyze <PAIR> atau /cek <PAIR> — analisa on-demand 1 pair
- /setup_stats atau /sr_stats — ringkasan performa live sejak 9 Juli 2026
- /status — status risk management umum
- /scan — trigger scan manual

## Catatan Penting untuk Evaluasi Berikutnya
- Backtest 90 hari cukup untuk validasi awal, tapi tetap pantau performa
  LIVE minimal 2-4 minggu sebelum menyimpulkan strategi ini "terbukti".
- Jangan ubah threshold berdasarkan sample < 30 trade.
- File terkait: indicators.py, scanner.py (VALID_SIGNALS), backtester.py (VALID_SIGNALS, MIN_CONF).
