# ============================================================
#  market_context.py  – Konteks Market Global
#  Fitur:
#  1. Fear & Greed Index (alternative.me - gratis)
#  2. Funding Rate (Binance Futures - gratis)
#  3. BTC Trend Filter (blokir altcoin jika BTC downtrend)
# ============================================================
import time
import logging
import requests
import pandas as pd
from typing import Dict, Optional

logger = logging.getLogger(__name__)

TIMEOUT = 10

# ------------------------------------------------------------------
#  1. FEAR & GREED INDEX
# ------------------------------------------------------------------
_fg_cache: dict = {}
_fg_last_fetch: float = 0
FG_CACHE_TTL = 3600  # update tiap 1 jam

def get_fear_greed() -> dict:
    """
    Ambil Fear & Greed Index dari alternative.me (gratis, tanpa API key).
    Return: {
        "value"      : 72,
        "label"      : "Greed",
        "emoji"      : "😏",
        "signal"     : "CAUTION_BUY",   # implikasi trading
        "raw"        : {...}
    }
    """
    global _fg_cache, _fg_last_fetch

    now = time.time()
    if _fg_cache and (now - _fg_last_fetch) < FG_CACHE_TTL:
        return _fg_cache

    try:
        r = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=TIMEOUT
        )
        r.raise_for_status()
        data = r.json()["data"][0]

        value = int(data["value"])
        label = data["value_classification"]

        # Emoji & implikasi trading
        if value <= 20:
            emoji  = "😱"
            signal = "STRONG_BUY"       # Extreme Fear = peluang beli
            advice = "Extreme Fear — potensi bottom, pertimbangkan BUY"
        elif value <= 40:
            emoji  = "😰"
            signal = "BUY"              # Fear = pasar oversold
            advice = "Fear — pasar oversold, bias BUY"
        elif value <= 60:
            emoji  = "😐"
            signal = "NEUTRAL"
            advice = "Neutral — tidak ada bias kuat"
        elif value <= 80:
            emoji  = "😏"
            signal = "CAUTION_BUY"     # Greed = mulai hati-hati
            advice = "Greed — hati-hati, pasar mulai panas"
        else:
            emoji  = "🤑"
            signal = "CAUTION_SELL"    # Extreme Greed = potensi top
            advice = "Extreme Greed — potensi top, pertimbangkan SELL"

        _fg_cache = {
            "value" : value,
            "label" : label,
            "emoji" : emoji,
            "signal": signal,
            "advice": advice,
            "raw"   : data,
        }
        _fg_last_fetch = now
        logger.info(f"Fear & Greed: {value} ({label}) {emoji}")
        return _fg_cache

    except Exception as e:
        logger.warning(f"Fear & Greed fetch error: {e}")
        return {
            "value" : 50,
            "label" : "Neutral",
            "emoji" : "😐",
            "signal": "NEUTRAL",
            "advice": "Data tidak tersedia",
        }


# ------------------------------------------------------------------
#  2. FUNDING RATE (Binance Futures)
# ------------------------------------------------------------------
_fr_cache: Dict[str, dict] = {}
_fr_last_fetch: float = 0
FR_CACHE_TTL = 1800  # update tiap 30 menit

def get_funding_rates(symbols: list = None) -> Dict[str, dict]:
    """
    Ambil funding rate dari Gate.io Futures (gratis, tanpa API key).
    Funding rate positif  = long lebih banyak = potensi koreksi turun
    Funding rate negatif  = short lebih banyak = potensi short squeeze naik

    Return dict: {
        "BTCUSDT": {
            "rate"   : 0.0001,
            "pct"    : 0.01,       # dalam %
            "signal" : "NEUTRAL",
            "label"  : "Neutral",
            "emoji"  : "😐"
        }, ...
    }
    """
    global _fr_cache, _fr_last_fetch

    now = time.time()
    if _fr_cache and (now - _fr_last_fetch) < FR_CACHE_TTL:
        if symbols:
            return {s: _fr_cache[s] for s in symbols if s in _fr_cache}
        return _fr_cache

    try:
        r = requests.get(
            "https://api.gateio.ws/api/v4/futures/usdt/contracts",
            timeout=TIMEOUT
        )
        r.raise_for_status()
        data = r.json()

        result = {}
        for item in data:
            raw  = item.get("name", "")
            sym  = raw.replace("_", "").replace("/", "")
            rate = float(item.get("funding_rate", 0))
            pct  = round(rate * 100, 4)

            if pct > 0.05:
                signal = "BEARISH"      # terlalu banyak long = bahaya
                label  = "High Longs"
                emoji  = "🔴"
            elif pct > 0.01:
                signal = "CAUTION"
                label  = "Mild Longs"
                emoji  = "🟡"
            elif pct < -0.05:
                signal = "BULLISH"      # terlalu banyak short = short squeeze
                label  = "High Shorts"
                emoji  = "🟢"
            elif pct < -0.01:
                signal = "CAUTION"
                label  = "Mild Shorts"
                emoji  = "🟡"
            else:
                signal = "NEUTRAL"
                label  = "Neutral"
                emoji  = "😐"

            result[sym] = {
                "rate"  : rate,
                "pct"   : pct,
                "signal": signal,
                "label" : label,
                "emoji" : emoji,
            }

        _fr_cache = result
        _fr_last_fetch = now
        logger.info(f"Funding rate: {len(result)} pair dimuat")

        if symbols:
            return {s: result[s] for s in symbols if s in result}
        return result

    except Exception as e:
        logger.warning(f"Funding rate fetch error: {e}")
        return {}


def get_funding_rate(symbol: str) -> dict:
    """Ambil funding rate untuk 1 symbol saja."""
    # Normalisasi: BTCUSDT → BTCUSDT (Binance format)
    sym = symbol.upper().replace("_", "").replace("/", "")
    if not sym.endswith("USDT"):
        sym = sym + "USDT"
    rates = get_funding_rates()
    return rates.get(sym, {
        "rate"  : 0,
        "pct"   : 0,
        "signal": "NEUTRAL",
        "label" : "No Data",
        "emoji" : "❓",
    })


# ------------------------------------------------------------------
#  3. BTC TREND FILTER
# ------------------------------------------------------------------
_btc_trend_cache: dict = {}
_btc_trend_last_fetch: float = 0
BTC_TREND_TTL = 900  # update tiap 15 menit

def get_btc_trend() -> dict:
    """
    Analisis trend BTC dari Gate.io OHLCV.
    Digunakan untuk filter: jika BTC downtrend, blokir BUY altcoin.

    Return: {
        "trend"       : "UPTREND",     # UPTREND / DOWNTREND / SIDEWAYS
        "strength"    : "STRONG",      # STRONG / MODERATE / WEAK
        "allow_buy"   : True,          # izinkan BUY altcoin?
        "allow_sell"  : True,         # izinkan SELL altcoin?
        "emoji"       : "🟢",
        "advice"      : "BTC uptrend — BUY altcoin diizinkan",
        "ema50"       : 65000.0,
        "ema200"      : 60000.0,
        "price"       : 67000.0,
        "adx"         : 32.5,
    }
    """
    global _btc_trend_cache, _btc_trend_last_fetch

    now = time.time()
    if _btc_trend_cache and (now - _btc_trend_last_fetch) < BTC_TREND_TTL:
        return _btc_trend_cache

    try:
        from data_fetcher import fetch_ohlcv
        from indicators   import institutional_ai_v4

        df = fetch_ohlcv("BTCUSDT", "4h", limit=300)
        if df is None or len(df) < 200:
            raise ValueError("Data BTC tidak cukup")

        # Cast tipe data
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()

        df   = institutional_ai_v4(df)
        last = df.iloc[-1]

        price  = float(last["close"])
        ema50  = float(last.get("ema50",  0))
        ema200 = float(last.get("ema200", 0))
        ema20  = float(last.get("ema20",  0))
        adx    = float(last.get("adx",    0))

        # Tentukan trend
        if ema50 > ema200 and price > ema50:
            if adx > 25:
                trend    = "UPTREND"
                strength = "STRONG"
                emoji    = "🟢"
                allow_buy  = True
                allow_sell = True
                advice   = "BTC strong uptrend — BUY altcoin diizinkan penuh"
            else:
                trend    = "UPTREND"
                strength = "MODERATE"
                emoji    = "🟢"
                allow_buy  = True
                allow_sell = True
                advice   = "BTC uptrend moderat — BUY altcoin diizinkan"

        elif ema50 < ema200 and price < ema50:
            if adx > 25:
                trend    = "DOWNTREND"
                strength = "STRONG"
                emoji    = "🔴"
                allow_buy  = True    # BUY diizinkan semua kondisi
                allow_sell = True
                advice   = "BTC strong downtrend — BUY altcoin DIBLOKIR"
            else:
                trend    = "DOWNTREND"
                strength = "MODERATE"
                emoji    = "🔴"
                allow_buy  = True
                allow_sell = True
                advice   = "BTC downtrend — BUY altcoin DIBLOKIR"

        else:
            trend    = "SIDEWAYS"
            strength = "WEAK"
            emoji    = "🟡"
            allow_buy  = True     # sideways = izinkan tapi hati-hati
            allow_sell = True
            advice   = "BTC sideways — semua sinyal diizinkan, hati-hati"

        result = {
            "trend"     : trend,
            "strength"  : strength,
            "allow_buy" : allow_buy,
            "allow_sell": allow_sell,
            "emoji"     : emoji,
            "advice"    : advice,
            "ema50"     : round(ema50,  2),
            "ema200"    : round(ema200, 2),
            "price"     : round(price,  2),
            "adx"       : round(adx,    2),
        }

        _btc_trend_cache      = result
        _btc_trend_last_fetch = now
        logger.info(f"BTC Trend: {trend} ({strength}) | Price: {price:.2f} | ADX: {adx:.1f}")
        return result

    except Exception as e:
        import traceback; logger.warning(f"BTC trend fetch error: {e}\n{traceback.format_exc()}")
        return {
            "trend"     : "SIDEWAYS",
            "strength"  : "WEAK",
            "allow_buy" : True,
            "allow_sell": True,
            "emoji"     : "🟡",
            "advice"    : "Data BTC tidak tersedia, semua sinyal diizinkan",
            "ema50"     : 0,
            "ema200"    : 0,
            "price"     : 0,
            "adx"       : 0,
        }


# ------------------------------------------------------------------
#  4. CONTEXT SUMMARY (gabungan semua)
# ------------------------------------------------------------------
def get_market_context() -> dict:
    """
    Gabungkan semua konteks market dalam 1 fungsi.
    Dipanggil sekali sebelum scan untuk efisiensi.

    Return: {
        "fear_greed" : {...},
        "btc_trend"  : {...},
        "overall"    : "BULLISH" / "BEARISH" / "NEUTRAL",
        "allow_buy"  : True/False,
        "allow_sell" : True/False,
        "summary"    : "string ringkasan"
    }
    """
    fg  = get_fear_greed()
    btc = get_btc_trend()

    # Tentukan overall context
    fg_bullish  = fg["signal"] in ("STRONG_BUY", "BUY")
    fg_bearish  = fg["signal"] in ("CAUTION_SELL",)
    btc_up      = btc["trend"] == "UPTREND"
    btc_down    = btc["trend"] == "DOWNTREND"

    if btc_up and (fg_bullish or fg["signal"] == "NEUTRAL"):
        overall    = "BULLISH"
        allow_buy  = True
        allow_sell = True
    elif btc_down and (fg_bearish or fg["signal"] in ("CAUTION_BUY", "NEUTRAL")):
        overall    = "BEARISH"
        allow_buy  = False
        allow_sell = True
    elif btc_down:
        overall    = "BEARISH"
        allow_buy  = False
        allow_sell = True

    # Circuit breaker — BTC pump mendadak → blokir semua SELL baru
    btc_change = get_btc_change_pct()
    if btc_change >= 3.0:
        allow_sell = False
        logger.warning(f"🚨 CIRCUIT BREAKER: BTC pump {btc_change:.2f}% — SELL diblokir sementara")
    if btc_change <= -3.0:
        allow_buy = False
        logger.warning(f"⚠️ CIRCUIT BREAKER: BTC dump {btc_change:.2f}% — BUY diblokir sementara")
    else:
        overall    = "NEUTRAL"
        allow_buy  = True
        allow_sell = True

    summary = (
        f"BTC: {btc['emoji']} {btc['trend']} ({btc['strength']}) | "
        f"F&G: {fg['emoji']} {fg['value']} {fg['label']} | "
        f"Bias: {'✅ BUY OK' if allow_buy else '🚫 BUY BLOCKED'} / "
        f"{'✅ SELL OK' if allow_sell else '🚫 SELL BLOCKED'}"
    )

    logger.info(f"Market Context: {summary}")

    return {
        "fear_greed" : fg,
        "btc_trend"  : btc,
        "overall"    : overall,
        "allow_buy"  : allow_buy,
        "allow_sell" : allow_sell,
        "summary"    : summary,
    }

def get_btc_change_pct() -> float:
    """Ambil perubahan harga BTC 1 jam terakhir dari Gate.io."""
    try:
        r = requests.get(
            "https://api.gateio.ws/api/v4/spot/candlesticks",
            params={"currency_pair": "BTC_USDT", "interval": "1h", "limit": 2},
            timeout=10
        )
        r.raise_for_status()
        rows = r.json()
        if len(rows) >= 2:
            prev_close = float(rows[-2][2])
            curr_close = float(rows[-1][2])
            return ((curr_close - prev_close) / prev_close) * 100
    except Exception as e:
        logger.warning(f"btc_change error: {e}")
    return 0.0

def is_btc_dump(threshold: float = -3.0) -> bool:
    """Return True jika BTC turun lebih dari threshold% dalam 1 jam."""
    change = get_btc_change_pct()
    if change <= threshold:
        logger.warning(f"⚠️ BTC DUMP terdeteksi: {change:.2f}% — BUY altcoin diblokir sementara")
        return True
    return False

def is_btc_pump(threshold: float = 3.0) -> bool:
    """Return True jika BTC naik lebih dari threshold% dalam 1 jam — circuit breaker SELL."""
    change = get_btc_change_pct()
    if change >= threshold:
        logger.warning(f"🚨 BTC PUMP terdeteksi: {change:.2f}% — SELL altcoin diblokir sementara")
        return True
    return False

# ==============================================================
#  MARKET REGIME DETECTION — per pair & global
# ==============================================================
_regime_cache: dict = {}
_regime_cache_ttl = 600  # 10 menit

def detect_market_regime(symbol: str, timeframe: str = "1h") -> dict:
    """
    Deteksi regime market untuk 1 pair:
    - TRENDING   : ADX > 25, harga jauh dari BB middle
    - RANGING    : ADX < 20, harga bolak-balik di BB
    - BREAKOUT   : Volume spike + harga tembus BB upper/lower
    - VOLATILE   : ATR tinggi relative to price
    """
    import time
    cache_key = f"{symbol}_{timeframe}"
    now = time.time()

    if cache_key in _regime_cache:
        ts, result = _regime_cache[cache_key]
        if now - ts < _regime_cache_ttl:
            return result

    try:
        from data_fetcher import fetch_ohlcv
        from indicators   import institutional_ai_v4
        import pandas as pd

        df = fetch_ohlcv(symbol, timeframe, limit=100)
        if df is None or len(df) < 50:
            raise ValueError("Data tidak cukup")

        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()
        df = institutional_ai_v4(df)
        last = df.iloc[-1]

        adx        = float(last.get("adx", 0))
        atr        = float(last.get("atr", 0))
        price      = float(last["close"])
        bb_upper   = float(last.get("bb_upper", price))
        bb_lower   = float(last.get("bb_lower", price))
        bb_middle  = float(last.get("bb_mid", price))
        vol_ratio  = float(last.get("volume_ratio", 1.0))
        atr_pct    = (atr / price * 100) if price > 0 else 0
        bb_width   = (bb_upper - bb_lower) / bb_middle * 100 if bb_middle > 0 else 0

        # Deteksi regime
        if vol_ratio > 2.0 and (price > bb_upper or price < bb_lower):
            regime   = "BREAKOUT"
            emoji    = "🚀"
            advice   = "Volume spike + harga tembus BB — momentum kuat"
            bias_buy  = price > bb_upper
            bias_sell = price < bb_lower

        elif adx > 25 and bb_width > 3.0:
            regime   = "TRENDING"
            emoji    = "📈" if price > bb_middle else "📉"
            advice   = f"ADX={adx:.1f} — trend kuat, ikuti arah"
            bias_buy  = price > bb_middle
            bias_sell = price < bb_middle

        elif adx < 20 and bb_width < 2.0:
            regime   = "RANGING"
            emoji    = "↔️"
            advice   = f"ADX={adx:.1f} — market sideways, hati-hati false signal"
            bias_buy  = price < bb_middle
            bias_sell = price > bb_middle

        elif atr_pct > 3.0:
            regime   = "VOLATILE"
            emoji    = "⚡"
            advice   = f"ATR={atr_pct:.1f}% — volatilitas tinggi, perkecil posisi"
            bias_buy  = False
            bias_sell = False

        else:
            regime   = "NEUTRAL"
            emoji    = "➡️"
            advice   = "Tidak ada regime dominan"
            bias_buy  = True
            bias_sell = True

        result = {
            "regime"    : regime,
            "emoji"     : emoji,
            "advice"    : advice,
            "adx"       : round(adx, 1),
            "atr_pct"   : round(atr_pct, 2),
            "bb_width"  : round(bb_width, 2),
            "vol_ratio" : round(vol_ratio, 2),
            "bias_buy"  : bias_buy,
            "bias_sell" : bias_sell,
        }

        _regime_cache[cache_key] = (now, result)
        return result

    except Exception as e:
        return {
            "regime"   : "UNKNOWN",
            "emoji"    : "❓",
            "advice"   : f"Error: {e}",
            "adx"      : 0, "atr_pct": 0, "bb_width": 0, "vol_ratio": 0,
            "bias_buy" : True, "bias_sell": True,
        }


def get_global_regime(symbols: list = None, timeframe: str = "1h") -> dict:
    """Regime agregat dari beberapa pair — gambaran market secara keseluruhan."""
    from config import WATCHLIST
    if symbols is None:
        symbols = WATCHLIST[:20]

    counts = {"TRENDING": 0, "RANGING": 0, "BREAKOUT": 0, "VOLATILE": 0, "NEUTRAL": 0, "UNKNOWN": 0}

    for sym in symbols:
        r = detect_market_regime(sym, timeframe)
        counts[r["regime"]] = counts.get(r["regime"], 0) + 1

    total    = len(symbols)
    dominant = max(counts, key=counts.get)
    pct      = round(counts[dominant] / total * 100, 1)

    emoji_map = {"TRENDING":"📈","RANGING":"↔️","BREAKOUT":"🚀","VOLATILE":"⚡","NEUTRAL":"➡️","UNKNOWN":"❓"}

    return {
        "dominant"  : dominant,
        "emoji"     : emoji_map.get(dominant, "❓"),
        "pct"       : pct,
        "counts"    : counts,
        "summary"   : f"{emoji_map.get(dominant,'❓')} {dominant} ({pct}% dari {total} pair)",
    }
