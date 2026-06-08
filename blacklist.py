# ============================================================
#  blacklist.py — Auto-blacklist pair yang sering false signal
# ============================================================
import json
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
BLACKLIST_FILE = "blacklist.json"
MAX_FALSE_SIGNALS = 2      # blacklist setelah 2x false signal
BLACKLIST_DURATION = 24    # jam
LOSS_COOLDOWN_HOURS = 2    # cooldown setelah 1x loss

def _load() -> dict:
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE) as f:
            return json.load(f)
    return {"blacklist": {}, "false_signals": {}}

def _save(data: dict):
    with open(BLACKLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_blacklisted(symbol: str) -> bool:
    data = _load()
    bl = data["blacklist"].get(symbol)
    if not bl:
        return False
    until = datetime.fromisoformat(bl["until"])
    if datetime.now() > until:
        del data["blacklist"][symbol]
        _save(data)
        return False
    return True

def report_false_signal(symbol: str):
    data = _load()
    fs = data["false_signals"]
    now = datetime.now()
    if symbol not in fs:
        fs[symbol] = {"count": 0, "last": now.isoformat()}
    fs[symbol]["count"] += 1
    fs[symbol]["last"] = now.isoformat()

    if fs[symbol]["count"] >= MAX_FALSE_SIGNALS:
        until = (now + timedelta(hours=BLACKLIST_DURATION)).isoformat()
        data["blacklist"][symbol] = {"until": until, "reason": "false_signal"}
        fs[symbol]["count"] = 0
        logger.warning(f"⛔ {symbol} di-blacklist selama {BLACKLIST_DURATION} jam")

    _save(data)

def add_loss_cooldown(symbol: str):
    """Tambah cooldown 2 jam setelah 1x loss."""
    from datetime import datetime, timedelta, timezone
    data = _load()
    now = datetime.now(timezone.utc)
    until = (now + timedelta(hours=LOSS_COOLDOWN_HOURS)).isoformat()
    data["blacklist"][symbol + "_cooldown"] = {"until": until, "reason": "loss_cooldown"}
    _save(data)
    logger.info(f"⏳ {symbol} cooldown {LOSS_COOLDOWN_HOURS} jam setelah loss")

def is_in_cooldown(symbol: str) -> bool:
    """Cek apakah pair sedang dalam cooldown loss."""
    from datetime import datetime, timezone
    data = _load()
    key = symbol + "_cooldown"
    cd = data["blacklist"].get(key)
    if not cd:
        return False
    now = datetime.now(timezone.utc)
    until = datetime.fromisoformat(cd["until"])
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if now >= until:
        del data["blacklist"][key]
        _save(data)
        return False
    return True

def get_blacklist() -> list:
    data = _load()
    return list(data["blacklist"].keys())
