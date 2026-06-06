# ============================================================
#  data_fetcher.py  – Gate.io + CMC + New Listing Detection
# ============================================================
import time
import logging
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

GATE_KLINES = "https://api.gateio.ws/api/v4/spot/candlesticks"
GATE_INFO   = "https://api.gateio.ws/api/v4/spot/tickers"

CMC_API_KEY = "80fcb8071c08424098840bd02df5f0c9"
CMC_LATEST  = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"

INTERVAL_GATE = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d"}
TIMEOUT       = 30

_gate_symbols: set = set()


# ------------------------------------------------------------------
#  Gate.io Symbol Loader
# ------------------------------------------------------------------
def _load_gate_symbols() -> set:
    global _gate_symbols
    if _gate_symbols:
        return _gate_symbols
    try:
        r = requests.get(GATE_INFO, timeout=TIMEOUT)
        r.raise_for_status()
        _gate_symbols = {item["currency_pair"] for item in r.json()}
        logger.info(f"Gate.io: {len(_gate_symbols)} simbol aktif")
    except Exception as e:
        logger.warning(f"Gagal load Gate.io symbols: {e}")
    return _gate_symbols


def _to_gate_symbol(symbol: str) -> str:
    sym = symbol.upper().replace("/", "")
    if "_" in sym:
        return sym
    if sym.endswith("USDT"):
        return sym[:-4] + "_USDT"
    if sym.endswith("USDC"):
        return sym[:-4] + "_USDC"
    if sym.endswith("BTC"):
        return sym[:-3] + "_BTC"
    if sym.endswith("ETH"):
        return sym[:-3] + "_ETH"
    return sym + "_USDT"


# ------------------------------------------------------------------
#  OHLCV Fetcher (fungsi utama)
# ------------------------------------------------------------------
def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 300):
    sym      = _to_gate_symbol(symbol)
    interval = INTERVAL_GATE.get(timeframe, "1h")

    valid = _load_gate_symbols()
    if valid and sym not in valid:
        logger.debug(f"Simbol tidak ada di Gate.io: {sym}")
        return None

    try:
        r = requests.get(
            GATE_KLINES,
            params={"currency_pair": sym, "interval": interval, "limit": limit},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        rows = r.json()

        if not rows or isinstance(rows, dict):
            return None

        # Format Gate.io (8 kolom):
        # [timestamp, volume_quote, close, high, low, open, volume_base, is_closed]
        df = pd.DataFrame(rows, columns=[
            "timestamp", "volume_quote", "close", "high", "low", "open",
            "volume", "is_closed"
        ])
        # Filter: buang candle terakhir jika belum closed
        if "is_closed" in df.columns:
            last_closed = df["is_closed"].iloc[-1]
            if str(last_closed) in ("0", "False", "false"):
                df = df.iloc[:-1]  # buang candle yang masih berjalan

        df = df[["open", "high", "low", "close", "volume"]].astype(float)

        return df if len(df) >= 30 else None

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout Gate.io: {sym}/{timeframe}")
        return None
    except Exception as e:
        logger.debug(f"Gate.io error {sym}/{timeframe}: {e}")
        return None


# ------------------------------------------------------------------
#  CMC Data
# ------------------------------------------------------------------
_cmc_cache     : dict  = {}
_cmc_last_fetch: float = 0
CMC_CACHE_TTL  = 3600


def _fetch_cmc_data() -> dict:
    global _cmc_cache, _cmc_last_fetch
    if not CMC_API_KEY:
        return {}
    now = time.time()
    if _cmc_cache and (now - _cmc_last_fetch) < CMC_CACHE_TTL:
        return _cmc_cache
    try:
        r = requests.get(
            CMC_LATEST,
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"limit": 200, "convert": "USDT"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        _cmc_cache = {
            item["symbol"]: {
                "rank"      : item["cmc_rank"],
                "market_cap": item["quote"]["USDT"]["market_cap"],
                "change_24h": item["quote"]["USDT"]["percent_change_24h"],
                "volume_24h": item["quote"]["USDT"]["volume_24h"],
            }
            for item in data
        }
        _cmc_last_fetch = now
        logger.info(f"CMC: {len(_cmc_cache)} coin dimuat")
    except Exception as e:
        logger.warning(f"CMC fetch error: {e}")
    return _cmc_cache


def get_cmc_info(symbol: str) -> dict:
    base = symbol.upper()
    for suffix in ["_USDT", "_BTC", "_ETH", "USDT", "BTC", "ETH"]:
        base = base.replace(suffix, "")
    return _fetch_cmc_data().get(base, {})


# ------------------------------------------------------------------
#  New Listing Detection
# ------------------------------------------------------------------
_known_symbols        : set   = set()
_new_listing_cache    : list  = []
_new_listing_last_check: float = 0
NEW_LISTING_CHECK_INTERVAL = 3600  # cek setiap 1 jam


def fetch_symbols(min_volume_usdt: float = 500000) -> list:
    """
    Ambil semua pair USDT aktif dari Gate.io.
    Filter volume minimum agar tidak ambil pair zombie.
    """
    global _known_symbols, _new_listing_cache, _new_listing_last_check

    now = time.time()
    if _new_listing_cache and (now - _new_listing_last_check) < NEW_LISTING_CHECK_INTERVAL:
        return _new_listing_cache

    try:
        r = requests.get(GATE_INFO, timeout=TIMEOUT)
        r.raise_for_status()
        tickers = r.json()

        all_pairs = []
        new_pairs = []

        for item in tickers:
            pair = item.get("currency_pair", "")
            if not pair.endswith("_USDT"):
                continue
            try:
                vol_24h = float(item.get("quote_volume", 0))
            except (ValueError, TypeError):
                vol_24h = 0
            if vol_24h < min_volume_usdt:
                continue

            symbol = pair.replace("_", "")
            all_pairs.append((symbol, vol_24h))

            if _known_symbols and symbol not in _known_symbols:
                new_pairs.append(symbol)
                logger.info(f"🆕 New listing terdeteksi: {symbol} | Vol 24h: ${vol_24h:,.0f}")

        # Sort by volume descending — pair paling likuid duluan
        all_pairs.sort(key=lambda x: x[1], reverse=True)
        all_pairs = [s for s, v in all_pairs]

        if all_pairs:
            _known_symbols = set(all_pairs)

        if new_pairs:
            logger.info(f"🆕 Total {len(new_pairs)} pair baru: {new_pairs[:10]}")
        else:
            logger.info(f"Gate.io: {len(all_pairs)} pair aktif, tidak ada listing baru")

        _new_listing_cache = all_pairs
        _new_listing_last_check = now
        return all_pairs

    except Exception as e:
        logger.warning(f"fetch_symbols error: {e}")
        return _new_listing_cache if _new_listing_cache else []

def get_top_gainers_losers(top_n: int = 10) -> tuple:
    """Ambil top gainer dan top loser dari Gate.io."""
    try:
        r = requests.get(
            "https://api.gateio.ws/api/v4/spot/tickers",
            timeout=10
        )
        r.raise_for_status()
        tickers = r.json()

        pairs = []
        for item in tickers:
            pair = item.get("currency_pair", "")
            if not pair.endswith("_USDT"):
                continue
            try:
                vol    = float(item.get("quote_volume", 0))
                change = float(item.get("change_percentage", 0))
            except:
                continue
            if vol < 500000:
                continue
            symbol = pair.replace("_", "")
            pairs.append((symbol, change, vol))

        pairs.sort(key=lambda x: x[1], reverse=True)
        gainers = [s for s, c, v in pairs[:top_n] if c > 3]
        losers  = [s for s, c, v in pairs[-top_n:] if c < -3]

        logger.info(f"Top gainers: {gainers[:5]}")
        logger.info(f"Top losers: {losers[:5]}")
        return gainers, losers

    except Exception as e:
        logger.warning(f"get_top_gainers_losers error: {e}")
        return [], []


def get_volume_spike_pairs(top_n: int = 30) -> list:
    """Ambil pair dengan volume spike tertinggi dari Gate.io."""
    try:
        r = requests.get(
            "https://api.gateio.ws/api/v4/spot/tickers",
            timeout=10
        )
        r.raise_for_status()
        tickers = r.json()

        spikes = []
        for item in tickers:
            pair = item.get("currency_pair", "")
            if not pair.endswith("_USDT"):
                continue
            try:
                vol = float(item.get("quote_volume", 0))
                change = abs(float(item.get("change_percentage", 0)))
            except:
                continue
            if vol < 500000:
                continue
            # Score = volume × perubahan harga
            spike_score = vol * change
            spikes.append((pair.replace("_", ""), spike_score))

        spikes.sort(key=lambda x: x[1], reverse=True)
        result = [s for s, _ in spikes[:top_n]]
        logger.info(f"Volume spike pairs: {result[:5]}")
        return result
    except Exception as e:
        logger.warning(f"get_volume_spike_pairs error: {e}")
        return []

    except Exception as e:
        logger.warning(f"fetch_symbols gagal: {e}")
        return _new_listing_cache if _new_listing_cache else []


def get_new_listings(min_volume_usdt: float = 500000) -> list:
    """Return hanya pair yang BARU listing sejak bot terakhir jalan."""
    global _known_symbols

    if not _known_symbols:
        fetch_symbols(min_volume_usdt)
        return []

    try:
        r = requests.get(GATE_INFO, timeout=TIMEOUT)
        r.raise_for_status()
        tickers = r.json()

        new_pairs = []
        for item in tickers:
            pair = item.get("currency_pair", "")
            if not pair.endswith("_USDT"):
                continue
            try:
                vol_24h = float(item.get("quote_volume", 0))
            except (ValueError, TypeError):
                vol_24h = 0
            if vol_24h < min_volume_usdt:
                continue

            symbol = pair.replace("_", "")
            if symbol not in _known_symbols:
                new_pairs.append(symbol)
                logger.info(f"🆕 New listing: {symbol} | Vol: ${vol_24h:,.0f}")

        return new_pairs

    except Exception as e:
        logger.warning(f"get_new_listings gagal: {e}")
        return []


# ------------------------------------------------------------------
#  Batch Fetcher
# ------------------------------------------------------------------
def fetch_batch(symbols: list, timeframe: str, delay: float = 0.3) -> dict:
    result = {}

    def _fetch(sym):
        return sym, fetch_ohlcv(sym, timeframe)

    with ThreadPoolExecutor(max_workers=10) as exe:
        for sym, df in exe.map(_fetch, symbols):
            if df is not None:
                result[sym] = df

    logger.info(f"[{timeframe}] {len(result)}/{len(symbols)} pair berhasil")
    return result

# ==============================================================
#  ASYNC UPGRADE — aiohttp native (drop-in async fetch_ohlcv)
# ==============================================================
import asyncio
import aiohttp

_async_session: aiohttp.ClientSession = None

async def _get_session() -> aiohttp.ClientSession:
    global _async_session
    if _async_session is None or _async_session.closed:
        connector = aiohttp.TCPConnector(limit=5, ttl_dns_cache=300)
        timeout   = aiohttp.ClientTimeout(total=TIMEOUT)
        _async_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _async_session

async def async_fetch_ohlcv(symbol: str, timeframe: str, limit: int = 300):
    """Versi async fetch_ohlcv — pakai aiohttp, ~10x lebih cepat untuk bulk scan."""
    sym      = _to_gate_symbol(symbol)
    interval = INTERVAL_GATE.get(timeframe, "1h")

    valid = _load_gate_symbols()
    if valid and sym not in valid:
        logger.debug(f"Simbol tidak ada di Gate.io: {sym}")
        return None

    try:
        session = await _get_session()
        params  = {"currency_pair": sym, "interval": interval, "limit": limit}
        async with session.get(GATE_KLINES, params=params) as r:
            r.raise_for_status()
            rows = await r.json()

        if not rows or isinstance(rows, dict):
            return None

        df = pd.DataFrame(rows, columns=[
            "timestamp", "volume_quote", "close", "high", "low", "open",
            "volume", "is_closed"
        ])
        if "is_closed" in df.columns:
            if str(df["is_closed"].iloc[-1]) in ("0", "False", "false"):
                df = df.iloc[:-1]

        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        return df if len(df) >= 30 else None

    except asyncio.TimeoutError:
        logger.warning(f"Timeout Gate.io async: {sym}/{timeframe}")
        return None
    except Exception as e:
        logger.debug(f"Gate.io async error {sym}/{timeframe}: {e}")
        return None

async def close_async_session():
    global _async_session
    if _async_session and not _async_session.closed:
        await _async_session.close()
        _async_session = None
