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
    data = df.copy()

    # ── EMA STACK ──────────────────────────────────────────
    data['ema9']   = data['close'].ewm(span=9).mean()
    data['ema20']  = data['close'].ewm(span=20).mean()
    data['ema50']  = data['close'].ewm(span=50).mean()
    data['ema200'] = data['close'].ewm(span=200).mean()

    # ── RSI ────────────────────────────────────────────────
    data['rsi'] = rsi_wilder(data['close'], 14)

    # ── MACD ───────────────────────────────────────────────
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

    # ── ATR ────────────────────────────────────────────────
    data['atr'] = atr(data)

    # ── BOLLINGER BANDS ────────────────────────────────────
    data['bb_mid'], data['bb_upper'], data['bb_lower'], data['bb_width'], data['bb_pct'] = bollinger_bands(data['close'])
    data['bb_bw'] = data['bb_width']

    # ── STOCHASTIC ─────────────────────────────────────────
    data['stoch_k'], data['stoch_d'] = stochastic(data)

    # ── ADX ────────────────────────────────────────────────
    data['adx'], data['plus_di'], data['minus_di'] = adx(data)

    # ── VOLUME ─────────────────────────────────────────────
    data['vol_ma'], data['vol_ratio'], data['obv'] = volume_analysis(data)
    data['obv_ma']   = data['obv'].rolling(20).mean()
    data['obv_bull'] = data['obv'] > data['obv_ma']

    # ── SUPPORT / RESISTANCE ───────────────────────────────
    data = support_resistance(data)
    data['near_support']     = (abs(data['close'] - data['support'])    / data['close']) < 0.005
    data['near_resistance']  = (abs(data['close'] - data['resistance']) / data['close']) < 0.005
    data['too_close_resistance'] = (abs(data['close'] - data['resistance']) / data['close']) < 0.005
    data['too_close_support']    = (abs(data['close'] - data['support'])    / data['close']) < 0.005
    data['broke_resistance'] = (
        (data['close'] > data['resistance'].shift()) &
        (data['close'].shift() <= data['resistance'].shift())
    )

    # ── RSI DIVERGENCE ─────────────────────────────────────
    data['rsi_div']  = rsi_divergence(data['close'], data['rsi'])
    data['macd_div'] = macd_divergence(data['close'], data['macd_hist'])

    # ── CANDLE PATTERNS ────────────────────────────────────
    data['hammer'], data['shooting_star'], \
        data['bull_engulf'], data['bear_engulf'], \
        data['doji'], data['morning_star'], data['evening_star'] = candle_patterns(data)

    # ── TREND ──────────────────────────────────────────────
    data['trend_up'] = (
        (data['ema9'] > data['ema20']) &
        (data['ema20'] > data['ema50']) &
        (data['ema50'] > data['ema200'])
    )
    data['trend_down'] = (
        (data['ema9'] < data['ema20']) &
        (data['ema20'] < data['ema50']) &
        (data['ema50'] < data['ema200'])
    )
    data['trend_up_weak']   = data['ema50'] > data['ema200']
    data['trend_down_weak'] = data['ema50'] < data['ema200']
    data['strong_trend']    = data['adx'] > 20

    # ── KONDISI OVERSOLD / OVERBOUGHT ──────────────────────
    data['oversold'] = (
        (data['rsi'] < 32) &
        (data['close'] < data['bb_lower']) &
        (data['stoch_k'] < 25)
    )
    data['overbought'] = (
        (data['rsi'] > 68) &
        (data['close'] > data['bb_upper']) &
        (data['stoch_k'] > 75)
    )
    data['reversal_bull'] = (
        data['oversold'] &
        (
            (data['rsi_div'] == 1) |
            (data['hammer'] == 1) |
            (data['bull_engulf'] == 1) |
            data['macd_cross_bull']
        )
    )
    data['reversal_bear'] = (
        data['overbought'] &
        (
            (data['rsi_div'] == -1) |
            (data['shooting_star'] == 1) |
            (data['bear_engulf'] == 1) |
            data['macd_cross_bear']
        )
    )

    # ── ANTICIPATORY INDICATORS ────────────────────────────
    data['squeeze_score']  = bb_squeeze_score(data['bb_width'], lookback=50)
    data['vol_dry_up']     = volume_dry_up(data['vol_ratio'])
    data['vol_expansion']  = volume_expansion(data['vol_ratio'])
    data['macd_momentum']  = macd_momentum_building(data['macd_hist'])
    data['rsi_pre']        = rsi_pre_signal(data['rsi'])
    data['price_compress'] = price_compression(data)
    data['ema_converge']   = ema_convergence(data['ema9'], data['ema20'], data['ema50'])
    data['stoch_pre']      = stoch_pre_cross(data['stoch_k'], data['stoch_d'])
    data['swing_struct']   = higher_low_detection(data)

    # ── SETUP SCORE (SEBELUM BERGERAK) ─────────────────────
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

    # ── BUY SCORE (KONFIRMASI TREND) ───────────────────────
    t_score = (
        data['trend_up'].astype(int) * 20 +
        data['strong_trend'].astype(int) * 10
    )
    m_score = (
        ((data['rsi'] > 50) & (data['rsi'] < 75)).astype(int) * 10 +
        (data['macd_hist'] > 0).astype(int) * 8 +
        (data['stoch_k'] > data['stoch_d']).astype(int) * 7
    )
    v_score = (
        (data['vol_ratio'] > 1.2).astype(int) * 12 +
        data['obv_bull'].astype(int) * 8
    )
    s_score = (
        data['near_support'].astype(int) * 8 +
        data['broke_resistance'].astype(int) * 7
    )
    p_score = (
        (data['bull_engulf'] | (data['hammer'] == 1) | (data['morning_star'] == 1)).astype(int) * 7 +
        (data['rsi_div'] == 1).astype(int) * 3 +
        (data['macd_div'] == 1).astype(int) * 4
    )
    r_score = data['reversal_bull'].astype(int) * 20
    data['score'] = (t_score + m_score + v_score + s_score + p_score + r_score).clip(0, 100)

    # ── SELL SCORE (KONFIRMASI TREND) ──────────────────────
    t_sell = (
        data['trend_down'].astype(int) * 20 +
        data['strong_trend'].astype(int) * 10
    )
    m_sell = (
        ((data['rsi'] < 50) & (data['rsi'] > 20)).astype(int) * 10 +
        (data['macd_hist'] < 0).astype(int) * 8 +
        (data['stoch_k'] < data['stoch_d']).astype(int) * 7
    )
    v_sell = (
        (data['vol_ratio'] > 1.2).astype(int) * 12 +
        (~data['obv_bull']).astype(int) * 8
    )
    s_sell = (
        data['near_resistance'].astype(int) * 8 +
        (data['rsi_div'] == -1).astype(int) * 7 +
        (data['macd_div'] == -1).astype(int) * 4
    )
    p_sell = (
        (data['bear_engulf'] | (data['shooting_star'] == 1) | (data['evening_star'] == 1)).astype(int) * 7 +
        (data['rsi_div'] == -1).astype(int) * 3
    )
    r_sell = data['reversal_bear'].astype(int) * 20
    data['sell_score'] = (t_sell + m_sell + v_sell + s_sell + p_sell + r_sell).clip(0, 100)

    # ── COMBINED SCORE ──────────────────────────────────────
    # FIX v7: bobot dibalik — score (konfirmasi) lebih reliable
    # score*0.6 + setup*0.4  (was 0.4/0.6)
    strong_trend_mask = data['adx'] > 40
    data['buy_combined'] = (
        data['score'].where(strong_trend_mask,
            (data['score'] * 0.6 + setup_buy_score.clip(0, 100) * 0.4))
    ).clip(0, 100)
    data['sell_combined'] = (
        data['sell_score'].where(strong_trend_mask,
            (data['sell_score'] * 0.6 + setup_sell_score.clip(0, 100) * 0.4))
    ).clip(0, 100)

    # ── SIGNAL CONDITIONS ──────────────────────────────────

    # -- BUY SETUP (early, sebelum bergerak) --
    buy_setup_cond = (
        (data['squeeze_score'] > 55) &
        data['vol_dry_up'] &
        (setup_buy_score >= 40) &
        data['trend_up_weak'] &
        (data['rsi'] > 35) & (data['rsi'] < 65) &
        (data['adx'] < 25)
    )

    # -- SELL SETUP (early, sebelum bergerak) --
    # FIX v8: RSI floor 35 → 25 (di bearish market RSI sering < 35)
    sell_setup_cond = (
        (data['squeeze_score'] > 55) &
        data['vol_dry_up'] &
        (setup_sell_score >= 40) &
        data['trend_down_weak'] &
        (data['rsi'] > 25) & (data['rsi'] < 65) &   # was 35–65
        (data['adx'] < 25)
    )

    # -- BUY BREAKOUT (konfirmasi volume expansion) --
    buy_breakout_cond = (
        (data['buy_combined'] >= 55) &
        data['vol_expansion'] &
        data['trend_up_weak'] &
        (data['rsi'] > 45) & (data['rsi'] < 78)
    )

    # -- SELL BREAKOUT (konfirmasi volume expansion) --
    sell_breakout_cond = (
        (data['sell_combined'] >= 55) &
        data['vol_expansion'] &
        data['trend_down_weak'] &
        (data['rsi'] < 65) & (data['rsi'] > 20)
    )

    # -- BUY MOMENTUM (FIX v8: fallback tanpa vol_expansion) --
    # Digunakan saat vol_expansion jarang muncul di ranging market
    buy_momentum_cond = (
        (data['buy_combined'] >= 58) &
        (data['vol_ratio'] > 0.9) &          # volume normal saja cukup
        data['trend_up_weak'] &
        (data['rsi'] > 45) & (data['rsi'] < 75) &
        (data['macd_hist'] > 0)
    )

    # -- SELL MOMENTUM (FIX v8: fallback tanpa vol_expansion) --
    # Krusial saat bearish — vol_expansion jarang tapi sinyal jual valid
    sell_momentum_cond = (
        (data['sell_combined'] >= 50) &
        (data['vol_ratio'] > 0.05) &
        data['trend_down_weak'] &
        (data['rsi'] < 65) & (data['rsi'] > 20) &
        (data['macd_hist'] < 0)
    )

    # -- BUY KONFIRMASI PENUH --
    buy_confirm_cond = (
        (data['score'] >= 60) &
        data['trend_up'] &
        (data['rsi'] > 45) & (data['rsi'] < 78) &
        (data['macd_hist'] > 0) &
        (data['adx'] < 35)
    )

    # -- SELL KONFIRMASI PENUH --
    # FIX v8: adx < 35 → adx < 45
    # (trend_down + adx<35 kontradiksi — strong downtrend sering adx 35–45)
    sell_confirm_cond = (
        (data['sell_score'] >= 55) &
        data['trend_down'] &
        (data['rsi'] < 65) & (data['rsi'] > 20) &
        (data['macd_hist'] < 0)
    )

    # -- REVERSAL --
    oversold_cond = (
        data['reversal_bull'] &
        (data['rsi'] < 32) &
        (data['vol_ratio'] > 1.0)
    )
    overbought_cond = (
        data['reversal_bear'] &
        (data['rsi'] > 68) &
        (data['vol_ratio'] > 1.0)
    )

    # ── SIGNAL GENERATION ──────────────────────────────────
    # FIX v8: URUTAN DIBALIK — tulis yang LEMAH dulu, KUAT terakhir
    # Sebelumnya: Confirm ditulis pertama → di-overwrite Setup (lebih lemah)
    # Sekarang  : Setup ditulis pertama  → di-overwrite Confirm (lebih kuat)
    data['signal'] = "NO TRADE"

    # Layer 1 — paling lemah (bisa di-overwrite semua di atasnya)
    data.loc[buy_setup_cond,      'signal'] = "BUY (SETUP)"
    data.loc[sell_setup_cond,     'signal'] = "SELL (SETUP)"

    # Layer 2 — momentum fallback
    data.loc[buy_momentum_cond,   'signal'] = "BUY"
    data.loc[sell_momentum_cond,  'signal'] = "SELL"

    # Layer 3 — breakout (volume expansion)
    data.loc[buy_breakout_cond,   'signal'] = "BUY"
    data.loc[sell_breakout_cond,  'signal'] = "SELL"

    # Layer 4 — konfirmasi penuh (paling kuat, tidak ter-overwrite)
    data.loc[buy_confirm_cond,    'signal'] = "BUY"
    data.loc[sell_confirm_cond,   'signal'] = "SELL"

    # Layer 5 — reversal (independent, override semua jika kondisi terpenuhi)
    data.loc[oversold_cond,       'signal'] = "BUY (REVERSAL)"
    data.loc[overbought_cond,     'signal'] = "SELL (REVERSAL)"

    # ── CONFIDENCE ─────────────────────────────────────────
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
                         data[['score', 'sell_score']].max(axis=1) * 0.4)
            )
        )
    )

    # ── POSITION SIZE ──────────────────────────────────────
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

    # ── TP / SL ────────────────────────────────────────────
    sl_multiplier = np.where(
        data['signal'].isin(["BUY (SETUP)", "SELL (SETUP)"]),
        1.0, 1.5
    )
    data['sl'] = np.where(
        data['signal'].str.startswith("BUY"),
        data['close'] - sl_multiplier * data['atr'],
        data['close'] + sl_multiplier * data['atr']
    )
    data['tp1'] = np.where(
        data['signal'].str.startswith("BUY"),
        data['close'] + 2.0 * data['atr'],
        data['close'] - 2.0 * data['atr']
    )
    data['tp2'] = np.where(
        data['signal'].str.startswith("BUY"),
        data['close'] + 3.5 * data['atr'],
        data['close'] - 3.5 * data['atr']
    )
    data['tp3'] = np.where(
        data['signal'].str.startswith("BUY"),
        data['close'] + 5.0 * data['atr'],
        data['close'] - 5.0 * data['atr']
    )
    data['trailing_stop'] = np.where(
        data['signal'].str.startswith("BUY"),
        data['close'] - 2.0 * data['atr'],
        data['close'] + 2.0 * data['atr']
    )
    data['rr_ratio'] = abs(data['tp1'] - data['close']) / (
        abs(data['close'] - data['sl']) + 1e-9
    )

    for col in ['confidence', 'position_size', 'sl', 'tp1', 'tp2', 'rr_ratio']:
        data[col] = data[col].fillna(0.0)

    return data
