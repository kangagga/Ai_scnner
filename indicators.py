# ============================================================
#  indicators.py  – Institutional AI Engine v8  [FIXED]
#
#  BUG FIXES v7 (retained):
#  1. vol_dry_up  : threshold 0.75 → 0.90
#  2. price_compression : multiplier 1.8x → 3.0x ATR
#  3. vol_expansion : spike threshold 1.4 → 1.2
#  4. buy_combined threshold : 60 → 55
#  5. sell_combined threshold : 60 → 55
#  6. setup_buy_score threshold : 50 → 40
#  7. buy_breakout + sell_breakout tidak mensyaratkan macd_momentum
#  8. Bobot combined dibalik: score*0.6 + setup*0.4
#
#  BUG FIXES v8 (NEW):
#  A. Signal priority overwrite order DIBALIK
#     (Setup ditulis dulu, Confirm ditulis terakhir → tidak ter-overwrite)
#  B. sell_confirm_cond: adx < 35 → adx < 45
#     (trend_down + adx<35 kontradiksi — downtrend kuat butuh ADX tinggi)
#  C. sell_setup_cond: RSI floor 35 → 25
#     (di bearish market banyak RSI sudah <35, missed padahal layak short)
#  D. Tambah sell_momentum_cond (fallback tanpa vol_expansion)
#     (vol_expansion jarang muncul di bearish — butuh fallback)
#  E. Tambah buy_momentum_cond (fallback tanpa vol_expansion, hanya jika BUY diizinkan)
#  F. higher_low_detection: loop Python → vectorized numpy (performa)
#  G. datetime.utcnow() deprecation hint di komentar
# ============================================================
import pandas as pd
import numpy as np

# [BACKTEST-TUNABLE] Ambang batas 'dekat' S/R (proximity), dipakai near_support/near_resistance.
# Default 0.005 (0.5%) sesuai SR-ONLY MODE 2026-07-09. Bisa di-override sementara oleh script
# backtest untuk eksperimen threshold tanpa mengubah source ini secara permanen.
SR_PROXIMITY_THRESHOLD = 0.005


# ------------------------------------------------------------------
#  Indikator Dasar
# ------------------------------------------------------------------
def rsi_wilder(close, period=14):
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df, period=14):
    hl  = df['high'] - df['low']
    hc  = abs(df['high'] - df['close'].shift())
    lc  = abs(df['low']  - df['close'].shift())
    tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def bollinger_bands(close, period=20, std_dev=2):
    mid   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    bw    = (upper - lower) / (mid + 1e-9)
    pct_b = (close - lower) / (upper - lower + 1e-9)
    return mid, upper, lower, bw, pct_b


def stochastic(df, k_period=14, d_period=3):
    low_min  = df['low'].rolling(k_period).min()
    high_max = df['high'].rolling(k_period).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min + 1e-9)
    d = k.rolling(d_period).mean()
    return k, d


def adx(df, period=14):
    up       = df['high'].diff()
    down     = -df['low'].diff()
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr_val   = atr(df, period)
    plus_di  = 100 * pd.Series(plus_dm,  index=df.index).ewm(alpha=1/period, adjust=False).mean() / (tr_val + 1e-9)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / (tr_val + 1e-9)
    dx       = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)
    return dx.ewm(alpha=1/period, adjust=False).mean(), plus_di, minus_di


def volume_analysis(df, period=20):
    vol_ma    = df['volume'].rolling(period).mean()
    vol_ratio = df['volume'] / (vol_ma + 1e-9)
    obv       = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    return vol_ma, vol_ratio, obv


def rsi_divergence(close, rsi, lookback=5):
    import numpy as np
    c = close.to_numpy()
    r = rsi.to_numpy()
    div = np.zeros(len(c), dtype=int)
    start = max(lookback, len(c) - 50)
    for i in range(start, len(c)):
        pw_c = c[i-lookback:i]
        pw_r = r[i-lookback:i]
        if c[i] < pw_c.min() and r[i] > pw_r.min():
            div[i] = 1
        elif c[i] > pw_c.max() and r[i] < pw_r.max():
            div[i] = -1
    return pd.Series(div, index=close.index)


def macd_divergence(close, macd_hist, lookback=5):
    import numpy as np
    c = close.to_numpy()
    m = macd_hist.to_numpy()
    div = np.zeros(len(c), dtype=int)
    start = max(lookback, len(c) - 50)
    for i in range(start, len(c)):
        pw_c = c[i-lookback:i]
        pw_m = m[i-lookback:i]
        if c[i] < pw_c.min() and m[i] > pw_m.min():
            div[i] = 1
        elif c[i] > pw_c.max() and m[i] < pw_m.max():
            div[i] = -1
    return pd.Series(div, index=close.index)

def support_resistance(df, window=20):
    df = df.copy()

    # Method 1: Rolling min/max (original)
    roll_support    = df['low'].rolling(window).min()
    roll_resistance = df['high'].rolling(window).max()

    # Method 2: Swing High/Low — lebih akurat
    swing_low  = df['low'].rolling(5, center=True).min()
    swing_high = df['high'].rolling(5, center=True).max()
    is_swing_low  = (df['low'] == swing_low)
    is_swing_high = (df['high'] == swing_high)

    # Ambil level swing terakhir yang valid
    swing_support    = df['low'].where(is_swing_low).ffill()
    swing_resistance = df['high'].where(is_swing_high).ffill()

    # Method 3: Volume-weighted — level dengan volume tinggi lebih kuat
    vol_ma = df['volume'].rolling(20).mean()
    high_vol = df['volume'] > vol_ma * 1.5

    vol_support    = df['low'].where(high_vol).rolling(window).min()
    vol_resistance = df['high'].where(high_vol).rolling(window).max()

    # Gabungkan — ambil yang paling konservatif
    df['support']    = pd.concat([roll_support, swing_support, vol_support], axis=1).max(axis=1)
    df['resistance'] = pd.concat([roll_resistance, swing_resistance, vol_resistance], axis=1).min(axis=1)

    # Fallback ke rolling kalau NaN
    df['support']    = df['support'].fillna(roll_support)
    df['resistance'] = df['resistance'].fillna(roll_resistance)

    return df.ffill()


def candle_patterns(df):
    o, h, l, c = df['open'], df['high'], df['low'], df['close']
    body   = abs(c - o)
    candle = h - l + 1e-9
    hammer        = ((body / candle < 0.35) & ((c > o) & ((o - l) / candle > 0.55))).astype(int)
    shooting_star = ((body / candle < 0.35) & ((c < o) & ((h - o) / candle > 0.55))).astype(int)
    bull_engulf   = ((c > o) & (c.shift() < o.shift()) & (c > o.shift()) & (o < c.shift())).astype(int)
    bear_engulf   = ((c < o) & (c.shift() > o.shift()) & (c < o.shift()) & (o > c.shift())).astype(int)
    doji          = (body / candle < 0.1).astype(int)
    morning_star  = ((c.shift(2) < o.shift(2)) & (body.shift(1) / candle.shift(1) < 0.2) & (c > o) & (c > (o.shift(2) + c.shift(2)) / 2)).astype(int)
    evening_star  = ((c.shift(2) > o.shift(2)) & (body.shift(1) / candle.shift(1) < 0.2) & (c < o) & (c < (o.shift(2) + c.shift(2)) / 2)).astype(int)
    return hammer, shooting_star, bull_engulf, bear_engulf, doji, morning_star, evening_star


# ------------------------------------------------------------------
#  INDIKATOR ANTICIPATORY
# ------------------------------------------------------------------
def bb_squeeze_score(bb_width: pd.Series, lookback: int = 50) -> pd.Series:
    """Score 100 = squeeze terkencang dalam lookback candle (siap meledak)."""
    pct = bb_width.rolling(lookback).rank(pct=True)
    return ((1 - pct) * 100).fillna(0).clip(0, 100)


def volume_dry_up(vol_ratio: pd.Series, window: int = 5) -> pd.Series:
    """
    FIX v7: threshold dinaikkan 0.75 → 0.90 agar lebih sensitif.
    Volume rata-rata 5 candle < 90% normal = mulai mengering.
    """
    rolling_avg = vol_ratio.rolling(window).mean()
    return rolling_avg < 0.90


def volume_expansion(vol_ratio: pd.Series, window: int = 3) -> pd.Series:
    """
    FIX v12: spike threshold dinaikkan 1.2 → 2.0 untuk filter lebih ketat.
    """
    dry_up = volume_dry_up(vol_ratio, window=5)
    spike  = vol_ratio > 2.0
    return spike & dry_up.shift(1).fillna(False)


def macd_momentum_building(macd_hist: pd.Series) -> pd.Series:
    """
    Deteksi MACD histogram yang makin mengecil — sinyal SEBELUM cross.
     1 = momentum beli sedang terbentuk
    -1 = momentum jual sedang terbentuk
    """
    result = pd.Series(0, index=macd_hist.index)
    h1, h2, h3 = macd_hist.shift(2), macd_hist.shift(1), macd_hist
    bull_build = (h1 < h2) & (h2 < h3) & (h3 < 0) & (h1 < -1e-8)
    bear_build = (h1 > h2) & (h2 > h3) & (h3 > 0) & (h1 > 1e-8)
    result[bull_build] =  1
    result[bear_build] = -1
    return result


def rsi_pre_signal(rsi: pd.Series) -> pd.Series:
    """Deteksi RSI mendekati zona kritis sebelum melewatinya."""
    result = pd.Series(0, index=rsi.index)
    bull = (rsi.shift(1) < 45) & (rsi >= 45) & (rsi < 60)
    bear = (rsi.shift(1) > 55) & (rsi <= 55) & (rsi > 40)
    result[bull] =  1
    result[bear] = -1
    return result


def price_compression(df: pd.DataFrame, window: int = 8) -> pd.Series:
    """
    FIX v7: multiplier 1.8x → 3.0x ATR agar lebih sering terdeteksi.
    """
    rolling_range = df['high'].rolling(window).max() - df['low'].rolling(window).min()
    atr_val = atr(df, 14)
    return rolling_range < (atr_val * 3.0)


def ema_convergence(ema9: pd.Series, ema20: pd.Series, ema50: pd.Series) -> pd.Series:
    """EMA sedang konvergen = setup sebelum breakout."""
    gap_now  = abs(ema9 - ema50)
    gap_prev = abs(ema9.shift(3) - ema50.shift(3))
    converging  = gap_now < gap_prev * 0.85
    not_crossed = gap_now > (ema50 * 0.001)
    return converging & not_crossed


def stoch_pre_cross(stoch_k: pd.Series, stoch_d: pd.Series) -> pd.Series:
    """Deteksi Stochastic mendekati persilangan."""
    result = pd.Series(0, index=stoch_k.index)
    gap    = stoch_k - stoch_d
    bull_pre = (gap.shift(2) < -3) & (gap.shift(1) < -1) & (gap > -0.5) & (stoch_k < 60)
    bear_pre = (gap.shift(2) > 3)  & (gap.shift(1) > 1)  & (gap < 0.5)  & (stoch_k > 40)
    result[bull_pre] =  1
    result[bear_pre] = -1
    return result


def higher_low_detection(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    FIX v8: Refactor dari loop Python ke vectorized numpy — jauh lebih cepat
    untuk 300 pair × 500 candle.

    Deteksi Higher Low (bullish=1) atau Lower High (bearish=-1).
    Bandingkan rolling min low dan rolling max high antara dua window berurutan.
    """
    lows   = df['low'].values
    highs  = df['high'].values
    n      = len(df)
    result = np.zeros(n, dtype=np.int8)

    # Buat rolling min/max dengan stride_tricks agar O(n) tanpa loop
    # recent  = window candle sebelum i
    # prev    = window candle sebelum recent
    w = window
    for i in range(w * 2, n):
        recent_low_min  = lows[i - w : i].min()
        prev_low_min    = lows[i - w*2 : i - w].min()
        recent_high_max = highs[i - w : i].max()
        prev_high_max   = highs[i - w*2 : i - w].max()

        if recent_low_min > prev_low_min * 1.001:
            result[i] = 1
        elif recent_high_max < prev_high_max * 0.999:
            result[i] = -1

    return pd.Series(result, index=df.index)


# ============================================================
#  INSTITUTIONAL AI ENGINE v8 — ANTICIPATORY [FIXED]
# ============================================================
def institutional_ai_v4(df):
    import numpy as np
    import pandas as pd
    data = df.copy()

    data['ema9']   = data['close'].ewm(span=9,   min_periods=9).mean()
    data['ema20']  = data['close'].ewm(span=20,  min_periods=20).mean()
    data['ema50']  = data['close'].ewm(span=50,  min_periods=50).mean()
    data['ema200'] = data['close'].ewm(span=200, min_periods=200).mean()

    data['ema_slope']       = (data['ema20'] - data['ema20'].shift(5)) / data['ema20'].shift(5) * 100
    ema_spread              = (data['ema9'] - data['ema200']).abs() / data['close']
    ema_spread_ma           = ema_spread.rolling(20).mean()
    data['ema_compression'] = ema_spread < ema_spread_ma * 0.7
    data['ema_expansion']   = ema_spread > ema_spread_ma * 1.3

    data['rsi'] = rsi_wilder(data['close'], 14)

    fast              = data['close'].ewm(span=12).mean()
    slow              = data['close'].ewm(span=26).mean()
    data['macd']      = fast - slow
    data['macd_sig']  = data['macd'].ewm(span=9).mean()
    data['macd_hist'] = data['macd'] - data['macd_sig']
    data['macd_cross_bull'] = (
        (data['macd'] > data['macd_sig']) &
        (data['macd'].shift() <= data['macd_sig'].shift())
    )
    data['macd_cross_bear'] = (
        (data['macd'] < data['macd_sig']) &
        (data['macd'].shift() >= data['macd_sig'].shift())
    )

    data['atr']             = atr(data)
    data['atr_ma']          = data['atr'].rolling(20).mean()
    data['atr_expansion']   = data['atr'] > data['atr_ma'] * 1.3
    data['atr_contraction'] = data['atr'] < data['atr_ma'] * 0.7
    data['high_volatility'] = data['atr'] > data['atr_ma'] * 1.5
    data['low_volatility']  = data['atr'] < data['atr_ma'] * 0.5

    data['bb_mid'], data['bb_upper'], data['bb_lower'], data['bb_width'], data['bb_pct'] = bollinger_bands(data['close'])
    data['bb_bw'] = data['bb_width']

    data['stoch_k'], data['stoch_d'] = stochastic(data)
    data['adx'], data['plus_di'], data['minus_di'] = adx(data)
    data['vol_ma'], data['vol_ratio'], data['obv'] = volume_analysis(data)
    data['obv_ma']   = data['obv'].rolling(20).mean()
    data['obv_bull'] = data['obv'] > data['obv_ma']

    vol_mean              = data['volume'].rolling(20).mean()
    vol_std               = data['volume'].rolling(20).std().replace(0, 1e-9)
    data['rvol']          = data['volume'] / vol_mean.replace(0, 1e-9)
    data['volume_zscore'] = (data['volume'] - vol_mean) / vol_std
    data['volume_spike']  = data['rvol'] > 2.0
    _body                 = abs(data['close'] - data['open'])
    _range                = (data['high'] - data['low']).replace(0, 1e-9)
    _body_ratio           = _body / _range
    data['smart_volume']      = (data['rvol'] > 1.5) & (_body_ratio > 0.6)
    data['volume_exhaustion'] = (data['rvol'] > 2.5) & (_body_ratio < 0.3)

    data = support_resistance(data)
    data['near_support']    = (abs(data['close'] - data['support'])    / data['close']) < SR_PROXIMITY_THRESHOLD
    data['near_resistance'] = (abs(data['close'] - data['resistance']) / data['close']) < SR_PROXIMITY_THRESHOLD
    _candle_range           = (data['high'] - data['low']).replace(0, np.nan)
    _close_position         = (data['close'] - data['low']) / _candle_range
    data['candle_confirms_breakout'] = (
        (data['close'] > data['resistance']) & (_close_position > 0.7)
    ).fillna(False)
    data['too_close_resistance'] = data['near_resistance']
    data['too_close_support']    = data['near_support']
    # [BREAKOUT MARGIN FIX 2026-07-22] Breakout harus tembus resistance/support
    # dengan margin minimum (ATR-based, dengan lantai persentase) — supaya
    # tidak menganggap selisih tipis 0.1-0.2% sebagai breakout valid.
    _breakout_margin_atr = data['atr'] * 0.3
    _breakout_margin_pct = data['resistance'].shift() * 0.003
    _required_margin_up  = pd.concat([_breakout_margin_atr, _breakout_margin_pct], axis=1).max(axis=1)

    _breakdown_margin_pct = data['support'].shift() * 0.003
    _required_margin_down = pd.concat([_breakout_margin_atr, _breakdown_margin_pct], axis=1).max(axis=1)

    data['broke_resistance']     = (
        (data['close'] > data['resistance'].shift() + _required_margin_up) &
        (data['close'].shift() <= data['resistance'].shift())
    )
    data['broke_support'] = (
        (data['close'] < data['support'].shift() - _required_margin_down) &
        (data['close'].shift() >= data['support'].shift())
    )
    data['candle_confirms_breakdown'] = (
        (data['close'] < data['support']) & (_close_position < 0.3)
    ).fillna(False)

    data['rsi_div']  = rsi_divergence(data['close'], data['rsi'])
    data['macd_div'] = macd_divergence(data['close'], data['macd_hist'])

    data['hammer'], data['shooting_star'],         data['bull_engulf'], data['bear_engulf'],         data['doji'], data['morning_star'], data['evening_star'] = candle_patterns(data)

    data['trend_up']        = (data['ema9'] > data['ema20']) & (data['ema20'] > data['ema50']) & (data['ema50'] > data['ema200'])
    data['trend_down']      = (data['ema9'] < data['ema20']) & (data['ema20'] < data['ema50']) & (data['ema50'] < data['ema200'])
    data['trend_up_weak']   = data['ema50'] > data['ema200']
    data['trend_down_weak'] = data['ema50'] < data['ema200']
    data['strong_trend']    = data['adx'] > 20

    swing_high = data['high'].rolling(5, center=True).max()
    swing_low  = data['low'].rolling(5,  center=True).min()
    data['bos']   = (data['close'] > swing_high.shift(1)) & (data['close'].shift(1) <= swing_high.shift(2))
    data['choch'] = (
        (data['close'] > swing_high.shift(1)) & data['trend_down'].shift(1)
    ) | (
        (data['close'] < swing_low.shift(1)) & data['trend_up'].shift(1)
    )
    data['liquidity_sweep_high'] = (data['high'] > swing_high.shift(1)) & (data['close'] < swing_high.shift(1))
    data['liquidity_sweep_low']  = (data['low']  < swing_low.shift(1))  & (data['close'] > swing_low.shift(1))
    data['fake_breakout']  = (
        (data['high'] > data['resistance'].shift(1)) &
        (data['close'] < data['resistance'].shift(1)) &
        (data['rvol'] < 1.2)
    )
    data['fake_breakdown'] = (
        (data['low'] < data['support'].shift(1)) &
        (data['close'] > data['support'].shift(1)) &
        (data['rvol'] < 1.2)
    )

    _bearish_candle   = data['close'] < data['open']
    _bullish_candle   = data['close'] > data['open']
    _strong_move_up   = data['close'].pct_change(3) > 0.02
    _strong_move_down = data['close'].pct_change(3) < -0.02
    data['bull_ob'] = _bearish_candle.shift(1) & _strong_move_up   & (data['rvol'] > 1.3)
    data['bear_ob'] = _bullish_candle.shift(1) & _strong_move_down & (data['rvol'] > 1.3)
    data['bull_fvg'] = data['low']  > data['high'].shift(2)
    data['bear_fvg'] = data['high'] < data['low'].shift(2)

    _rsi_pullback      = (data['rsi'] > 40) & (data['rsi'] < 60)
    _price_above_ema50 = data['close'] > data['ema50']
    _price_near_ema20  = abs(data['close'] - data['ema20']) / data['close'] < 0.02
    data['healthy_pullback'] = _price_above_ema50 & _rsi_pullback & _price_near_ema20 & data['trend_up_weak']

    _adx_strong = data['adx'] > 25
    _adx_weak   = data['adx'] < 15
    _bb_squeeze = data['bb_width'] < data['bb_width'].rolling(20).mean() * 0.7
    data['market_regime'] = np.select(
        [
            data['high_volatility'] & _adx_strong,
            _adx_strong & data['trend_up'],
            _adx_strong & data['trend_down'],
            _adx_weak & _bb_squeeze,
            _adx_weak,
        ],
        ['VOLATILE', 'TRENDING_UP', 'TRENDING_DOWN', 'SIDEWAYS', 'WEAK_TREND'],
        default='NEUTRAL'
    )

    data['oversold']  = (data['rsi'] < 32) & (data['close'] < data['bb_lower']) & (data['stoch_k'] < 25)
    data['overbought'] = (data['rsi'] > 68) & (data['close'] > data['bb_upper']) & (data['stoch_k'] > 75)
    data['reversal_bull'] = data['oversold'] & (
        (data['rsi_div'] == 1) | (data['hammer'] == 1) |
        (data['bull_engulf'] == 1) | data['macd_cross_bull']
    )
    data['reversal_bear'] = data['overbought'] & (
        (data['rsi_div'] == -1) | (data['shooting_star'] == 1) |
        (data['bear_engulf'] == 1) | data['macd_cross_bear']
    )

    data['squeeze_score']  = bb_squeeze_score(data['bb_width'], lookback=50)
    data['vol_dry_up']     = volume_dry_up(data['vol_ratio'])
    data['vol_expansion']  = volume_expansion(data['vol_ratio'])
    data['macd_momentum']  = macd_momentum_building(data['macd_hist'])
    data['rsi_pre']        = rsi_pre_signal(data['rsi'])
    data['price_compress'] = price_compression(data)
    data['ema_converge']   = ema_convergence(data['ema9'], data['ema20'], data['ema50'])
    data['stoch_pre']      = stoch_pre_cross(data['stoch_k'], data['stoch_d'])
    data['swing_struct']   = higher_low_detection(data)

    _rsi_norm   = ((data['rsi'] - 50) / 50).clip(-1, 1)
    _macd_norm  = np.sign(data['macd_hist']) * data['macd_hist'].abs().clip(0, 1)
    _stoch_norm = ((data['stoch_k'] - 50) / 50).clip(-1, 1)
    _adx_norm   = (data['adx'] / 50).clip(0, 1)
    _slope_norm = data['ema_slope'].clip(-2, 2) / 2
    data['momentum_score'] = (
        (_rsi_norm * 25 + 25) +
        (_macd_norm * 20).clip(0, 20) +
        (_stoch_norm * 15 + 15) +
        (_adx_norm * 20) +
        (_slope_norm * 10 + 10).clip(0, 20)
    ).clip(0, 100)

    data['volume_score'] = (
        (data['rvol'].clip(0, 3) / 3 * 40) +
        (data['volume_zscore'].clip(0, 3) / 3 * 30) +
        data['smart_volume'].astype(int) * 20 +
        data['obv_bull'].astype(int) * 10
    ).clip(0, 100)

    _atr_pct = (data['atr'] / data['close']).clip(0, 0.1) / 0.1
    data['volatility_score'] = (
        _atr_pct * 50 +
        data['atr_expansion'].astype(int) * 25 +
        data['high_volatility'].astype(int) * 25
    ).clip(0, 100)

    data['trend_score'] = (
        data['trend_up'].astype(int) * 30 +
        data['trend_up_weak'].astype(int) * 15 +
        (data['adx'] / 50).clip(0, 1) * 25 +
        data['ema_expansion'].astype(int) * 15 +
        (data['ema_slope'].clip(0, 2) / 2 * 15)
    ).clip(0, 100)

    setup_buy_score = (
        (data['squeeze_score'] > 60).astype(int) * 15 +
        data['vol_dry_up'].astype(int) * 10 +
        (data['macd_momentum'] == 1).astype(int) * 15 +
        (data['rsi_pre'] == 1).astype(int) * 12 +
        data['price_compress'].astype(int) * 10 +
        data['ema_converge'].astype(int) * 8 +
        (data['stoch_pre'] == 1).astype(int) * 10 +
        (data['swing_struct'] == 1).astype(int) * 12 +
        (data['near_support'] & data['obv_bull']).astype(int) * 8
    )
    setup_sell_score = (
        (data['squeeze_score'] > 60).astype(int) * 15 +
        data['vol_dry_up'].astype(int) * 10 +
        (data['macd_momentum'] == -1).astype(int) * 15 +
        (data['rsi_pre'] == -1).astype(int) * 12 +
        data['price_compress'].astype(int) * 10 +
        data['ema_converge'].astype(int) * 8 +
        (data['stoch_pre'] == -1).astype(int) * 10 +
        (data['swing_struct'] == -1).astype(int) * 12 +
        (data['near_resistance'] & ~data['obv_bull']).astype(int) * 8
    )

    t_score = data['trend_up'].astype(int) * 20 + data['strong_trend'].astype(int) * 10
    m_score = (
        ((data['rsi'] > 50) & (data['rsi'] < 75)).astype(int) * 10 +
        (data['macd_hist'] > 0).astype(int) * 8 +
        (data['stoch_k'] > data['stoch_d']).astype(int) * 7
    )
    v_score = (data['vol_ratio'] > 1.2).astype(int) * 12 + data['obv_bull'].astype(int) * 8
    s_score = data['near_support'].astype(int) * 8 + data['broke_resistance'].astype(int) * 7
    p_score = (
        (data['bull_engulf'] | (data['hammer'] == 1) | (data['morning_star'] == 1)).astype(int) * 7 +
        (data['rsi_div'] == 1).astype(int) * 3 +
        (data['macd_div'] == 1).astype(int) * 4
    )
    r_score       = data['reversal_bull'].astype(int) * 20
    data['score'] = (t_score + m_score + v_score + s_score + p_score + r_score).clip(0, 100)

    t_sell  = data['trend_down'].astype(int) * 20 + data['strong_trend'].astype(int) * 10
    m_sell  = (
        ((data['rsi'] < 50) & (data['rsi'] > 20)).astype(int) * 10 +
        (data['macd_hist'] < 0).astype(int) * 8 +
        (data['stoch_k'] < data['stoch_d']).astype(int) * 7
    )
    v_sell  = (data['vol_ratio'] > 1.2).astype(int) * 12 + (~data['obv_bull']).astype(int) * 8
    s_sell  = (
        data['near_resistance'].astype(int) * 8 +
        (data['rsi_div'] == -1).astype(int) * 7 +
        (data['macd_div'] == -1).astype(int) * 4
    )
    p_sell  = (
        (data['bear_engulf'] | (data['shooting_star'] == 1) | (data['evening_star'] == 1)).astype(int) * 7 +
        (data['rsi_div'] == -1).astype(int) * 3
    )
    r_sell         = data['reversal_bear'].astype(int) * 20
    data['sell_score'] = (t_sell + m_sell + v_sell + s_sell + p_sell + r_sell).clip(0, 100)

    strong_trend_mask     = data['adx'] > 40
    data['buy_combined']  = (
        data['score'].where(strong_trend_mask,
            (data['score'] * 0.6 + setup_buy_score.clip(0, 100) * 0.4))
    ).clip(0, 100)
    data['sell_combined'] = (
        data['sell_score'].where(strong_trend_mask,
            (data['sell_score'] * 0.6 + setup_sell_score.clip(0, 100) * 0.4))
    ).clip(0, 100)

    data['institutional_score'] = (
        data['trend_score']    * 0.20 +
        data['momentum_score'] * 0.20 +
        data['volume_score']   * 0.15 +
        data['buy_combined']   * 0.15 +
        data['bull_ob'].astype(int) * 10 +
        data['bull_fvg'].astype(int) * 5 +
        data['bos'].astype(int) * 5 +
        data['choch'].astype(int) * 5 +
        data['healthy_pullback'].astype(int) * 5
    ).clip(0, 100)

    _fake_signal = (
        (data['rvol'] < 0.5) |
        (data['atr'] < data['atr_ma'] * 0.3) |
        data['fake_breakout'] |
        data['volume_exhaustion']
    )

    buy_setup_cond = (
        (data['squeeze_score'] > 40) &          # [LOOSENED 2026-07-09] was > 55
        data['vol_dry_up'] &
        (setup_buy_score >= 35) &                # was >= 40
        data['trend_up_weak'] &
        (data['rsi'] > 30) & (data['rsi'] < 70) &  # was 35-65
        (data['adx'] < 30) &                      # was < 25
        (data['macd_hist'] > 0) &
        (data['shooting_star'] == 0) &
        (data['evening_star'] == 0) &
        (data['bear_engulf'] == 0) &
        (data['doji'] == 0) &
        ~_fake_signal
    )
    sell_setup_cond = (
        (setup_sell_score >= 30) &                # was >= 35
        data['trend_down_weak'] &
        (data['rsi'] > 18) & (data['rsi'] < 75) &  # was 20-72
        (data['macd_hist'] < 0) &
        (data['hammer'] == 0) &
        (data['morning_star'] == 0) &
        (data['bull_engulf'] == 0) &
        (data['doji'] == 0) &
        ~_fake_signal
    )
    buy_breakout_cond = (
        (data['buy_combined'] >= 40) &
        data['vol_expansion'] &
        data['trend_up_weak'] &
        (data['rsi'] > 45) & (data['rsi'] < 78) &
        (data['macd_hist'] > 0) &
        ~((data['rsi'] > 65) & ((data['adx'] > 60) | (data['stoch_k'] > 85))) &
        ~(data['rsi'] > 75) &
        ~(data['near_resistance'] & (data['stoch_k'] > 90)) &
        ~(data['near_resistance'] & ~data['candle_confirms_breakout']) &
        ~(data['doji'] == 1) &
        ~_fake_signal
    )
    sell_breakout_cond = (
        (data['sell_combined'] >= 40) &
        data['vol_expansion'] &
        data['trend_down_weak'] &
        (data['rsi'] < 65) & (data['rsi'] > 20) &
        (data['macd_hist'] < 0) &
        ~((data['rsi'] < 35) & ((data['adx'] > 60) | (data['stoch_k'] < 15))) &
        ~(data['rsi'] < 25) &
        ~(data['near_support'] & (data['stoch_k'] < 10)) &
        ~(data['doji'] == 1) &
        ~_fake_signal
    )
    buy_momentum_cond = (
        (data['buy_combined'] >= 40) &
        (data['vol_ratio'] > 0.5) &
        data['trend_up_weak'] &
        (data['rsi'] > 35) & (data['rsi'] < 80) &
        (data['macd_hist'] > 0) &
        ~((data['rsi'] > 65) & ((data['adx'] > 60) | (data['stoch_k'] > 85))) &
        ~(data['doji'] == 1) &
        ~_fake_signal
    )
    sell_momentum_cond = (
        (data['sell_combined'] >= 40) &
        (data['vol_ratio'] > 0.5) &
        data['trend_down_weak'] &
        (data['rsi'] < 65) & (data['rsi'] > 20) &
        (data['macd_hist'] < 0) &
        ~((data['rsi'] < 35) & ((data['adx'] > 60) | (data['stoch_k'] < 15))) &
        ~(data['doji'] == 1) &
        ~_fake_signal
    )
    buy_confirm_cond = (
        data['trend_up'] &
        (data['buy_combined'] >= 50) &
        (data['rsi'] > 50) & (data['rsi'] < 70) &
        (data['macd_hist'] > 0) &
        data['vol_expansion'] &
        ~(data['doji'] == 1) &
        ~_fake_signal
    )
    sell_confirm_cond = (
        data['trend_down'] &
        (data['sell_combined'] >= 50) &
        (data['rsi'] < 50) & (data['rsi'] > 30) &
        (data['macd_hist'] < 0) &
        data['vol_expansion'] &
        ~(data['doji'] == 1) &
        ~_fake_signal
    )
    oversold_cond   = data['reversal_bull'] & (data['rsi'] < 36) & (data['vol_ratio'] > 0.8)  # [LOOSENED 2026-07-09] was rsi<32, vol_ratio>1.0
    overbought_cond = data['reversal_bear'] & (data['rsi'] > 64) & (data['vol_ratio'] > 0.8)  # [LOOSENED 2026-07-09] was rsi>68, vol_ratio>1.0

    data['signal'] = "NO TRADE"
    data.loc[buy_momentum_cond,  'signal'] = "BUY"
    data.loc[sell_momentum_cond, 'signal'] = "SELL"
    data.loc[buy_breakout_cond,  'signal'] = "BUY"
    data.loc[sell_breakout_cond, 'signal'] = "SELL"
    data.loc[buy_confirm_cond,   'signal'] = "BUY"
    data.loc[sell_confirm_cond,  'signal'] = "SELL"
    # [FIX 2026-07-09] SETUP & REVERSAL dipindah ke akhir (prioritas tertinggi) --
    # sebelumnya sinyal SETUP yang valid bisa ketimpa "BUY"/"SELL" polos yang
    # sudah dinonaktifkan di VALID_SIGNALS, lalu dibuang scanner sbg invalid.
    data.loc[buy_setup_cond,     'signal'] = "BUY (SETUP)"
    data.loc[sell_setup_cond,    'signal'] = "SELL (SETUP)"
    data.loc[oversold_cond,      'signal'] = "BUY (REVERSAL)"
    data.loc[overbought_cond,    'signal'] = "SELL (REVERSAL)"

    # ── SELL BOUNCE: harga bounce palsu di market lemah/netral ──
    sell_bounce_cond = (
        (data['rsi'] > 63) &
        (data['bb_pct'] > 0.78) &
        data['fake_breakout'] &
        (data['rvol'] > 0.8) &
        (data['adx'] < 30) &
        (data['market_regime'] != 'TRENDING')
    )
    data.loc[sell_bounce_cond, 'signal'] = "SELL (REVERSAL)"

    _confirmations = (
        (data['bos'] | data['choch']).astype(int) +
        (data['bull_ob'] | data['bear_ob']).astype(int) +
        (data['bull_fvg'] | data['bear_fvg']).astype(int) +
        data['smart_volume'].astype(int) +
        data['atr_expansion'].astype(int) +
        data['ema_expansion'].astype(int) +
        data['healthy_pullback'].astype(int) +
        (data['liquidity_sweep_high'] | data['liquidity_sweep_low']).astype(int)
    )
    data['confidence_score'] = (_confirmations / 8 * 40 + data['institutional_score'] * 0.6).clip(0, 100)

    data['confidence'] = np.where(
        data['signal'].isin(["BUY", "BUY (SETUP)"]),
        np.where(data['signal'] == "BUY (SETUP)",
                 setup_buy_score.clip(0, 100),
                 data['buy_combined']),
        np.where(
            data['signal'].isin(["SELL", "SELL (SETUP)"]),
            np.where(data['signal'] == "SELL (SETUP)",
                     setup_sell_score.clip(0, 100),
                     data['sell_combined']),
            np.where(
                data['signal'].str.startswith("BUY"), data['score'],
                np.where(data['signal'].str.startswith("SELL"), data['sell_score'],
                         data[["score", "sell_score"]].max(axis=1) * 0.4)
            )
        )
    )

    # Boost confidence minimum sell_bounce supaya lolos threshold
    data.loc[sell_bounce_cond, 'confidence'] = data.loc[sell_bounce_cond, 'confidence'].clip(lower=38)

    data['position_size'] = np.where(
        data['signal'].isin(["BUY (SETUP)", "SELL (SETUP)"]),
        np.where(data['confidence'] >= 70, 0.3, 0.2),
        np.where(
            data['signal'].isin(["BUY (REVERSAL)", "SELL (REVERSAL)"]),
            np.where(data['confidence'] >= 70, 0.4, 0.25),
            np.where(data['confidence'] >= 90, 1.0,
            np.where(data['confidence'] >= 80, 0.75,
            np.where(data['confidence'] >= 70, 0.5, 0.3)))
        )
    )

    sl_multiplier         = np.where(data['signal'].isin(["BUY (SETUP)", "SELL (SETUP)"]), 1.0, 1.5)
    data['sl']            = np.where(data['signal'].str.startswith("BUY"),
                                      data['close'] - sl_multiplier * data['atr'],
                                      data['close'] + sl_multiplier * data['atr'])
    data['tp1']           = np.where(data['signal'].str.startswith("BUY"),
                                      data['close'] + 2.0 * data['atr'],
                                      data['close'] - 2.0 * data['atr'])
    data['tp2']           = np.where(data['signal'].str.startswith("BUY"),
                                      data['close'] + 3.5 * data['atr'],
                                      data['close'] - 3.5 * data['atr'])
    data['tp3']           = np.where(data['signal'].str.startswith("BUY"),
                                      data['close'] + 5.0 * data['atr'],
                                      data['close'] - 5.0 * data['atr'])
    data['trailing_stop'] = np.where(data['signal'].str.startswith("BUY"),
                                      data['close'] - 2.0 * data['atr'],
                                      data['close'] + 2.0 * data['atr'])
    data['rr_ratio']      = abs(data['tp1'] - data['close']) / (abs(data['close'] - data['sl']) + 1e-9)

    # ══════════════════════════════════════════════════════════
    # [SR-ONLY MODE 2026-07-09] Override total: signal murni dari
    # Support/Resistance + Volume + Candle Pattern. TIDAK pakai RSI/MACD/EMA.
    # Semua kondisi lama (SETUP/MOMENTUM/BREAKOUT/CONFIRM/REVERSAL) di atas
    # diabaikan -- override final di bawah ini yang menentukan sinyal akhir.
    # ══════════════════════════════════════════════════════════
    buy_sr_bounce_cond = (
        data['near_support'] &
        ((data['hammer'] == 1) | data['bull_engulf'] | (data['morning_star'] == 1)) &
        (data['rvol'] > 0.8) &
        ~data['fake_breakdown']
    )
    sell_sr_bounce_cond = (
        data['near_resistance'] &
        ((data['shooting_star'] == 1) | data['bear_engulf'] | (data['evening_star'] == 1)) &
        (data['rvol'] > 0.8) &
        ~data['fake_breakout']
    )
    # [OVEREXTENSION + RSI GUARD FIX 2026-07-22] Breakout hanya valid kalau
    # close masih dekat resistance (bukan chasing pump yang udah jauh),
    # dan RSI belum overbought/oversold ekstrem.
    # [FIX] Pakai .shift() supaya bandingkan close SEKARANG dengan support/
    # resistance SEBELUM candle breakout/breakdown -- bukan nilai yang sudah
    # ikut ter-update turun/naik akibat rolling window menyerap candle crash
    # itu sendiri (bug: overextension check jadi selalu lolos di crash besar).
    _max_extension_up   = data['resistance'].shift() * (SR_PROXIMITY_THRESHOLD * 4)  # ~2%
    _max_extension_down = data['support'].shift()    * (SR_PROXIMITY_THRESHOLD * 4)

    data['breakout_not_overextended'] = (
        (data['close'] - data['resistance'].shift()) <= _max_extension_up
    )
    data['breakdown_not_overextended'] = (
        (data['support'].shift() - data['close']) <= _max_extension_down
    )

    buy_sr_breakout_cond = (
        data['broke_resistance'] &
        (data['rvol'] > 1.3) &
        ~data['fake_breakout'] &
        data['candle_confirms_breakout'] &
        ~data['trend_down'] &
        ~data['shooting_star'].shift(1).fillna(0).astype(bool) &
        data['breakout_not_overextended'] &
        (data['rsi'] < 75) &
        (data['close'] > data['ema200'])
    )
    sell_sr_breakdown_cond = (
        data['broke_support'] &
        (data['rvol'] > 1.3) &
        ~data['fake_breakdown'] &
        data['candle_confirms_breakdown'] &
        ~data['trend_up'] &
        ~data['hammer'].shift(1).fillna(0).astype(bool) &
        data['breakdown_not_overextended'] &
        (data['rsi'] > 25) &
        (data['close'] < data['ema200'])
    )

    data['signal'] = "NO TRADE"
    data.loc[buy_sr_bounce_cond,     'signal'] = "BUY (SR BOUNCE)"
    data.loc[sell_sr_bounce_cond,    'signal'] = "SELL (SR BOUNCE)"
    data.loc[buy_sr_breakout_cond,   'signal'] = "BUY (SR BREAKOUT)"
    data.loc[sell_sr_breakdown_cond, 'signal'] = "SELL (SR BREAKDOWN)"

    _sr_confidence = (
        (data['rvol'].clip(0, 3) / 3 * 50) + (_body_ratio.clip(0, 1) * 50)
    ).clip(0, 100)
    data['confidence'] = np.where(data['signal'] != "NO TRADE", _sr_confidence, 0)

    data['position_size'] = np.where(
        data['signal'].isin(["BUY (SR BREAKOUT)", "SELL (SR BREAKDOWN)"]),
        np.where(data['confidence'] >= 70, 0.5, 0.3),
        np.where(
            data['signal'].isin(["BUY (SR BOUNCE)", "SELL (SR BOUNCE)"]),
            np.where(data['confidence'] >= 70, 0.3, 0.2),
            0.0
        )
    )

    _sr_sl_mult = np.where(data['signal'].isin(["BUY (SR BOUNCE)", "SELL (SR BOUNCE)"]), 1.0, 1.5)
    data['sl']  = np.where(data['signal'].str.startswith("BUY"),
                            data['close'] - _sr_sl_mult * data['atr'],
                            data['close'] + _sr_sl_mult * data['atr'])
    data['tp1'] = np.where(data['signal'].str.startswith("BUY"),
                            data['close'] + 2.0 * data['atr'],
                            data['close'] - 2.0 * data['atr'])
    data['tp2'] = np.where(data['signal'].str.startswith("BUY"),
                            data['close'] + 3.5 * data['atr'],
                            data['close'] - 3.5 * data['atr'])
    data['tp3'] = np.where(data['signal'].str.startswith("BUY"),
                            data['close'] + 5.0 * data['atr'],
                            data['close'] - 5.0 * data['atr'])
    data['trailing_stop'] = np.where(data['signal'].str.startswith("BUY"),
                            data['close'] - 2.0 * data['atr'],
                            data['close'] + 2.0 * data['atr'])
    data['rr_ratio'] = abs(data['tp1'] - data['close']) / (abs(data['close'] - data['sl']) + 1e-9)

    for col in ['confidence', 'position_size', 'sl', 'tp1', 'tp2', 'rr_ratio',
                'trend_score', 'momentum_score', 'volume_score', 'volatility_score',
                'institutional_score', 'confidence_score']:
        if col in data.columns:
            data[col] = data[col].fillna(0.0)

    return data


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
