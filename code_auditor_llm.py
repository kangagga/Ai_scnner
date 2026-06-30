#!/usr/bin/env python3
"""
code_auditor_llm.py — LAPIS 2: AUDIT KODE MENDALAM (via Groq)

Mengirim source code 3 file/hari (rotasi) ke Groq untuk audit terstruktur:
bug, race condition, exception handling kurang aman, memory leak, logic error.

PENTING — READ-ONLY:
  Modul ini HANYA MELAPORKAN. Tidak pernah menulis/mengubah file kode apapun.
  Hasil audit disimpan ke audit_log/ untuk direview manual oleh developer.

Strategi rotasi file:
  - File core kritis (main.py, scanner.py, risk_manager.py, exit_monitor.py,
    adaptive_brain_v6.py) diprioritaskan lebih sering muncul dalam rotasi.
  - File yang baru dimodifikasi (mtime terbaru) diprioritaskan di atas file lain.
  - State rotasi disimpan di JSON kecil supaya tidak mengaudit file yang sama
    berturut-turut dan akhirnya semua file ter-cover dalam beberapa hari.

Pakai Groq (llama-3.3-70b-versatile) — reuse _call_groq() dari ai_analyst.py,
konsisten dengan stack yang sudah dipakai project untuk post-mortem & sentiment.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("code_auditor_llm")

# ── Konfigurasi ──────────────────────────────────────────────────────────────
WIB = timezone(timedelta(hours=7))
BASE_DIR = Path(__file__).resolve().parent
AUDIT_LOG_DIR = BASE_DIR / "audit_log"
ROTATION_STATE_FILE = BASE_DIR / "code_audit_rotation_state.json"

FILES_PER_DAY = 3

# File core kritis — diprioritaskan dalam rotasi (muncul lebih sering)
CORE_FILES = [
    "main.py",
    "scanner.py",
    "risk_manager.py",
    "exit_monitor.py",
    "adaptive_brain_v6.py",
]

# File yang TIDAK pernah diaudit (bukan logic, atau terlalu besar/tidak relevan)
EXCLUDE_PATTERNS = [
    ".bak", ".bak_", "_backup", "backup_",
    "__pycache__", ".pyc", ".db", ".log", ".json",
    "venv/", "static/", "model/", "logs/", "audit_reports/",
    "scanner_backup", "scanner_main_refactor", "scanner_refactored",
    "indicators_backup", "part_aa", "part_ab",
]

# Batas ukuran file (karakter) yang dikirim ke Groq — hindari prompt terlalu besar
MAX_FILE_CHARS = 18000

AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# ROTASI FILE — PILIH FILE MANA YANG DIAUDIT HARI INI
# ═══════════════════════════════════════════════════════════════════════════

def _load_rotation_state() -> Dict[str, Any]:
    """Load state rotasi: kapan terakhir tiap file diaudit."""
    if ROTATION_STATE_FILE.exists():
        try:
            with open(ROTATION_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[CODE-AUDIT] Gagal load rotation state: {e}")
    return {"last_audited": {}, "history": []}


def _save_rotation_state(state: Dict[str, Any]) -> None:
    """Simpan state rotasi."""
    try:
        with open(ROTATION_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"[CODE-AUDIT] Gagal simpan rotation state: {e}")


def _list_candidate_files() -> List[Path]:
    """Daftar semua file .py di project yang layak diaudit (exclude pattern)."""
    candidates = []
    for path in BASE_DIR.glob("*.py"):
        name = path.name
        if any(pat in str(path) for pat in EXCLUDE_PATTERNS):
            continue
        if name == Path(__file__).name:  # jangan audit diri sendiri
            continue
        candidates.append(path)
    return candidates


def select_files_for_today() -> List[Path]:
    """
    Pilih FILES_PER_DAY file untuk diaudit hari ini, dengan prioritas:
      1. File core kritis yang paling lama tidak diaudit
      2. File yang baru dimodifikasi (mtime terbaru) dan belum pernah diaudit lagi-lagi
      3. File yang paling lama tidak pernah diaudit sama sekali (round-robin)
    """
    state = _load_rotation_state()
    last_audited = state.get("last_audited", {})
    candidates = _list_candidate_files()

    if not candidates:
        return []

    def score_file(path: Path) -> tuple:
        name = path.name
        last_audit_str = last_audited.get(name)
        last_audit_ts = (
            datetime.fromisoformat(last_audit_str).timestamp()
            if last_audit_str else 0
        )
        mtime = path.stat().st_mtime
        is_core = name in CORE_FILES

        # Skor lebih kecil = prioritas lebih tinggi untuk dipilih
        # Core file dapat bonus prioritas (dikurangi 7 hari setara waktu)
        core_bonus = -7 * 86400 if is_core else 0
        # File yang baru dimodifikasi dan lama tidak diaudit = prioritas tinggi
        recency_factor = -mtime * 0.1  # bobot kecil supaya tidak mendominasi
        return (last_audit_ts + core_bonus, recency_factor)

    sorted_candidates = sorted(candidates, key=score_file)
    selected = sorted_candidates[:FILES_PER_DAY]

    logger.info(f"[CODE-AUDIT] File terpilih hari ini: {[f.name for f in selected]}")
    return selected


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT BUILDER + GROQ CALL
# ═══════════════════════════════════════════════════════════════════════════

AUDIT_PROMPT_TEMPLATE = """Kamu adalah Senior Python Code Auditor untuk sistem trading bot crypto production (24/7).
Audit file berikut secara TERSTRUKTUR. Fokus HANYA pada:
1. Bug nyata (logic error, NameError/undefined variable, off-by-one, dll)
2. Race condition (terutama di kode yang pakai threading/concurrent.futures)
3. Exception handling yang tidak aman (bare except, silent fail yang menyembunyikan bug, exception yang ditangkap tapi tidak di-log)
4. Memory leak / resource leak (file/koneksi DB yang tidak ditutup, cache yang terus tumbuh tanpa batas)
5. Logic error yang berisiko terhadap uang/trading (kondisi yang salah urutan, off-by-one di perhitungan SL/TP, dll)

JANGAN laporkan masalah gaya kode (style/formatting) kecuali berdampak nyata pada bug.
JANGAN beri rekomendasi fitur baru — fokus HANYA pada bug & resiko di kode yang ada.

Nama file: {filename}

```python
{code}
```

WAJIB jawab HANYA dalam format JSON array (tanpa teks lain di luar JSON), dengan struktur:
[
  {{
    "severity": "Critical|High|Medium|Low",
    "line_hint": "nomor baris atau range perkiraan, atau 'N/A'",
    "issue": "deskripsi singkat masalah dalam Bahasa Indonesia",
    "recommendation": "rekomendasi perbaikan singkat dalam Bahasa Indonesia"
  }}
]

Jika tidak ada masalah signifikan ditemukan, kembalikan array kosong: []
"""


def audit_file_with_groq(file_path: Path) -> Dict[str, Any]:
    """
    Kirim 1 file ke Groq untuk audit, parse hasil JSON.
    Mengembalikan dict dengan hasil audit + metadata.
    """
    from ai_analyst import _call_groq

    try:
        with open(file_path, "r", errors="ignore") as f:
            code = f.read()
    except Exception as e:
        return {
            "file": file_path.name,
            "status": "error",
            "message": f"Gagal baca file: {e}",
            "findings": [],
        }

    truncated = False
    if len(code) > MAX_FILE_CHARS:
        code = code[:MAX_FILE_CHARS]
        truncated = True

    prompt = AUDIT_PROMPT_TEMPLATE.format(filename=file_path.name, code=code)

    raw_response = _call_groq(prompt, max_tokens=2048)

    findings: List[Dict[str, Any]] = []
    parse_error = None
    try:
        # Groq kadang membungkus JSON dengan teks/markdown — coba ekstrak blok JSON
        cleaned = raw_response.strip()
        if "```" in cleaned:
            # Ambil isi antara ```json ... ``` atau ``` ... ```
            parts = cleaned.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("["):
                    cleaned = part
                    break
        findings = json.loads(cleaned)
        if not isinstance(findings, list):
            findings = []
    except Exception as e:
        parse_error = str(e)
        logger.warning(f"[CODE-AUDIT] Gagal parse JSON untuk {file_path.name}: {e}")

    return {
        "file": file_path.name,
        "status": "ok" if not parse_error else "parse_error",
        "truncated": truncated,
        "findings": findings,
        "raw_response": raw_response if parse_error else None,  # simpan raw kalau parse gagal, untuk debug
        "parse_error": parse_error,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

def run_code_audit(send_telegram: bool = True) -> Dict[str, Any]:
    """
    Jalankan audit kode harian: pilih file, kirim ke Groq, simpan hasil,
    kirim ringkasan Critical/High ke Telegram.
    """
    logger.info("[CODE-AUDIT] Memulai audit kode mendalam (Lapis 2)...")

    files = select_files_for_today()
    if not files:
        logger.warning("[CODE-AUDIT] Tidak ada file kandidat untuk diaudit")
        return {"status": "skipped", "reason": "no_candidates"}

    state = _load_rotation_state()
    now = datetime.now(WIB)
    all_results = []
    critical_findings = []
    high_findings = []
    total_findings = 0

    for file_path in files:
        result = audit_file_with_groq(file_path)
        all_results.append(result)

        for finding in result.get("findings", []):
            total_findings += 1
            sev = str(finding.get("severity", "")).lower()
            entry = {**finding, "file": result["file"]}
            if sev == "critical":
                critical_findings.append(entry)
            elif sev == "high":
                high_findings.append(entry)

        # Update state rotasi — tandai file ini sudah diaudit sekarang
        state.setdefault("last_audited", {})[file_path.name] = now.isoformat()

    state.setdefault("history", []).append({
        "timestamp": now.isoformat(),
        "files": [f.name for f in files],
        "total_findings": total_findings,
        "critical": len(critical_findings),
        "high": len(high_findings),
    })
    # Batasi history supaya file state tidak terus membesar
    state["history"] = state["history"][-60:]
    _save_rotation_state(state)

    # ── Simpan full hasil ke audit_log/ ──
    log_filename = f"{now.strftime('%Y-%m-%d_%H%M')}.json"
    log_path = AUDIT_LOG_DIR / log_filename
    try:
        with open(log_path, "w") as f:
            json.dump({
                "timestamp": now.isoformat(),
                "files_audited": [f.name for f in files],
                "results": all_results,
            }, f, indent=2, default=str, ensure_ascii=False)
        logger.info(f"[CODE-AUDIT] Hasil lengkap disimpan: {log_path}")
    except Exception as e:
        logger.error(f"[CODE-AUDIT] Gagal simpan audit log: {e}")

    # ── Kirim ringkasan Telegram (hanya Critical/High, supaya tidak spam) ──
    if send_telegram:
        _send_audit_summary_telegram(
            now=now,
            files=[f.name for f in files],
            critical_findings=critical_findings,
            high_findings=high_findings,
            total_findings=total_findings,
            log_filename=log_filename,
        )

    logger.info(
        f"[CODE-AUDIT] Selesai — {len(files)} file diaudit, "
        f"{total_findings} temuan ({len(critical_findings)} Critical, {len(high_findings)} High)"
    )

    return {
        "status": "completed",
        "files_audited": [f.name for f in files],
        "total_findings": total_findings,
        "critical_count": len(critical_findings),
        "high_count": len(high_findings),
        "log_file": str(log_path),
    }


def _send_audit_summary_telegram(
    now: datetime,
    files: List[str],
    critical_findings: List[Dict],
    high_findings: List[Dict],
    total_findings: int,
    log_filename: str,
) -> None:
    """Kirim ringkasan audit ke Telegram — HANYA tampilkan Critical/High."""
    try:
        from telegram_sender import send_alert
    except Exception as e:
        logger.error(f"[CODE-AUDIT] Gagal import telegram_sender: {e}")
        return

    lines = [
        "<b>🔍 AUDIT KODE HARIAN (Lapis 2)</b>",
        f"Waktu: {now.strftime('%d/%m/%Y %H:%M')} WIB",
        f"File diaudit: {', '.join(files)}",
        f"Total temuan: {total_findings} (Critical: {len(critical_findings)}, High: {len(high_findings)})",
        "",
    ]

    if not critical_findings and not high_findings:
        lines.append("✅ Tidak ada temuan Critical/High. Detail lengkap di audit_log/" + log_filename)
    else:
        if critical_findings:
            lines.append("<b>🔴 CRITICAL:</b>")
            for f in critical_findings[:5]:
                lines.append(f"• [{f['file']}] {f.get('issue','')}")
                lines.append(f"  ↳ Saran: {f.get('recommendation','')}")
        if high_findings:
            lines.append("")
            lines.append("<b>🟠 HIGH:</b>")
            for f in high_findings[:5]:
                lines.append(f"• [{f['file']}] {f.get('issue','')}")
                lines.append(f"  ↳ Saran: {f.get('recommendation','')}")
        lines.append("")
        lines.append(f"📄 Detail lengkap: audit_log/{log_filename}")

    lines.append("")
    lines.append("⚠️ Ini HANYA laporan — tidak ada perubahan kode otomatis. Review manual diperlukan.")
    lines.append("🤖 Code Auditor LLM (Lapis 2, via Groq)")

    msg = "\n".join(lines)
    try:
        send_alert(msg)
    except Exception as e:
        logger.error(f"[CODE-AUDIT] Gagal kirim Telegram: {e}")


if __name__ == "__main__":
    result = run_code_audit(send_telegram=False)
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
