

# ═══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL AI V7 — Multi-Timeframe Confluence + Orderflow Proxy
# ═══════════════════════════════════════════════════════════════════════════════
#
# V7 dibangun DI ATAS v4 (reuse semua logic v4 yang sudah teruji), menambahkan:
#   1. Multi-timeframe confluence (4h confirmation jika df_htf disediakan)
#   2. VWAP deviation — jarak harga dari fair value institusional
#   3. CVD proxy (Cumulative Volume Delta dari OHLCV, tanpa perlu data tick)
#   4. Absorption / Iceberg detection — volume besar, pergerakan kecil
#   5. Confidence band — label keyakinan statistik berdasar jumlah konfirmasi
#   6. institutional_score_v7 — skor gabungan v4 + fitur baru
#
# Kompatibel penuh: semua kolom v4 tetap ada (signal, confidence, sl, tp1-3, dll),
# v7 hanya MENAMBAH kolom baru tanpa menghapus/mengubah kolom existing.
# ═══════════════════════════════════════════════════════════════════════════════

def _vwap_deviation(df):
    """
    Hitung VWAP (Volume Weighted Average Price) session-based dan deviasi harga darinya.
    VWAP adalah salah satu acuan utama institusi untuk menilai apakah harga
    "murah" atau "mahal" relatif terhadap rata-rata transaksi berbobot volume.

    Returns:
        vwap (Series), vwap_dev_pct (Series) — deviasi harga dari VWAP dalam %
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    cum_vol       = df['volume'].cumsum().replace(0, 1e-9)
    cum_vol_price = (typical_price * df['volume']).cumsum()
    vwap          = cum_vol_price / cum_vol
    vwap_dev_pct  = (df['close'] - vwap) / vwap.replace(0, 1e-9) * 100
    return vwap, vwap_dev_pct


def _cvd_proxy(df):
    """
    Cumulative Volume Delta (proxy) — estimasi tekanan beli vs jual tanpa data tick asli.
    Menggunakan posisi close dalam range candle untuk approximate buy/sell volume:
    close dekat high → volume dianggap dominan buy, close dekat low → dominan sell.

    Returns:
        cvd (Series) — kumulatif delta volume
        cvd_slope (Series) — kemiringan CVD 5 bar terakhir (momentum orderflow)
    """
    candle_range = (df['high'] - df['low']).replace(0, 1e-9)
    close_pos    = (df['close'] - df['low']) / candle_range  # 0=low, 1=high
    buy_vol      = df['volume'] * close_pos
    sell_vol     = df['volume'] * (1 - close_pos)
    delta        = buy_vol - sell_vol
    cvd          = delta.cumsum()
    cvd_slope    = (cvd - cvd.shift(5)) / 5
    return cvd, cvd_slope


def _absorption_detection(df, vol_ratio, atr_pct_threshold=0.3):
    """
    Deteksi Absorption / Iceberg Order — volume sangat besar tapi harga
    bergerak sangat kecil. Ini sinyal klasik institusi sedang menyerap
    likuiditas tanpa membiarkan harga bergerak banyak (akumulasi/distribusi diam-diam).

    Returns:
        absorption (Series bool), absorption_direction (Series: 'BULL'/'BEAR'/'')
    """
    candle_body_pct = (df['close'] - df['open']).abs() / df['close'].replace(0, 1e-9) * 100
    high_volume     = vol_ratio > 2.0
    tiny_move       = candle_body_pct < atr_pct_threshold

    absorption = high_volume & tiny_move

    closes_upper_half = (df['close'] - df['low']) / (df['high'] - df['low']).replace(0, 1e-9) > 0.5
    direction = pd.Series(np.where(closes_upper_half, 'BULL', 'BEAR'), index=df.index)
    direction = direction.where(absorption, '')

    return absorption, direction


def _multi_timeframe_confluence(df, df_htf):
    """
    Hitung skor konfluensi antara timeframe utama dan Higher Timeframe (HTF, misal 4h).
    Jika trend HTF searah dengan sinyal di timeframe utama, beri bonus.
    Jika berlawanan, beri penalty. Ini mengurangi false signal yang melawan trend besar.

    Parameters:
        df     : DataFrame timeframe utama (sudah diproses institutional_ai_v4)
        df_htf : DataFrame higher timeframe (sudah diproses institutional_ai_v4), atau None

    Returns:
        mtf_score (Series 0-100), mtf_aligned (Series bool), mtf_note (str untuk log)
    """
    if df_htf is None or len(df_htf) == 0 or 'trend_up' not in df_htf.columns:
        # Tidak ada data HTF — netral, tidak mempengaruhi score
        neutral = pd.Series(50.0, index=df.index)
        aligned = pd.Series(False, index=df.index)
        return neutral, aligned, "HTF tidak tersedia"

    htf_last       = df_htf.iloc[-1]
    htf_trend_up   = bool(htf_last.get('trend_up', False))
    htf_trend_down = bool(htf_last.get('trend_down', False))
    htf_adx        = float(htf_last.get('adx', 0) or 0)

    if htf_trend_up:
        htf_bias = 'UP'
    elif htf_trend_down:
        htf_bias = 'DOWN'
    else:
        htf_bias = 'NEUTRAL'

    mtf_score = pd.Series(50.0, index=df.index)
    aligned_buy  = df['trend_up'] if 'trend_up' in df.columns else pd.Series(False, index=df.index)
    aligned_sell = df['trend_down'] if 'trend_down' in df.columns else pd.Series(False, index=df.index)

    if htf_bias == 'UP':
        bonus = min(25.0, 10.0 + htf_adx * 0.3)
        mtf_score = mtf_score.where(~aligned_buy, mtf_score + bonus)
        mtf_score = mtf_score.where(~aligned_sell, mtf_score - bonus)
    elif htf_bias == 'DOWN':
        bonus = min(25.0, 10.0 + htf_adx * 0.3)
        mtf_score = mtf_score.where(~aligned_sell, mtf_score + bonus)
        mtf_score = mtf_score.where(~aligned_buy, mtf_score - bonus)

    mtf_score = mtf_score.clip(0, 100)
    mtf_aligned = (
        ((htf_bias == 'UP') & aligned_buy) |
        ((htf_bias == 'DOWN') & aligned_sell)
    )
    note = f"HTF bias={htf_bias} (ADX={htf_adx:.0f})"
    return mtf_score, mtf_aligned, note


def institutional_ai_v7(df, df_htf=None):
    """
    Institutional AI V7 — Multi-Timeframe Confluence + Orderflow Proxy Engine.

    Membangun di atas institutional_ai_v4 (reuse seluruh logic indikator, signal,
    SL/TP, scoring yang sudah teruji), menambahkan layer institusional baru:

        - VWAP deviation     : jarak harga dari fair value institusional
        - CVD proxy          : estimasi tekanan beli/jual dari struktur candle
        - Absorption detect  : deteksi akumulasi/distribusi diam-diam institusi
        - Multi-TF confluence: konfirmasi dari timeframe lebih besar (opsional)
        - institutional_score_v7 : skor gabungan akhir 0-100
        - confidence_band_v7 : label keyakinan statistik (LOW/MEDIUM/HIGH/VERY_HIGH)

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV timeframe utama (kolom wajib: open, high, low, close, volume).
    df_htf : pd.DataFrame, optional
        OHLCV timeframe lebih besar (misal 4h) untuk konfirmasi trend.
        Jika None, multi-timeframe confluence di-skip (netral, tidak ada penalty).

    Returns
    -------
    pd.DataFrame
        Semua kolom dari institutional_ai_v4 TETAP ADA, ditambah kolom baru:
        vwap, vwap_dev_pct, cvd, cvd_slope, absorption, absorption_direction,
        mtf_score, mtf_aligned, institutional_score_v7, confidence_band_v7.

    Backward Compatibility
    -----------------------
    Fungsi ini TIDAK mengubah/menghapus kolom apapun dari v4. Kode yang sudah
    bergantung pada institutional_ai_v4() (mis. scanner.py) tetap bisa membaca
    'signal', 'confidence', 'sl', 'tp1', dst dari hasil fungsi ini tanpa perubahan.
    """
    # ── Step 1: jalankan v4 dulu — reuse semua logic yang sudah teruji ──
    data = institutional_ai_v4(df)

    # ── Step 2: VWAP Deviation ──
    data['vwap'], data['vwap_dev_pct'] = _vwap_deviation(data)

    # ── Step 3: CVD Proxy (orderflow tanpa data tick) ──
    data['cvd'], data['cvd_slope'] = _cvd_proxy(data)

    # ── Step 4: Absorption / Iceberg Detection ──
    data['absorption'], data['absorption_direction'] = _absorption_detection(
        data, data['vol_ratio']
    )

    # ── Step 5: Multi-Timeframe Confluence ──
    mtf_score, mtf_aligned, mtf_note = _multi_timeframe_confluence(data, df_htf)
    data['mtf_score']   = mtf_score
    data['mtf_aligned'] = mtf_aligned
    data.attrs['mtf_note'] = mtf_note  # info untuk logging, tidak masuk kolom

    # ── Step 6: Institutional Score V7 — gabungan v4 + fitur baru ──
    # Bobot: 65% dari skor v4 (sudah teruji), 35% dari fitur institusional baru
    vwap_component = (50.0 + data['vwap_dev_pct'].clip(-5, 5) * 5).clip(0, 100)
    cvd_component = (50.0 + (data['cvd_slope'] / (data['volume'].rolling(20).mean().replace(0, 1e-9))).clip(-1, 1) * 50).clip(0, 100)
    absorption_bonus = np.where(
        data['absorption'] & (data['absorption_direction'] == 'BULL'), 8.0,
        np.where(data['absorption'] & (data['absorption_direction'] == 'BEAR'), -8.0, 0.0)
    )

    data['institutional_score_v7'] = (
        data['institutional_score'] * 0.65 +
        vwap_component               * 0.12 +
        cvd_component                * 0.12 +
        data['mtf_score']            * 0.11 +
        absorption_bonus
    ).clip(0, 100)

    # ── Step 7: Confidence Band — label keyakinan statistik ──
    # Hitung jumlah konfirmasi independen yang searah (semakin banyak = semakin yakin)
    buy_signals_aligned = (
        data['trend_up'].astype(int) +
        (data['vwap_dev_pct'] > 0).astype(int) +
        (data['cvd_slope'] > 0).astype(int) +
        data['mtf_aligned'].astype(int) +
        (data['absorption_direction'] == 'BULL').astype(int) +
        data['obv_bull'].astype(int)
    )
    sell_signals_aligned = (
        data['trend_down'].astype(int) +
        (data['vwap_dev_pct'] < 0).astype(int) +
        (data['cvd_slope'] < 0).astype(int) +
        data['mtf_aligned'].astype(int) +
        (data['absorption_direction'] == 'BEAR').astype(int) +
        (~data['obv_bull']).astype(int)
    )
    confirmations = np.where(
        data['signal'].astype(str).str.startswith("BUY"), buy_signals_aligned,
        np.where(data['signal'].astype(str).str.startswith("SELL"), sell_signals_aligned, 0)
    )

    data['confirmations_count'] = confirmations
    data['confidence_band_v7'] = np.select(
        [confirmations >= 5, confirmations >= 4, confirmations >= 2, confirmations >= 0],
        ['VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW'],
        default='LOW'
    )

    # ── Step 8: Fill NaN untuk kolom numerik baru ──
    for col in ['vwap', 'vwap_dev_pct', 'cvd', 'cvd_slope',
                'mtf_score', 'institutional_score_v7']:
        if col in data.columns:
            data[col] = data[col].fillna(0.0)

    return data


def get_institutional_summary_v7(last_row: dict) -> dict:
    """
    Ekstrak ringkasan Institutional AI V7 dari baris terakhir DataFrame
    menjadi dict siap pakai untuk Adaptive Brain V6 (get_adaptive_score).

    Parameters
    ----------
    last_row : dict
        Hasil dari df.iloc[-1].to_dict() setelah institutional_ai_v7().

    Returns
    -------
    dict dengan key yang kompatibel dengan AdaptiveScoreEngine V6:
        institutional_score, order_block_score, fvg_score,
        liquidity_sweep_score, order_block_valid, fvg_valid, liquidity_sweep
    """
    def _g(key, default=0.0):
        v = last_row.get(key, default)
        try:
            fv = float(v)
            return default if (fv != fv) else fv
        except (TypeError, ValueError):
            return default

    bull_ob   = bool(last_row.get('bull_ob', False))
    bear_ob   = bool(last_row.get('bear_ob', False))
    bull_fvg  = bool(last_row.get('bull_fvg', False))
    bear_fvg  = bool(last_row.get('bear_fvg', False))
    liq_sweep_high = bool(last_row.get('liquidity_sweep_high', False))
    liq_sweep_low  = bool(last_row.get('liquidity_sweep_low', False))

    return {
        "institutional_score":     _g('institutional_score_v7', _g('institutional_score', 0)),
        "order_block_score":       80.0 if (bull_ob or bear_ob) else 0.0,
        "order_block_valid":       bull_ob or bear_ob,
        "fvg_score":               75.0 if (bull_fvg or bear_fvg) else 0.0,
        "fvg_valid":               bull_fvg or bear_fvg,
        "liquidity_sweep_score":   70.0 if (liq_sweep_high or liq_sweep_low) else 0.0,
        "liquidity_sweep":         liq_sweep_high or liq_sweep_low,
        "vwap_dev_pct":            _g('vwap_dev_pct', 0),
        "cvd_slope":               _g('cvd_slope', 0),
        "mtf_score":               _g('mtf_score', 50),
        "mtf_aligned":             bool(last_row.get('mtf_aligned', False)),
        "confidence_band":         last_row.get('confidence_band_v7', 'LOW'),
        "confirmations_count":     int(_g('confirmations_count', 0)),
        "absorption":              bool(last_row.get('absorption', False)),
        "absorption_direction":    last_row.get('absorption_direction', ''),
    }
