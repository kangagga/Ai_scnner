"""
chart_patterns.py
==================
Deteksi chart pattern kompleks (swing-based) sebagai KONFIRMASI TAMBAHAN
untuk sinyal yang sudah ada di ai-scanner (BOUNCE, SETUP, REJECTION).

STATUS: STANDALONE / PROOF-OF-CONCEPT. Belum diintegrasikan ke indicators.py,
scanner.py, atau telegram_sender.py. Jalankan test_patterns.py dulu untuk
verifikasi manual sebelum integrasi.

Tidak pakai scipy — swing high/low pakai custom peak-finder (rolling window
comparison) supaya tidak nambah dependency dan lebih mudah dikontrol untuk
data crypto yang noisy.

Semua fungsi menerima pandas DataFrame `df` dengan kolom minimal:
    open, high, low, close, volume
dan mengembalikan dict:
    {
        "detected": bool,
        "pattern": str,          # nama pattern kalau detected
        "direction": "bullish" | "bearish",
        "strength": float,       # 0.0 - 1.0, seberapa "bersih" pola ini
        "details": dict,         # info tambahan (level neckline, index peak, dll)
    }
"""

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# 1. SWING HIGH/LOW DETECTION (dasar untuk semua pattern di bawah)
# ---------------------------------------------------------------------------

def find_swing_points(df: pd.DataFrame, order: int = 5):
    """
    Cari swing high & swing low pakai rolling window comparison.
    order=5 artinya sebuah titik dianggap swing high/low kalau dia adalah
    titik tertinggi/terendah dibanding 5 candle di kiri DAN 5 candle di kanan.

    Return: (swing_highs, swing_lows)
        masing-masing list of tuple (index_posisi, harga)
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    swing_highs = []
    swing_lows = []

    for i in range(order, n - order):
        window_high = highs[i - order: i + order + 1]
        window_low = lows[i - order: i + order + 1]

        if highs[i] == window_high.max() and np.argmax(window_high) == order:
            swing_highs.append((i, highs[i]))

        if lows[i] == window_low.min() and np.argmin(window_low) == order:
            swing_lows.append((i, lows[i]))

    return swing_highs, swing_lows


def _pct_diff(a, b):
    """Persentase selisih dua harga, dipakai untuk toleransi 'setara'."""
    return abs(a - b) / max(a, b)


def _segment_width_ratio_ok(i1: int, i2: int, i3: int,
                             min_ratio: float = 0.35, max_ratio: float = 2.85):
    """
    Cek 2 segmen antar swing point (i1->i2 dan i2->i3) punya lebar yang
    proporsional, bukan timpang jauh. Pump-dump 1 candle tunggal sering
    menghasilkan swing point yang jaraknya sangat timpang (misal 2 candle
    vs 40 candle), yang menandakan itu bukan struktur pattern asli
    melainkan noise dari satu lonjakan tajam.
    """
    w1 = i2 - i1
    w2 = i3 - i2
    if w1 <= 0 or w2 <= 0:
        return False
    ratio = w1 / w2
    return min_ratio <= ratio <= max_ratio


def _max_single_candle_dominance(df: pd.DataFrame, start_idx: int, end_idx: int):
    """
    Rasio (range candle tunggal terbesar) terhadap (total range window).
    Kalau rasio ini tinggi (mendekati/di atas ~0.5), artinya bentuk
    'pattern' itu didominasi oleh satu lonjakan candle ekstrem (pump/dump
    tunggal), bukan struktur multi-candle asli -> harus ditolak.
    """
    start_idx = max(0, start_idx)
    end_idx = min(len(df) - 1, end_idx)
    window = df.iloc[start_idx:end_idx + 1]
    if len(window) == 0:
        return 1.0
    total_range = window["high"].max() - window["low"].min()
    if total_range <= 0:
        return 0.0
    max_candle_range = (window["high"] - window["low"]).max()
    return max_candle_range / total_range


# Ambang batas dominasi candle tunggal: kalau 1 candle sendirian menyumbang
# lebih dari 50% total range window pattern, tolak pattern itu (indikasi
# pump-dump ekstrem, bukan struktur wajar).
MAX_SINGLE_CANDLE_DOMINANCE = 0.5


# ---------------------------------------------------------------------------
# 2. DOUBLE TOP / DOUBLE BOTTOM  (proof-of-concept pertama)
# ---------------------------------------------------------------------------

def detect_double_top_bottom(df: pd.DataFrame, order: int = 5,
                              peak_tolerance: float = 0.015,
                              min_trough_depth: float = 0.02):
    """
    Double Top: 2 swing high setara, dipisahkan 1 swing low yang cukup dalam
                di antaranya. Konfirmasi: close terakhir break di bawah
                level swing low tengah (neckline).
    Double Bottom: kebalikannya.

    peak_tolerance: toleransi selisih harga antar 2 peak/trough (1.5% default)
    min_trough_depth: swing low/high tengah harus minimal sekian % lebih
                       rendah/tinggi dari kedua peak/trough di sisinya,
                       supaya bukan noise datar.
    """
    swing_highs, swing_lows = find_swing_points(df, order=order)
    last_close = df["close"].iloc[-1]
    result = {"detected": False, "pattern": None, "direction": None,
              "strength": 0.0, "details": {}}

    # --- Double Top ---
    if len(swing_highs) >= 2:
        # ambil 2 swing high terakhir
        (i1, p1), (i2, p2) = swing_highs[-2], swing_highs[-1]
        if _pct_diff(p1, p2) <= peak_tolerance:
            # cari swing low di antara i1 dan i2 (neckline)
            mid_lows = [(i, p) for (i, p) in swing_lows if i1 < i < i2]
            if mid_lows:
                neck_i, neck_p = min(mid_lows, key=lambda x: x[1])
                depth1 = _pct_diff(p1, neck_p)
                depth2 = _pct_diff(p2, neck_p)
                width_ok = _segment_width_ratio_ok(i1, neck_i, i2)
                dominance = _max_single_candle_dominance(df, i1, i2)
                if (depth1 >= min_trough_depth and depth2 >= min_trough_depth
                        and width_ok and dominance <= MAX_SINGLE_CANDLE_DOMINANCE):
                    breakout = last_close < neck_p
                    strength = min(1.0, (depth1 + depth2) / 2 / 0.05)
                    result.update({
                        "detected": bool(breakout),
                        "pattern": "Double Top",
                        "direction": "bearish",
                        "strength": round(strength, 2) if breakout else 0.0,
                        "details": {
                            "peak1_idx": i1, "peak1_price": p1,
                            "peak2_idx": i2, "peak2_price": p2,
                            "neckline_idx": neck_i, "neckline_price": neck_p,
                            "breakout_confirmed": breakout,
                        },
                    })
                    if breakout:
                        return result

    # --- Double Bottom ---
    if len(swing_lows) >= 2:
        (i1, p1), (i2, p2) = swing_lows[-2], swing_lows[-1]
        if _pct_diff(p1, p2) <= peak_tolerance:
            mid_highs = [(i, p) for (i, p) in swing_highs if i1 < i < i2]
            if mid_highs:
                neck_i, neck_p = max(mid_highs, key=lambda x: x[1])
                depth1 = _pct_diff(neck_p, p1)
                depth2 = _pct_diff(neck_p, p2)
                width_ok = _segment_width_ratio_ok(i1, neck_i, i2)
                dominance = _max_single_candle_dominance(df, i1, i2)
                if (depth1 >= min_trough_depth and depth2 >= min_trough_depth
                        and width_ok and dominance <= MAX_SINGLE_CANDLE_DOMINANCE):
                    breakout = last_close > neck_p
                    strength = min(1.0, (depth1 + depth2) / 2 / 0.05)
                    result = {
                        "detected": bool(breakout),
                        "pattern": "Double Bottom",
                        "direction": "bullish",
                        "strength": round(strength, 2) if breakout else 0.0,
                        "details": {
                            "trough1_idx": i1, "trough1_price": p1,
                            "trough2_idx": i2, "trough2_price": p2,
                            "neckline_idx": neck_i, "neckline_price": neck_p,
                            "breakout_confirmed": breakout,
                        },
                    }

    return result


# ---------------------------------------------------------------------------
# 3. HEAD AND SHOULDERS (dan inverse)
# ---------------------------------------------------------------------------

def detect_head_and_shoulders(df: pd.DataFrame, order: int = 5,
                               shoulder_tolerance: float = 0.03,
                               head_min_prominence: float = 0.02):
    """
    H&S: 3 swing high berurutan (L-shoulder, Head, R-shoulder) dimana
    Head > kedua shoulder, dan kedua shoulder relatif setara.
    Neckline = garis penghubung 2 swing low di antara shoulder-head-shoulder.
    Konfirmasi: close break di bawah neckline (pendekatan disederhanakan:
    neckline diambil sebagai rata-rata 2 swing low, bukan garis miring
    penuh — cukup untuk proof-of-concept).

    Inverse H&S: kebalikannya, pakai swing low.
    """
    swing_highs, swing_lows = find_swing_points(df, order=order)
    last_close = df["close"].iloc[-1]
    result = {"detected": False, "pattern": None, "direction": None,
              "strength": 0.0, "details": {}}

    # --- Head and Shoulders (bearish) ---
    if len(swing_highs) >= 3:
        (iL, pL), (iH, pH), (iR, pR) = swing_highs[-3], swing_highs[-2], swing_highs[-1]
        if pH > pL and pH > pR and _pct_diff(pL, pR) <= shoulder_tolerance:
            head_prom_L = _pct_diff(pH, pL)
            head_prom_R = _pct_diff(pH, pR)
            if head_prom_L >= head_min_prominence and head_prom_R >= head_min_prominence:
                mid_lows = [(i, p) for (i, p) in swing_lows if iL < i < iR]
                width_ok = _segment_width_ratio_ok(iL, iH, iR)
                dominance = _max_single_candle_dominance(df, iL, iR)
                neck_p_candidate = np.mean([p for _, p in mid_lows]) if len(mid_lows) >= 2 else None
                # Syarat tambahan: kedua shoulder harus cukup jauh DI ATAS neckline
                # (bukan cuma head yang harus jauh di atas shoulder). Ini menolak
                # kasus dimana "neckline" cuma level chop dangkal pasca-pump
                # tunggal, bukan support yang benar-benar teruji dua kali.
                shoulders_above_neck_ok = (
                    neck_p_candidate is not None
                    and _pct_diff(pL, neck_p_candidate) >= head_min_prominence
                    and _pct_diff(pR, neck_p_candidate) >= head_min_prominence
                )
                if (len(mid_lows) >= 2 and width_ok
                        and dominance <= MAX_SINGLE_CANDLE_DOMINANCE
                        and shoulders_above_neck_ok):
                    neck_p = neck_p_candidate
                    breakout = last_close < neck_p
                    strength = min(1.0, (head_prom_L + head_prom_R) / 2 / 0.06)
                    result = {
                        "detected": bool(breakout),
                        "pattern": "Head and Shoulders",
                        "direction": "bearish",
                        "strength": round(strength, 2) if breakout else 0.0,
                        "details": {
                            "left_shoulder": pL, "head": pH, "right_shoulder": pR,
                            "neckline_price": neck_p,
                            "breakout_confirmed": breakout,
                        },
                    }
                    if breakout:
                        return result

    # --- Inverse Head and Shoulders (bullish) ---
    if len(swing_lows) >= 3:
        (iL, pL), (iH, pH), (iR, pR) = swing_lows[-3], swing_lows[-2], swing_lows[-1]
        if pH < pL and pH < pR and _pct_diff(pL, pR) <= shoulder_tolerance:
            head_prom_L = _pct_diff(pL, pH)
            head_prom_R = _pct_diff(pR, pH)
            if head_prom_L >= head_min_prominence and head_prom_R >= head_min_prominence:
                mid_highs = [(i, p) for (i, p) in swing_highs if iL < i < iR]
                width_ok = _segment_width_ratio_ok(iL, iH, iR)
                dominance = _max_single_candle_dominance(df, iL, iR)
                neck_p_candidate = np.mean([p for _, p in mid_highs]) if len(mid_highs) >= 2 else None
                shoulders_below_neck_ok = (
                    neck_p_candidate is not None
                    and _pct_diff(pL, neck_p_candidate) >= head_min_prominence
                    and _pct_diff(pR, neck_p_candidate) >= head_min_prominence
                )
                if (len(mid_highs) >= 2 and width_ok
                        and dominance <= MAX_SINGLE_CANDLE_DOMINANCE
                        and shoulders_below_neck_ok):
                    neck_p = neck_p_candidate
                    breakout = last_close > neck_p
                    strength = min(1.0, (head_prom_L + head_prom_R) / 2 / 0.06)
                    result = {
                        "detected": bool(breakout),
                        "pattern": "Inverse Head and Shoulders",
                        "direction": "bullish",
                        "strength": round(strength, 2) if breakout else 0.0,
                        "details": {
                            "left_shoulder": pL, "head": pH, "right_shoulder": pR,
                            "neckline_price": neck_p,
                            "breakout_confirmed": breakout,
                        },
                    }

    return result


# ---------------------------------------------------------------------------
# 4. TRIANGLES (Ascending, Descending, Symmetrical)
# ---------------------------------------------------------------------------

def detect_triangle(df: pd.DataFrame, order: int = 5, lookback_points: int = 4,
                     flat_tolerance: float = 0.005, min_slope_pct: float = 0.001):
    """
    Pakai regresi linear sederhana atas beberapa swing high & swing low
    terakhir untuk menentukan arah garis atas (resistance) dan garis bawah
    (support):
        - Ascending Triangle: resistance ~flat, support naik (higher lows)
        - Descending Triangle: support ~flat, resistance turun (lower highs)
        - Symmetrical Triangle: resistance turun DAN support naik (converging)

    Konfirmasi breakout: close terakhir keluar dari salah satu garis.
    """
    swing_highs, swing_lows = find_swing_points(df, order=order)
    last_close = df["close"].iloc[-1]
    result = {"detected": False, "pattern": None, "direction": None,
              "strength": 0.0, "details": {}}

    if len(swing_highs) < lookback_points or len(swing_lows) < lookback_points:
        return result

    highs_recent = swing_highs[-lookback_points:]
    lows_recent = swing_lows[-lookback_points:]

    hx = np.array([p[0] for p in highs_recent])
    hy = np.array([p[1] for p in highs_recent])
    lx = np.array([p[0] for p in lows_recent])
    ly = np.array([p[1] for p in lows_recent])

    # slope dinormalisasi terhadap harga rata-rata supaya persentase, bukan absolut
    avg_price = df["close"].mean()
    slope_high = np.polyfit(hx, hy, 1)[0] / avg_price
    slope_low = np.polyfit(lx, ly, 1)[0] / avg_price

    resistance_level = hy[-1]
    support_level = ly[-1]

    is_flat_high = abs(slope_high) <= flat_tolerance
    is_flat_low = abs(slope_low) <= flat_tolerance
    is_rising_low = slope_low >= min_slope_pct
    is_falling_high = slope_high <= -min_slope_pct

    pattern = None
    direction = None
    if is_flat_high and is_rising_low:
        pattern = "Ascending Triangle"
        direction = "bullish"
        breakout = last_close > resistance_level
    elif is_flat_low and is_falling_high:
        pattern = "Descending Triangle"
        direction = "bearish"
        breakout = last_close < support_level
    elif is_falling_high and is_rising_low:
        pattern = "Symmetrical Triangle"
        # arah breakout ditentukan oleh sisi mana yang ditembus
        if last_close > resistance_level:
            direction = "bullish"
            breakout = True
        elif last_close < support_level:
            direction = "bearish"
            breakout = True
        else:
            direction = None
            breakout = False
    else:
        breakout = False

    if pattern and breakout:
        strength = min(1.0, (abs(slope_high) + abs(slope_low)) / (2 * flat_tolerance * 4))
        result = {
            "detected": True,
            "pattern": pattern,
            "direction": direction,
            "strength": round(strength, 2),
            "details": {
                "resistance_level": resistance_level,
                "support_level": support_level,
                "slope_high_pct": slope_high,
                "slope_low_pct": slope_low,
            },
        }

    return result


# ---------------------------------------------------------------------------
# 5. WEDGES (Rising, Falling)
# ---------------------------------------------------------------------------

def detect_wedge(df: pd.DataFrame, order: int = 5, lookback_points: int = 4,
                  min_slope_pct: float = 0.001, convergence_ratio_max: float = 0.7):
    """
    Wedge mirip triangle tapi KEDUA garis bergerak ke arah yang SAMA
    (bukan konvergen dari arah berlawanan seperti symmetrical triangle):
        - Rising Wedge: support & resistance sama-sama naik, tapi resistance
          naik lebih landai (konvergen) -> biasanya BEARISH meski dalam uptrend
        - Falling Wedge: support & resistance sama-sama turun, support lebih
          landai -> biasanya BULLISH meski dalam downtrend

    convergence_ratio_max: rasio slope_resistance/slope_support (rising) atau
        sebaliknya (falling) harus < ini, supaya jelas konvergen bukan channel paralel.
    """
    swing_highs, swing_lows = find_swing_points(df, order=order)
    last_close = df["close"].iloc[-1]
    result = {"detected": False, "pattern": None, "direction": None,
              "strength": 0.0, "details": {}}

    if len(swing_highs) < lookback_points or len(swing_lows) < lookback_points:
        return result

    highs_recent = swing_highs[-lookback_points:]
    lows_recent = swing_lows[-lookback_points:]

    hx = np.array([p[0] for p in highs_recent])
    hy = np.array([p[1] for p in highs_recent])
    lx = np.array([p[0] for p in lows_recent])
    ly = np.array([p[1] for p in lows_recent])

    avg_price = df["close"].mean()
    slope_high = np.polyfit(hx, hy, 1)[0] / avg_price
    slope_low = np.polyfit(lx, ly, 1)[0] / avg_price

    resistance_level = hy[-1]
    support_level = ly[-1]

    pattern = None
    direction = None
    breakout = False

    # Rising Wedge: keduanya naik, tapi support naik lebih curam -> konvergen, bearish
    if slope_high >= min_slope_pct and slope_low >= min_slope_pct:
        if slope_high > 0 and (slope_high / slope_low) < convergence_ratio_max:
            pattern = "Rising Wedge"
            direction = "bearish"
            breakout = last_close < support_level

    # Falling Wedge: keduanya turun, tapi resistance turun lebih curam -> konvergen, bullish
    if slope_high <= -min_slope_pct and slope_low <= -min_slope_pct:
        if slope_low < 0 and (slope_low / slope_high) < convergence_ratio_max:
            pattern = "Falling Wedge"
            direction = "bullish"
            breakout = last_close > resistance_level

    if pattern and breakout:
        strength = min(1.0, (abs(slope_high) + abs(slope_low)) / (2 * min_slope_pct * 5))
        result = {
            "detected": True,
            "pattern": pattern,
            "direction": direction,
            "strength": round(strength, 2),
            "details": {
                "resistance_level": resistance_level,
                "support_level": support_level,
                "slope_high_pct": slope_high,
                "slope_low_pct": slope_low,
            },
        }

    return result


# ---------------------------------------------------------------------------
# 6. FLAG & PENNANT
# ---------------------------------------------------------------------------

def detect_flag_pennant(df: pd.DataFrame, pole_lookback: int = 20,
                         consolidation_lookback: int = 15,
                         pole_min_move: float = 0.05,
                         consolidation_max_range: float = 0.4):
    """
    Flag/Pennant: pergerakan tajam (pole) diikuti konsolidasi sempit.
    Pendekatan disederhanakan (bukan swing-based seperti pattern lain):
      1. Cek 'pole': apakah ada pergerakan >= pole_min_move (%) dalam
         pole_lookback candle sebelum window konsolidasi.
      2. Cek 'konsolidasi': apakah consolidation_lookback candle terakhir
         punya range (high-low) yang jauh lebih sempit dibanding pole
         (diukur consolidation_max_range = rasio range konsolidasi vs pole).
      3. Arah flag/pennant mengikuti arah pole (continuation pattern).

    Catatan: ini pendekatan paling kasar dari 6 pattern -- perlu validasi
    manual paling ketat saat testing.
    """
    total_needed = pole_lookback + consolidation_lookback
    result = {"detected": False, "pattern": None, "direction": None,
              "strength": 0.0, "details": {}}
    if len(df) < total_needed + 1:
        return result

    consolidation = df.iloc[-consolidation_lookback:]
    pole = df.iloc[-total_needed:-consolidation_lookback]

    pole_move = (pole["close"].iloc[-1] - pole["close"].iloc[0]) / pole["close"].iloc[0]
    pole_range = pole["high"].max() - pole["low"].min()
    consolidation_range = consolidation["high"].max() - consolidation["low"].min()

    if pole_range <= 0:
        return result

    range_ratio = consolidation_range / pole_range
    last_close = df["close"].iloc[-1]

    if abs(pole_move) >= pole_min_move and range_ratio <= consolidation_max_range:
        direction = "bullish" if pole_move > 0 else "bearish"
        # nama "Pennant" kalau konsolidasi mengerucut (range mengecil terus),
        # "Flag" kalau konsolidasi cenderung sejajar/menurun landai -- untuk
        # POC ini kita generalisasi sebagai "Flag/Pennant" saja dulu.
        breakout = (last_close > consolidation["high"].max() if direction == "bullish"
                    else last_close < consolidation["low"].min())
        if breakout:
            strength = min(1.0, abs(pole_move) / (pole_min_move * 3))
            result = {
                "detected": True,
                "pattern": "Flag/Pennant",
                "direction": direction,
                "strength": round(strength, 2),
                "details": {
                    "pole_move_pct": pole_move,
                    "consolidation_range_ratio": range_ratio,
                },
            }

    return result


# ---------------------------------------------------------------------------
# 7. AGGREGATOR — dipanggil dari indicators.py nanti (belum diintegrasi)
# ---------------------------------------------------------------------------

def detect_all_patterns(df: pd.DataFrame, order: int = 5):
    """
    Jalankan semua detector, kembalikan list hasil yang 'detected': True saja,
    diurutkan dari strength tertinggi. Dipakai nanti untuk confidence boost:
    ambil pattern dengan direction yang SAMA dengan arah sinyal (BUY/SELL),
    baru tambahkan bonus confidence (lihat catatan integrasi di test_patterns.py).
    """
    detectors = [
        detect_double_top_bottom,
        detect_head_and_shoulders,
        detect_triangle,
        detect_wedge,
        detect_flag_pennant,
    ]
    found = []
    for fn in detectors:
        try:
            r = fn(df, order=order) if fn is not detect_flag_pennant else fn(df)
            if r.get("detected"):
                found.append(r)
        except Exception as e:
            # Proof-of-concept: jangan biarkan 1 detector error mematikan yang lain
            found.append({"detected": False, "pattern": fn.__name__,
                          "direction": None, "strength": 0.0,
                          "details": {"error": str(e)}})
    found = [f for f in found if f.get("detected")]
    found.sort(key=lambda r: r["strength"], reverse=True)
    return found
