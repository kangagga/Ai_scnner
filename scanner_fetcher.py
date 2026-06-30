"""
scanner/fetcher.py — fetch, cache, rate limit
"""
import logging
import time
import random
import threading
from typing import Dict, Optional

import numpy as np
import pandas as pd

from data_fetcher import fetch_ohlcv

logger = logging.getLogger(__name__)

MAX_RETRIES        = 3
BASE_DELAY         = 1.5
RATE_LIMIT_PER_SEC = 2
CACHE_TTL_SEC      = 600

_fetch_cache: Dict[str, tuple]           = {}
_cache_lock                               = threading.Lock()
_indicator_cache: Dict[str, pd.DataFrame] = {}
_rate_limit_lock                          = threading.Lock()
_last_request_time: Dict[int, float]      = {}


def cast_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close", "volume"])


def safe_float(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        return default if (np.isnan(v) or np.isinf(v)) else v
    except Exception:
        return default


def apply_rate_limit() -> None:
    min_interval = 1.0 / RATE_LIMIT_PER_SEC
    with _rate_limit_lock:
        last    = _last_request_time.get(threading.get_ident(), 0)
        elapsed = time.time() - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_request_time[threading.get_ident()] = time.time()


def cached_fetch(symbol: str, timeframe: str, limit: int = 300) -> Optional[pd.DataFrame]:
    key = f"{symbol}_{timeframe}_{limit}"
    now = time.time()
    with _cache_lock:
        if key in _fetch_cache:
            ts, df = _fetch_cache[key]
            if now - ts < CACHE_TTL_SEC:
                return df
        _fetch_cache.pop(key, None)
    df = fetch_ohlcv(symbol, timeframe, limit=limit)
    if df is not None:
        with _cache_lock:
            _fetch_cache[key] = (now, df.copy())
    return df


def fetch_with_retry(symbol: str, timeframe: str, limit: int = 300) -> Optional[pd.DataFrame]:
    for attempt in range(MAX_RETRIES):
        try:
            df = cached_fetch(symbol, timeframe, limit)
            if df is not None and len(df) >= limit * 0.8:
                return df
        except Exception as e:
            logger.warning(f"Fetch gagal {symbol}/{timeframe} attempt {attempt+1}: {e}")
        time.sleep(BASE_DELAY * (attempt + 1) + random.uniform(0, 1))
    return None


def get_indicator_cache(key: str) -> Optional[pd.DataFrame]:
    return _indicator_cache.get(key)


def set_indicator_cache(key: str, df: pd.DataFrame, max_size: int = 300) -> None:
    _indicator_cache[key] = df
    if len(_indicator_cache) > max_size:
        del _indicator_cache[next(iter(_indicator_cache))]


def clear_fetch_cache() -> None:
    with _cache_lock:
        _fetch_cache.clear()
    _indicator_cache.clear()
    logger.info("[FETCHER] Cache dibersihkan")
