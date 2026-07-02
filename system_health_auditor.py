#!/usr/bin/env python3
"""
system_health_auditor.py — LAPIS 1: HEALTH CHECK HARIAN

Audit kesehatan sistem (bukan performa trading — itu sudah dicover bot_auditor.py).
Modul ini READ-ONLY terhadap proses lain: hanya membaca file/proses/DB,
tidak pernah mengubah logic trading/scanning.

Cek yang dilakukan:
  1. Duplicate process detection — lebih dari 1 instance main.py jalan bersamaan
  2. Log health — ukuran file + jumlah error/warning per jenis, 24 jam terakhir
  3. Database integrity — PRAGMA integrity_check tiap .db, ukuran wajar
  4. System resources — CPU, RAM, disk usage milik proses bot
  5. Process uptime — sejak kapan PID bot start (deteksi crash+restart)
  6. Signal-to-trade ratio — rasio sinyal masuk vs trade yang benar2 dibuka

Dipanggil dari main.py via scheduler `schedule`, terpisah dari job_health_check
yang sudah ada (yang itu untuk audit performa trading via bot_auditor.py).

Tidak menambah dependency baru selain `psutil` (sudah terinstall di project).
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import psutil

logger = logging.getLogger("system_health_auditor")

# ── Konfigurasi ──────────────────────────────────────────────────────────────
WIB = timezone(timedelta(hours=7))
BASE_DIR = Path(__file__).resolve().parent

# File log yang dipantau ukurannya
LOG_FILES = {
    "signal_bot.log": BASE_DIR / "signal_bot.log",
    "main_output.log": BASE_DIR / "main_output.log",
    "bot.log": BASE_DIR / "bot.log",
}

# Threshold ukuran log (MB) sebelum dianggap abnormal/perlu rotasi
LOG_SIZE_WARN_MB = 50
LOG_SIZE_CRITICAL_MB = 150

# Database yang dicek integritasnya
DB_FILES = [
    "bot.db", "brain_memory.db", "signals.db", "trades.db",
    "trading_bot.db", "virtual_trades.db", "virtual_trading.db",
]

# Threshold ukuran DB (MB) sebelum dianggap abnormal
DB_SIZE_WARN_MB = 200

# Threshold resource proses bot
CPU_WARN_PCT = 80.0
RAM_WARN_MB = 1024  # 1 GB

# Nama script utama untuk deteksi duplicate process
MAIN_SCRIPT_NAME = "main.py"


# ═══════════════════════════════════════════════════════════════════════════
# 1. DUPLICATE PROCESS DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def check_duplicate_process() -> Dict[str, Any]:
    """
    Cari semua proses python yang menjalankan main.py.
    Lebih dari 1 instance = kemungkinan duplicate run yang bisa menyebabkan
    race condition di database, double-trade, atau double-notif Telegram.
    """
    matches: List[Dict[str, Any]] = []
    try:
        for proc in psutil.process_iter(["pid", "cmdline", "create_time"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                cmdline_str = " ".join(cmdline)
                if MAIN_SCRIPT_NAME in cmdline_str and "system_health_auditor" not in cmdline_str:
                    matches.append({
                        "pid": proc.info["pid"],
                        "create_time": proc.info["create_time"],
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.warning(f"[HEALTH] check_duplicate_process error: {e}")
        return {"status": "error", "message": str(e), "count": 0}

    count = len(matches)
    is_duplicate = count > 1

    return {
        "status": "CRITICAL" if is_duplicate else "OK",
        "count": count,
        "pids": [m["pid"] for m in matches],
        "message": (
            f"Ditemukan {count} instance main.py berjalan bersamaan! "
            f"PID: {[m['pid'] for m in matches]}"
            if is_duplicate else f"Normal — 1 instance berjalan (PID {matches[0]['pid']})"
            if matches else "Tidak ada instance main.py terdeteksi berjalan"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. LOG HEALTH — UKURAN + ERROR COUNT PER JENIS
# ═══════════════════════════════════════════════════════════════════════════

def check_log_health() -> Dict[str, Any]:
    """
    Cek ukuran file log (deteksi pembengkakan abnormal yang butuh rotasi)
    dan hitung jumlah error/warning per jenis dalam 24 jam terakhir.
    """
    result: Dict[str, Any] = {"files": {}, "issues": []}
    cutoff = datetime.now(WIB) - timedelta(hours=24)
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    yesterday_str = (datetime.now(WIB) - timedelta(days=1)).strftime("%Y-%m-%d")

    for name, path in LOG_FILES.items():
        if not path.exists():
            result["files"][name] = {"status": "MISSING", "size_mb": 0}
            continue

        size_mb = round(path.stat().st_size / (1024 * 1024), 2)
        status = "OK"
        if size_mb >= LOG_SIZE_CRITICAL_MB:
            status = "CRITICAL"
            result["issues"].append(f"{name} membengkak: {size_mb}MB (>{LOG_SIZE_CRITICAL_MB}MB)")
        elif size_mb >= LOG_SIZE_WARN_MB:
            status = "WARNING"
            result["issues"].append(f"{name} cukup besar: {size_mb}MB (>{LOG_SIZE_WARN_MB}MB)")

        # Hitung error/warning per jenis — hanya baca tail untuk file besar (hemat memori)
        error_breakdown = {"ERROR": 0, "WARNING": 0, "Traceback": 0, "Exception": 0}
        try:
            # Baca maksimal 5000 baris terakhir untuk efisiensi pada file besar
            with open(path, "r", errors="ignore") as f:
                lines = f.readlines()[-5000:]

            for line in lines:
                if today_str not in line and yesterday_str not in line:
                    continue
                if "[ERROR]" in line or " ERROR " in line:
                    error_breakdown["ERROR"] += 1
                if "[WARNING]" in line or " WARNING " in line:
                    error_breakdown["WARNING"] += 1
                if "Traceback" in line:
                    error_breakdown["Traceback"] += 1
                if "Exception" in line:
                    error_breakdown["Exception"] += 1
        except Exception as e:
            error_breakdown = {"read_error": str(e)}

        result["files"][name] = {
            "status": status,
            "size_mb": size_mb,
            "error_breakdown": error_breakdown,
        }

        if isinstance(error_breakdown, dict) and error_breakdown.get("ERROR", 0) > 20:
            result["issues"].append(
                f"{name}: {error_breakdown['ERROR']} ERROR dalam 24 jam terakhir"
            )

    result["status"] = "CRITICAL" if any("CRITICAL" in i or "membengkak" in i for i in result["issues"]) \
        else ("WARNING" if result["issues"] else "OK")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 3. DATABASE INTEGRITY CHECK
# ═══════════════════════════════════════════════════════════════════════════

def check_database_integrity() -> Dict[str, Any]:
    """
    Jalankan PRAGMA integrity_check pada tiap database SQLite,
    dan cek ukuran file tidak abnormal (kosong/0 byte atau terlalu besar).
    """
    result: Dict[str, Any] = {"databases": {}, "issues": []}

    for db_name in DB_FILES:
        db_path = BASE_DIR / db_name
        if not db_path.exists():
            result["databases"][db_name] = {"status": "MISSING"}
            continue

        size_mb = round(db_path.stat().st_size / (1024 * 1024), 3)

        if db_path.stat().st_size == 0:
            result["databases"][db_name] = {"status": "EMPTY", "size_mb": 0}
            # File 0 byte mungkin memang belum dipakai (mis. trades.db, trading_bot.db
            # yang terlihat tidak aktif di project ini) — tidak otomatis jadi issue,
            # cukup dicatat statusnya.
            continue

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check(1)")
            check_result = cur.fetchone()[0]
            conn.close()

            is_ok = check_result == "ok"
            status = "OK" if is_ok else "CORRUPT"

            result["databases"][db_name] = {
                "status": status,
                "size_mb": size_mb,
                "integrity_check": check_result,
            }

            if not is_ok:
                result["issues"].append(f"{db_name}: integrity_check GAGAL — {check_result}")
            if size_mb > DB_SIZE_WARN_MB:
                result["issues"].append(f"{db_name}: ukuran besar {size_mb}MB (>{DB_SIZE_WARN_MB}MB)")

        except Exception as e:
            result["databases"][db_name] = {"status": "ERROR", "message": str(e)}
            result["issues"].append(f"{db_name}: gagal diakses — {e}")

    result["status"] = "CRITICAL" if any("CORRUPT" in i or "GAGAL" in i for i in result["issues"]) \
        else ("WARNING" if result["issues"] else "OK")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 4. SYSTEM RESOURCES (CPU, RAM, DISK)
# ═══════════════════════════════════════════════════════════════════════════

def check_system_resources() -> Dict[str, Any]:
    """
    Cek penggunaan CPU/RAM proses bot (main.py) dan disk usage partisi project.
    """
    result: Dict[str, Any] = {"process": {}, "disk": {}, "issues": []}

    # ── Proses bot ──
    bot_proc = None
    try:
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline_str = " ".join(proc.info.get("cmdline") or [])
                if MAIN_SCRIPT_NAME in cmdline_str and "system_health_auditor" not in cmdline_str:
                    bot_proc = proc
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        result["issues"].append(f"Gagal scan proses: {e}")

    if bot_proc:
        try:
            cpu_pct = bot_proc.cpu_percent(interval=1.0)
            mem_info = bot_proc.memory_info()
            ram_mb = round(mem_info.rss / (1024 * 1024), 1)

            result["process"] = {
                "pid": bot_proc.pid,
                "cpu_pct": cpu_pct,
                "ram_mb": ram_mb,
            }

            if cpu_pct > CPU_WARN_PCT:
                result["issues"].append(f"CPU tinggi: {cpu_pct}% (>{CPU_WARN_PCT}%)")
            if ram_mb > RAM_WARN_MB:
                result["issues"].append(f"RAM tinggi: {ram_mb}MB (>{RAM_WARN_MB}MB)")
        except Exception as e:
            result["process"] = {"status": "error", "message": str(e)}
    else:
        result["process"] = {"status": "NOT_FOUND"}
        result["issues"].append("Proses main.py tidak ditemukan saat pengecekan resource")

    # ── Disk usage partisi project ──
    try:
        disk = psutil.disk_usage(str(BASE_DIR))
        disk_used_pct = disk.percent
        result["disk"] = {
            "used_pct": disk_used_pct,
            "free_gb": round(disk.free / (1024 ** 3), 2),
        }
        if disk_used_pct > 90:
            result["issues"].append(f"Disk penuh: {disk_used_pct}% terpakai")
    except Exception as e:
        result["disk"] = {"status": "error", "message": str(e)}

    result["status"] = "CRITICAL" if any("Disk penuh" in i for i in result["issues"]) \
        else ("WARNING" if result["issues"] else "OK")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 5. PROCESS UPTIME — DETEKSI CRASH + RESTART
# ═══════════════════════════════════════════════════════════════════════════

def check_process_uptime() -> Dict[str, Any]:
    """
    Cek sejak kapan proses main.py berjalan. Uptime singkat (<10 menit)
    bisa mengindikasikan bot baru saja crash dan auto-restart.
    """
    try:
        for proc in psutil.process_iter(["pid", "cmdline", "create_time"]):
            try:
                cmdline_str = " ".join(proc.info.get("cmdline") or [])
                if MAIN_SCRIPT_NAME in cmdline_str and "system_health_auditor" not in cmdline_str:
                    create_time = datetime.fromtimestamp(proc.info["create_time"], tz=WIB)
                    uptime = datetime.now(WIB) - create_time
                    uptime_minutes = uptime.total_seconds() / 60

                    status = "OK"
                    message = f"Bot berjalan sejak {create_time.strftime('%d/%m %H:%M')} WIB ({_format_duration(uptime)})"
                    if uptime_minutes < 10:
                        status = "WARNING"
                        message = f"⚠️ Bot baru start {round(uptime_minutes,1)} menit lalu — kemungkinan baru crash & restart"

                    return {
                        "status": status,
                        "pid": proc.info["pid"],
                        "start_time": create_time.isoformat(),
                        "uptime_minutes": round(uptime_minutes, 1),
                        "message": message,
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return {"status": "NOT_FOUND", "message": "Proses main.py tidak ditemukan"}


def _format_duration(td: timedelta) -> str:
    """Format timedelta jadi string human-readable (mis. '2 hari 3 jam')."""
    total_seconds = int(td.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days: parts.append(f"{days} hari")
    if hours: parts.append(f"{hours} jam")
    if minutes and not days: parts.append(f"{minutes} menit")
    return " ".join(parts) if parts else "< 1 menit"


# ═══════════════════════════════════════════════════════════════════════════
# 6. SIGNAL-TO-TRADE RATIO
# ═══════════════════════════════════════════════════════════════════════════

def check_signal_to_trade_ratio() -> Dict[str, Any]:
    """
    Bandingkan jumlah sinyal yang masuk (signals.db) vs trade yang benar2
    dibuka (virtual_trading.db) dalam 24 jam terakhir. Rasio sangat rendah
    (banyak sinyal tapi sedikit/tidak ada trade) bisa indikasi filter
    terlalu ketat atau bug gating — seperti kasus 'smc_data NameError'
    yang pernah terjadi di project ini.
    """
    # Gunakan UTC naive string supaya SQLite bisa bandingkan lexicografis dengan benar
    # Window 7 hari supaya laporan tidak kosong di hari pertama periode baru
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    result: Dict[str, Any] = {"signals_7d": 0, "trades_7d": 0, "ratio_pct": 0, "issues": []}

    # Jumlah sinyal masuk
    try:
        signals_db = BASE_DIR / "signals.db"
        if signals_db.exists():
            conn = sqlite3.connect(f"file:{signals_db}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()
            # Cek nama tabel yang ada dulu, karena skema bisa beda antar project version
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            signal_table = "signals" if "signals" in tables else (
                "performance" if "performance" in tables else None
            )
            if signal_table:
                cur.execute(
                    f"SELECT COUNT(*) FROM {signal_table} WHERE timestamp >= ?",
                    (cutoff_iso,)
                )
                result["signals_7d"] = cur.fetchone()[0]
            conn.close()
    except Exception as e:
        result["issues"].append(f"Gagal baca signals.db: {e}")

    # Jumlah trade dibuka
    try:
        vt_db = BASE_DIR / "virtual_trading.db"
        if vt_db.exists():
            conn = sqlite3.connect(f"file:{vt_db}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            if "virtual_trades" in tables:
                cur.execute(
                    "SELECT COUNT(*) FROM virtual_trades WHERE timestamp >= ?",
                    (cutoff_iso,)
                )
                result["trades_7d"] = cur.fetchone()[0]
            conn.close()
    except Exception as e:
        result["issues"].append(f"Gagal baca virtual_trading.db: {e}")

    if result["signals_7d"] > 0:
        result["ratio_pct"] = round(result["trades_7d"] / result["signals_7d"] * 100, 1)

    # Anomali: ada banyak sinyal tapi 0 trade sama sekali — pola persis seperti
    # bug smc_data NameError yang pernah membuat scanner 0-sinyal/0-trade diam-diam
    if result["signals_7d"] >= 10 and result["trades_7d"] == 0:
        result["issues"].append(
            f"⚠️ ANOMALI: {result['signals_7d']} sinyal masuk tapi 0 trade dibuka 7 hari terakhir "
            f"— mirip pola bug filter/exception tersembunyi"
        )
    elif result["signals_7d"] == 0:
        result["issues"].append("Tidak ada sinyal sama sekali dalam 24 jam — cek apakah scanner berjalan normal")

    result["status"] = "CRITICAL" if any("ANOMALI" in i for i in result["issues"]) \
        else ("WARNING" if result["issues"] else "OK")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR — RUN ALL CHECKS + KIRIM TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════

def run_system_health_check(send_telegram: bool = True) -> Dict[str, Any]:
    """
    Jalankan semua pengecekan Lapis 1 dan kirim ringkasan ke Telegram.
    Dipanggil dari main.py scheduler, terpisah dari job_health_check (trading).
    """
    logger.info("[SYS-HEALTH] Memulai system health check...")

    checks = {
        "duplicate_process": check_duplicate_process(),
        "log_health":        check_log_health(),
        "database":          check_database_integrity(),
        "resources":         check_system_resources(),
        "uptime":            check_process_uptime(),
        "signal_trade_ratio":check_signal_to_trade_ratio(),
    }

    all_issues: List[str] = []
    critical_count = 0
    warning_count = 0

    for name, data in checks.items():
        status = data.get("status", "OK")
        if status == "CRITICAL":
            critical_count += 1
        elif status == "WARNING":
            warning_count += 1
        for issue in data.get("issues", []):
            all_issues.append(f"[{name}] {issue}")
        if name == "duplicate_process" and status == "CRITICAL":
            all_issues.append(f"[duplicate_process] {data.get('message','')}")
        if name == "uptime" and status == "WARNING":
            all_issues.append(f"[uptime] {data.get('message','')}")

    overall_status = "🔴 CRITICAL" if critical_count > 0 else (
        "🟡 WARNING" if warning_count > 0 else "🟢 SEHAT"
    )

    now_str = datetime.now(WIB).strftime("%d/%m/%Y %H:%M")
    msg_lines = [
        "<b>🩺 SYSTEM HEALTH CHECK</b>",
        f"Waktu: {now_str} WIB",
        f"Status: {overall_status}",
        "",
    ]

    proc_info = checks["resources"].get("process", {})
    if proc_info.get("pid"):
        msg_lines.append(f"⚙️ Proses: PID {proc_info['pid']} | CPU {proc_info.get('cpu_pct','?')}% | RAM {proc_info.get('ram_mb','?')}MB")

    uptime_info = checks["uptime"]
    if uptime_info.get("message"):
        msg_lines.append(f"⏱️ {uptime_info['message']}")

    ratio_info = checks["signal_trade_ratio"]
    msg_lines.append(
        f"📊 Sinyal/Trade (24h): {ratio_info.get('signals_24h',0)} sinyal → "
        f"{ratio_info.get('trades_24h',0)} trade ({ratio_info.get('ratio_pct',0)}%)"
    )

    if all_issues:
        msg_lines.append("")
        msg_lines.append("<b>⚠️ Masalah Ditemukan:</b>")
        for issue in all_issues[:15]:  # batasi supaya tidak terlalu panjang
            msg_lines.append(f"• {issue}")
    else:
        msg_lines.append("")
        msg_lines.append("✅ Tidak ada masalah terdeteksi")

    msg_lines.append("")
    msg_lines.append("🤖 System Health Auditor (Lapis 1)")

    final_msg = "\n".join(msg_lines)

    if send_telegram:
        try:
            from telegram_sender import send_alert
            send_alert(final_msg)
        except Exception as e:
            logger.error(f"[SYS-HEALTH] Gagal kirim Telegram: {e}")

    logger.info(f"[SYS-HEALTH] Selesai — status={overall_status}, issues={len(all_issues)}")

    return {
        "status": overall_status,
        "checks": checks,
        "issues": all_issues,
        "timestamp": now_str,
    }


if __name__ == "__main__":
    import json
    result = run_system_health_check(send_telegram=False)
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
