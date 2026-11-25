# AGENTS.md

## Backend bot (Python/Flask)
- Server: `python3 api_server.py` (default port 5000). Butuh `config.py` lokal (tidak ada di repo).
- Endpoint Android baru ditambahkan di `api_server.py`: `/api/bot/status`, `/api/dashboard`, `/api/trades`, `/api/market-analysis`, `/api/risk/status`, dan kontrol `/api/bot/pause|resume|emergency-stop`.
- Endpoint kontrol wajib header `X-API-Key` (env `AI_SCANNER_API_KEY`, TANPA fallback). Jika env belum diset, endpoint kontrol menolak SEMUA permintaan dengan 503. Key tidak pernah di-log. Audit log di `audit_log/app_control.log`.
- Jangan ubah mesin trading/risk. Endpoint baru hanya baca state/DB + ubah flag `trading_halted` aman (hanya memblokir entry baru, tidak menutup posisi).

## Aplikasi Android
- Project Android ada di `android/` (Kotlin + Jetpack Compose + Material 3 + MVVM + Retrofit + Room + Vico).
- Base URL dikonfigurasi per perangkat lewat layar Settings (ikon gerigi). Default emulator `http://10.0.2.2:5000/`.
- API Control Key TIDAK ditanam di APK; dimasukkan manual di layar Risk Control. Tombol kontrol nonaktif jika key kosong.
- Jaringan: `network_security_config.xml` melarang cleartext (HTTP) untuk semua host kecuali loopback/emulator (localhost, 127.0.0.1, 10.0.2.2). Akses jarak jauh wajib HTTPS.

## Build
- Build lokal di sandbox ARM64 gagal karena `aapt2` SDK hanya x86_64 (tidak ada varian linux-aarch64). JANGAN buang waktu memperbaiki ini.
- Build APK yang benar: GitHub Actions workflow `.github/workflows/build-apk.yml` (ubuntu-latest x86_64, JDK 17, `./gradlew assembleDebug`, upload artifact).
- `android/local.properties` tidak boleh di-commit (sudah di .gitignore).

## Repo
- Branch lokal `main` (bukan eksperimen-ai). Jangan reset repo / jangan timpa perubahan lokal yang belum di-commit.
