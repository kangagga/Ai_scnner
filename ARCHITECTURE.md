# ai-scanner Bot — Arsitektur Modul

## Diagram Alur Utama

    main.py (orchestrator)
    ├── schedule.every(60s) → job_scan()
    │   ├── scanner.scan_all_fast()
    │   │   ├── data_fetcher.fetch_ohlcv()
    │   │   ├── blacklist.is_blacklisted()
    │   │   ├── indicators.institutional_ai_v4()
    │   │   ├── market_context.detect_market_regime()
    │   │   ├── smc_scorer.smc_confidence()
    │   │   ├── orderbook_features.get_orderbook_features()
    │   │   ├── volume_profile.get_volume_profile()
    │   │   ├── liquidity_filter.check_liquidity()
    │   │   ├── dynamic_penalty.get_dynamic_penalty()
    │   │   ├── risk_manager.check_risk_approval()
    │   │   └── validators.validate_signal_dict()
    │   ├── virtual_trader.add_virtual_trade()
    │   ├── database.save_signal()
    │   └── telegram_sender.send_top_signals()
    │
    ├── schedule.every(60s) → exit_monitor (background)
    │   ├── Cek harga vs TP1/TP2/TP3/SL
    │   ├── virtual_trader.close_virtual_trade()
    │   ├── ai_analyst (Groq post-mortem)
    │   └── telegram_sender.send_alert()
    │
    ├── schedule.every(6h) → job_health_check()
    │   ├── bot_auditor.run_audit()
    │   ├── auto_blacklist.run_auto_blacklist()
    │   └── self_learning.run_self_learning()
    │       ├── trade_analyzer.analyze()
    │       └── xgb_trainer.XGBTrainer.train()
    │
    └── schedule.every(day) → job_daily_report()
        ├── telegram_sender.send_daily_report()
        └── email_reporter.send_email_report()

## Score Pipeline

    indicators → confidence_raw (0-100)
        + SMC layer        (-10 s/d +15)
        + Orderbook        (-10 s/d +10)
        + Volume Profile   ( -8 s/d  +8)
        + Liquidity        ( -5 s/d  +3)
        = confidence_pre   (max 100)
        + Dynamic Penalty  (-20 s/d  0)
        = confidence_final (0-100)
        → validate_signal_dict()
        → Alert Level:
            EKSEKUSI    score>=65 + SMC>=70 + valid
            SIAP ENTRY  score>=55 + SMC>=50
            WATCHLIST   score>=45
            MONITOR     score<45

## Tanggung Jawab Setiap File

| File                   | Tanggung Jawab                              |
|------------------------|---------------------------------------------|
| main.py                | Orchestrator, scheduling, job runner        |
| scanner.py             | Core pipeline fetch-analyze-score-filter    |
| indicators.py          | Kalkulasi semua indikator teknikal          |
| market_context.py      | BTC trend, Fear & Greed, regime detection   |
| smc_scorer.py          | Smart Money Concepts scoring                |
| orderbook_features.py  | Orderbook imbalance, funding rate           |
| volume_profile.py      | VWAP, POC, buy/sell pressure                |
| liquidity_filter.py    | Liquidity & slippage check                  |
| dynamic_penalty.py     | Penalty berbasis trade history              |
| risk_manager.py        | Portfolio heat, drawdown, position sizing   |
| virtual_trader.py      | Simulasi trade, track balance               |
| exit_monitor.py        | Monitor TP/SL/trailing stop                 |
| telegram_sender.py     | Format & kirim notifikasi                   |
| blacklist.py           | Blacklist & cooldown management             |
| auto_blacklist.py      | Auto-blacklist pair konsisten loss          |
| trade_analyzer.py      | Analisa statistik trade history             |
| xgb_trainer.py         | Training XGBoost model                      |
| self_learning.py       | Trigger retrain + model protection          |
| database.py            | SQLite operations untuk signals.db          |
| validators.py          | Input/output validation & guards            |
| logger_config.py       | Centralized logging setup                   |
| config.py              | Semua konfigurasi & konstanta               |
| data_fetcher.py        | Fetch OHLCV & symbol list dari Gate.io      |
| ai_analyst.py          | Groq AI post-trade analysis                 |
| bot_auditor.py         | Health check & audit harian                 |

## Database Schema

    signals.db
    ├── signals         — history semua sinyal
    ├── performance     — hasil trade WIN/LOSS/pnl
    └── signal_cooldown — cooldown per pair

    virtual_trading.db
    ├── virtual_trades  — semua trade virtual + 16 kolom fitur
    └── virtual_balance — balance, peak, stats

## File Standalone (tidak diimport bot)

    query.py               — query manual DB
    export_dashboard_data.py — export data dashboard
    send_dashboard_email.py  — kirim email dashboard
