"""
Centralized logging configuration
Import di main.py sebelum modul lain
"""
import logging
import logging.handlers
import os
from datetime import datetime

LOG_DIR  = "logs"
LOG_FILE = os.path.join(LOG_DIR, "bot.log")

def setup_logging(level=logging.INFO) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter(
        fmt     = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt = "%Y-%m-%d %H:%M:%S"
    )

    # ── Root logger ──
    root = logging.getLogger()
    root.setLevel(level)

    # Hindari duplicate handler jika dipanggil 2x
    if root.handlers:
        return

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File handler — rotate setiap 5MB, simpan 3 backup
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5*1024*1024, backupCount=3,
        encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Silence noisy libs
    for lib in ["urllib3","requests","httpx","aiohttp","schedule"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

    logging.info(f"Logging initialized → {LOG_FILE}")

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
