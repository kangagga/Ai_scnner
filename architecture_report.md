# Architecture Report — ai-scanner
Generated: 2026-07-03T12:10:25.289703
Total Python files: 66
Total lines of code: 21413

## 1. File Structure & Size
| File | LOC |
|---|---|
| adaptive_brain_v6.py | 2428 |
| adaptive_weights.py | 298 |
| ai-dashboard/backend/api_server.py | 36 |
| ai_analyst.py | 124 |
| api_server.py | 339 |
| api_server_addon.py | 169 |
| auto_blacklist.py | 134 |
| backtester.py | 327 |
| backup_v7/adaptive_brain_v6.py | 675 |
| backup_v7/dynamic_penalty.py | 107 |
| backup_v7/indicators.py | 724 |
| backup_v7/main.py | 576 |
| backup_v7/market_context.py | 577 |
| backup_v7/risk_manager.py | 508 |
| backup_v7/scanner.py | 892 |
| backup_v7/trade_analyzer.py | 292 |
| backup_v7/volume_profile.py | 162 |
| blacklist.py | 84 |
| bot_auditor.py | 174 |
| code_auditor_llm.py | 376 |
| config.py | 115 |
| data_fetcher.py | 431 |
| database.py | 181 |
| divergence_detector.py | 134 |
| dynamic_penalty.py | 107 |
| email_reporter.py | 129 |
| exit_monitor.py | 264 |
| export_dashboard_data.py | 182 |
| indicators.py | 1035 |
| institutional_v7_addon.py | 289 |
| liquidity_filter.py | 125 |
| logger_config.py | 64 |
| main.py | 625 |
| market_context.py | 577 |
| module_auditor.py | 326 |
| monitor_trades.py | 49 |
| orderbook_features.py | 166 |
| patch_dashboard.py | 110 |
| patch_timezone_wib.py | 130 |
| query.py | 23 |
| retest_filter.py | 126 |
| risk_manager.py | 515 |
| scanner.py | 963 |
| scanner_backup_20260624.py | 923 |
| scanner_cooldown.py | 120 |
| scanner_fetcher.py | 96 |
| scanner_main_refactor.py | 564 |
| scanner_refactored.py | 450 |
| scanner_signals.py | 122 |
| self_learning.py | 128 |
| send_dashboard_email.py | 64 |
| smart_zone_engine.py | 197 |
| smc_scorer.py | 141 |
| smc_trade_counter.py | 163 |
| system_health_auditor.py | 518 |
| telegram_sender.py | 539 |
| test_alert_level.py | 18 |
| trade_analyzer.py | 292 |
| trend_filter.py | 138 |
| validators.py | 97 |
| virtual_trader.py | 290 |
| volume_filter.py | 125 |
| volume_profile.py | 162 |
| win_rate_predictor.py | 291 |
| xgb_trainer.py | 171 |
| zone_detector.py | 136 |

## 2. Internal Dependency Graph (module -> imports local module)
- **adaptive_brain_v6** → config
- **api_server** → database, market_context, risk_manager
- **ai_analyst** → config
- **api_server_addon** → market_context, risk_manager
- **auto_blacklist** → blacklist, config
- **backtester** → config, data_fetcher, indicators
- **dynamic_penalty** → config
- **main** → ai_analyst, api_server, auto_blacklist, backtester, bot_auditor, code_auditor_llm, config, database, email_reporter, exit_monitor, logger_config, market_context, risk_manager, scanner, self_learning, system_health_auditor, telegram_sender, virtual_trader
- **market_context** → config, data_fetcher, indicators
- **risk_manager** → config
- **scanner** → blacklist, config, data_fetcher, database, dynamic_penalty, indicators, liquidity_filter, market_context, orderbook_features, risk_manager, smc_scorer, volume_profile, win_rate_predictor, xgb_trainer
- **bot_auditor** → ai_analyst, telegram_sender
- **code_auditor_llm** → ai_analyst, telegram_sender
- **database** → blacklist, market_context
- **email_reporter** → config
- **exit_monitor** → ai_analyst, blacklist, virtual_trader
- **liquidity_filter** → config
- **monitor_trades** → data_fetcher
- **retest_filter** → smart_zone_engine
- **scanner_backup_20260624** → blacklist, config, data_fetcher, database, dynamic_penalty, indicators, liquidity_filter, market_context, orderbook_features, risk_manager, smc_scorer, validators, volume_profile, win_rate_predictor, xgb_trainer
- **scanner_fetcher** → data_fetcher
- **scanner_main_refactor** → adaptive_weights, blacklist, config, data_fetcher, database, dynamic_penalty, indicators, liquidity_filter, market_context, orderbook_features, risk_manager, scanner.cooldown, scanner.fetcher, scanner.signals, smc_scorer, smc_trade_counter, validators, volume_profile, win_rate_predictor, xgb_trainer
- **scanner_refactored** → blacklist, config, data_fetcher, database, dynamic_penalty, indicators, liquidity_filter, market_context, orderbook_features, risk_manager, scanner.cooldown, scanner.fetcher, scanner.signals, smc_scorer, smc_trade_counter, validators, volume_profile, win_rate_predictor, xgb_trainer
- **self_learning** → config, trade_analyzer, xgb_trainer
- **send_dashboard_email** → config
- **smart_zone_engine** → zone_detector
- **smc_scorer** → divergence_detector, retest_filter, smart_zone_engine, trend_filter, volume_filter, zone_detector
- **smc_trade_counter** → xgb_trainer
- **system_health_auditor** → telegram_sender
- **telegram_sender** → bot_auditor, config, database, risk_manager, virtual_trader
- **test_alert_level** → telegram_sender
- **virtual_trader** → risk_manager, telegram_sender
- **win_rate_predictor** → data_fetcher, indicators

## 3. Key Configuration Constants
### /home/userland/ai-scanner/config.py
- `BOT_TOKEN = ***REDACTED***`
- `CHAT_ID = ***REDACTED***`
- `GROQ_API_KEY = ***REDACTED***`
- `EMAIL_SENDER = ***REDACTED***`
- `EMAIL_PASSWORD = ***REDACTED***`
- `EMAIL_RECEIVER = ***REDACTED***`
- `SCAN_INTERVAL = 60`
- `MIN_SCORE = 30`
- `SIGNAL_THRESHOLD = 35`
- `MAX_SIGNALS_PER_DAY = 50`
- `TIMEFRAMES = ['1h']`
- `PAIR_LIMIT = 300`
- `RISK_PER_TRADE = 0.25`
- `ACCOUNT_BALANCE = 80.04`
- `MACD_FAST = 12`
- `MACD_SLOW = 26`
- `MACD_SIGNAL = 9`
- `RSI_PERIOD = 14`
- `VOLUME_MA = 20`
- `DAILY_REPORT_HOUR = 0`
- `DAILY_REPORT_MINUTE = 0`
- `WATCHLIST = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'BCHUSDT', 'ATOMUSDT', 'NEARUSDT', 'APTUSDT', 'SUIUSDT', 'INJUSDT', 'SEIUSDT', 'TIAUSDT', 'ICPUSDT', 'XLMUSDT', 'ALGOUSDT', 'EGLDUSDT', 'VETUSDT', 'FTMUSDT', 'ONEUSDT', 'UNIUSDT', 'AAVEUSDT', 'MKRUSDT', 'LDOUSDT', 'GMXUSDT', 'RUNEUSDT', 'CRVUSDT', 'SNXUSDT', 'COMPUSDT', 'DYDXUSDT', 'YFIUSDT', 'BALUSDT', 'KAVAUSDT', 'SUSHIUSDT', '1INCHUSDT', 'ARBUSDT', 'OPUSDT', 'IMXUSDT', 'STRKUSDT', 'METISUSDT', 'LRCUSDT', 'SKLUSDT', 'STXUSDT', 'FETUSDT', 'RENDERUSDT', 'WLDUSDT', 'AGIXUSDT', 'OCEANUSDT', 'TAOUSDT', 'LINKUSDT', 'TRXUSDT', 'HBARUSDT', 'QNTUSDT', 'FILUSDT', 'ARUSDT', 'CELRUSDT', 'CFXUSDT', 'BANDUSDT', 'XTZUSDT', 'DOGEUSDT', 'SHIBUSDT', 'PEPEUSDT', 'FLOKIUSDT', 'WIFUSDT', 'BONKUSDT', 'AXSUSDT', 'SANDUSDT', 'MANAUSDT', 'GALAUSDT', 'GMTUSDT', 'ENJUSDT', 'CHRUSDT', 'ROSEUSDT', 'JUPUSDT', 'ENAUSDT', 'NOTUSDT', 'ZROUSDT', 'EIGENUSDT', 'CATIUSDT', 'BOMEUSDT', 'BLURUSDT', 'TURBOUSDT', 'ILVUSDT', 'OKBUSDT', 'BTTUSDT', 'HOTUSDT', 'ETHBTC', 'BNBBTC', 'SOLBTC', 'XRPBTC', 'ADABTC', 'DOTBTC', 'AVAXBTC', 'WUSDT', 'PYTHUSDT', 'JTOUSDT', 'MEMEUSDT', 'ACEUSDT', 'ALTUSDT', 'RONINUSDT', 'PIXELUSDT', 'PORTALUSDT', 'STRKUSDT', 'DYMUSDT', 'AIUSDT', 'LPTUSDT', 'ORDIUSDT', 'SATSUSDT', 'RATS1USDT', '10000SATSUSDT', 'MOVRUSDT', 'ZRXUSDT', 'UMAUSDT', 'API3USDT', 'ACHUSDT', 'HIGHUSDT', 'MDTUSDT', 'ONGUSDT', 'FORTHUSDT', 'IDUSDT', 'AMBUSDT', 'CVXUSDT', 'PENDLEUSDT', 'WLDUSDT', 'VANRYUSDT', 'AEVOUSDT', 'SAFEUSDT']`
- `WATCHLIST = list(dict.fromkeys(WATCHLIST))[:150]`
- `BLACKLIST_DAYS = 7`
- `BLACKLIST_MIN_TRADES = 5`
- `BLACKLIST_MAX_WR = 30`
- `BLACKLIST_MAX_LOSS = 4`
- `MIN_LIQUIDITY_USD = 10000`
- `MAX_SPREAD_PCT = 0.5`
- `MIN_DAILY_VOL_USD = 100000`
- `RETRAIN_EVERY_N = 50`
- `MIN_TRADES_FOR_XGB = 50`
- `XGB_ROLLBACK_THRESH = 0.03`
- `SCORE_MIN = 0`
- `SCORE_MAX = 100`
- `SMC_BONUS_MAX = 15`
- `SMC_PENALTY_MAX = -10`
- `OB_BONUS_MAX = 10`
- `OB_PENALTY_MAX = -10`
- `VP_BONUS_MAX = 8`
- `VP_PENALTY_MAX = -8`
- `LIQ_BONUS_MAX = 3`
- `LIQ_PENALTY_MAX = -5`
- `PENALTY_CACHE_TTL = 300`
- `PENALTY_WR_HARD = 35`
- `PENALTY_WR_SOFT = 45`
- `ANALYSIS_MIN_TRADES = 5`
- `ANALYSIS_DAYS_BACK = 14`
- `MAX_OPEN_POSITIONS = 5`
- `MAX_PORTFOLIO_HEAT = 6.0`
- `MAX_DRAWDOWN_PCT = 15.0`
- `MAX_CONSECUTIVE_LOSS = 15`

## 4. Database Schema
### signals.db
```sql
CREATE TABLE signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT,
            symbol      TEXT,
            timeframe   TEXT,
            signal      TEXT,
            confidence  REAL,
            momentum    REAL,
            win_rate    REAL,
            entry       REAL,
            sl          REAL,
            tp1         REAL,
            tp2         REAL,
            tp3         REAL,
            rr_ratio    REAL,
            sent        INTEGER DEFAULT 0
        )
```
```sql
CREATE TABLE sqlite_sequence(name,seq)
```
```sql
CREATE TABLE performance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT,
            symbol      TEXT,
            signal      TEXT,
            entry       REAL,
            exit_price  REAL,
            pnl_pct     REAL,
            result      TEXT
        , timeframe TEXT, confidence REAL, rsi REAL, adx REAL, macd_hist REAL, vol_ratio REAL, squeeze_score REAL, regime TEXT, fg_value INTEGER, btc_trend TEXT)
```
```sql
CREATE TABLE signal_cooldown (
                key TEXT PRIMARY KEY,
                signal_type TEXT,
                last_time TEXT
            )
```
```sql
CREATE TABLE smc_counter (
                id          INTEGER PRIMARY KEY,
                symbol      TEXT,
                timeframe   TEXT,
                signal_type TEXT,
                smc_score   REAL,
                ts          TEXT
            )
```
```sql
CREATE TABLE smc_retrain_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                triggered_at TEXT,
                smc_count    INTEGER,
                status       TEXT
            )
```
### brain_memory.db
```sql
CREATE TABLE trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT    NOT NULL,
                    signal      TEXT    NOT NULL,
                    confidence  REAL,
                    regime      TEXT,
                    session     TEXT,
                    setup_type  TEXT,
                    score       REAL,
                    indicators  TEXT,
                    profit      REAL    DEFAULT 0,
                    loss        REAL    DEFAULT 0,
                    rr_actual   REAL    DEFAULT 0,
                    sl_hit      INTEGER DEFAULT 0,
                    tp1_hit     INTEGER DEFAULT 0,
                    tp2_hit     INTEGER DEFAULT 0,
                    timestamp   TEXT    NOT NULL
                )
```
```sql
CREATE TABLE sqlite_sequence(name,seq)
```
```sql
CREATE TABLE indicator_weights (
                    name         TEXT PRIMARY KEY,
                    weight       REAL NOT NULL,
                    hits         INTEGER DEFAULT 0,
                    misses       INTEGER DEFAULT 0,
                    last_updated TEXT
                )
```
```sql
CREATE TABLE pair_stats (
                    symbol              TEXT PRIMARY KEY,
                    total               INTEGER DEFAULT 0,
                    wins                INTEGER DEFAULT 0,
                    losses              INTEGER DEFAULT 0,
                    total_profit        REAL    DEFAULT 0,
                    total_loss          REAL    DEFAULT 0,
                    consecutive_loss    INTEGER DEFAULT 0,
                    confidence_modifier REAL    DEFAULT 0,
                    last_updated        TEXT
                )
```
```sql
CREATE TABLE session_stats (
                    session         TEXT PRIMARY KEY,
                    total           INTEGER DEFAULT 0,
                    wins            INTEGER DEFAULT 0,
                    score_modifier  REAL    DEFAULT 0
                )
```
```sql
CREATE TABLE regime_stats (
                    regime              TEXT PRIMARY KEY,
                    total               INTEGER DEFAULT 0,
                    wins                INTEGER DEFAULT 0,
                    best_setup          TEXT    DEFAULT '',
                    worst_setup         TEXT    DEFAULT '',
                    avg_rr              REAL    DEFAULT 0,
                    threshold_modifier  REAL    DEFAULT 0
                )
```
```sql
CREATE TABLE decisions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    symbol      TEXT,
                    signal      TEXT,
                    score       REAL,
                    threshold   REAL,
                    recommendation TEXT,
                    reasoning   TEXT,
                    context     TEXT
                )
```
### virtual_trading.db
```sql
CREATE TABLE virtual_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            signal TEXT,
            entry REAL,
            sl REAL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            exit_price REAL,
            pnl_pct REAL,
            pnl_usd REAL,
            result TEXT,
            balance_after REAL,
            timeframe TEXT
        , closed INTEGER DEFAULT 0, exit REAL DEFAULT 0, pnl_usdt REAL DEFAULT 0, closed_at TEXT, smc_score REAL DEFAULT 0, smc_bonus REAL DEFAULT 0, ob_imbalance REAL DEFAULT 0, ob_pressure TEXT DEFAULT 'N/A', ob_bonus REAL DEFAULT 0, vp_ratio REAL DEFAULT 1, vp_bonus REAL DEFAULT 0, liq_usd REAL DEFAULT 0, liq_score INTEGER DEFAULT 5, liq_adj REAL DEFAULT 0, funding_rate REAL DEFAULT 0, price_vs_vwap REAL DEFAULT 0, score_raw REAL DEFAULT 0, score_final REAL DEFAULT 0, regime TEXT DEFAULT 'NEUTRAL', hour_entry INTEGER DEFAULT 0, support REAL DEFAULT 0, resistance REAL DEFAULT 0, sr_guard_pass INTEGER DEFAULT 0)
```
```sql
CREATE TABLE sqlite_sequence(name,seq)
```
```sql
CREATE TABLE virtual_balance (
            id INTEGER PRIMARY KEY,
            balance REAL,
            peak_balance REAL,
            total_trades INTEGER,
            total_wins INTEGER,
            total_losses INTEGER,
            updated_at TEXT
        )
```
### bot.db
### trades.db
### trading_bot.db
### virtual_trades.db

## 5. Module Contents (classes & functions per file)
### adaptive_brain_v6.py
**Classes:**
- `class IndicatorWeight()`
- `class PairStats()`
- `class SessionStats()`
- `class RegimeStats()`
- `class RiskLearning()`
- `class AIMemory()`
- `class BrainState()`
- `class PerformanceMemory()`
- `class AdaptiveScoreEngine()`
- `class AdaptiveBrainV6()`
**Functions:**
- `def get_brain()`
- `def get_threshold(market_context)`
- `def get_confidence(indicators, market_context)`
- `def get_risk_params(market_context)`
- `def update_weights(result, indicators, context, profit, loss)`
- `def calibrate_brain()`
- `def get_adaptive_score(components, regime, signal, symbol, hour)`
- `def get_recommendation(score, market_context, symbol, signal)`
- `def get_market_health(context)`
- `def get_ai_memory()`
- `def get_performance_stats(days)`
- `def record_trade_result(trade_data)`
- `def get_confidence_level(confidence)`
- `def get_weight_profile(regime)`
- `def compute_adaptive_score(components, regime)`
- `def compute_confidence(regime, trend_score, volume_score, volatility, sr_score, liquidity, smc_score)`
- `def should_skip_volatile(confidence)`
- `def get_position_size_multiplier(regime, confidence)`
- `def get_sl_tp_multiplier(regime)`
- `def extract_components_from_last(last, df)`
- `def hit_rate(self)`
- `def sample_size(self)`
- `def win_rate(self)`
- `def profit_factor(self)`
- `def win_rate(self)`
- `def win_rate(self)`
- `def __init__(self, db_path)`
- `def conn(self)`
- `def _init_db(self)`
- `def save_trade(self, trade)`
- `def load_recent_trades(self, days)`
- `def get_pair_performance(self, symbol, days)`
- `def get_session_performance(self, session, days)`
- `def get_regime_performance(self, regime, days)`
- `def get_global_stats(self, days)`
- `def get_sl_stats(self, days)`
- `def save_indicator_weights(self, weights)`
- `def load_indicator_weights(self)`
- `def save_decision(self, decision)`
- `def prune_old_data(self, days)`
- `def __init__(self, weights)`
- `def _safe(self, v, default)`
- `def compute(self, components, regime)`
- `def compute_penalties(self, components, regime, signal)`
- `def compute_rewards(self, components, regime, signal)`
- `def __init__(self, state_dir)`
- `def _state_file(self)`
- `def _load_state(self)`
- `def _save_state(self)`
- `def _init_default_weights(self)`
- `def _get_current_session(self, hour)`
- `def get_threshold(self, market_context)`
- `def get_confidence(self, indicators, market_context)`
- `def get_confidence_level(self, confidence)`
- `def get_adaptive_score(self, components, regime, signal, symbol, hour)`
- `def get_recommendation(self, score, market_context, symbol, signal)`
- `def get_market_health(self, context)`
- `def get_risk_params(self, market_context)`
- `def update_weights(self, result, indicators, context, profit, loss)`
- `def record_trade_result(self, trade_data)`
- `def _check_smart_recovery(self)`
- `def get_performance_stats(self, days)`
- `def _calc_max_drawdown(self, trades)`
- `def get_ai_memory(self)`
- `def _refresh_ai_memory(self)`
- `def calibrate(self)`
- `def learn(self)`
- `def save(self)`
- `def load(self)`
- `def get_brain(self)`
- `def sf(v, default)`
- `def _w(name, default)`
- `def _s(v, d)`
- `def _s(v, d)`

### adaptive_weights.py
**Functions:**
- `def get_weight_profile(regime)`
- `def compute_adaptive_score(components, regime)`
- `def compute_confidence(regime, trend_score, volume_score, volatility, sr_score, liquidity, smc_score)`
- `def should_skip_volatile(confidence)`
- `def get_position_size_multiplier(regime, confidence)`
- `def get_sl_tp_multiplier(regime)`
- `def extract_components_from_last(last, df)`
- `def sf(v, default)`

### ai-dashboard/backend/api_server.py
**Functions:**
- `def status()`
- `def signals()`
- `def logs()`
- `def progress()`

### ai_analyst.py
**Functions:**
- `def _call_groq(prompt, max_tokens)`
- `def analyse_market_sentiment(top_signals)`
- `def analyse_single_signal(signal)`
- `def analyse_trade_postmortem(trade)`
- `def filter_signals_ai(signals, market_ctx)`

### api_server.py
**Functions:**
- `def update_signals(signals)`
- `def update_progress(pct, current, done, total)`
- `def add_log(icon, message)`
- `def update_cooldowns(cooldowns)`
- `def set_config(cfg)`
- `def index()`
- `def api_signals()`
- `def api_signals_orig()`
- `def api_status()`
- `def api_history()`
- `def api_stats()`
- `def api_health()`
- `def start_api(host, port)`
- `def manifest()`
- `def service_worker()`
- `def heatmap()`
- `def api_portfolio()`
- `def api_performance()`
- `def api_market_regime()`
- `def _run()`

### api_server_addon.py
**Functions:**
- `def api_portfolio()`
- `def api_performance()`
- `def api_market_regime()`

### auto_blacklist.py
**Functions:**
- `def get_pair_stats(days_back)`
- `def get_consecutive_losses(symbol)`
- `def add_to_blacklist(symbol, reason, days)`
- `def run_auto_blacklist()`
- `def get_blacklist_report()`

### backtester.py
**Functions:**
- `def run_backtest(symbol, timeframe, days, sl_atr, tp1_atr, tp2_atr, tp3_atr, min_confidence)`
- `def run_backtest_multi(symbols, timeframe, days, min_confidence)`
- `def print_report(result)`

### backup_v7/adaptive_brain_v6.py
**Classes:**
- `class IndicatorWeight()`
- `class BrainState()`
- `class PerformanceMemory()`
- `class DecisionLogger()`
- `class AdaptiveBrainV6()`
**Functions:**
- `def get_brain()`
- `def get_threshold(market_context)`
- `def get_confidence(indicators, market_context)`
- `def get_risk(risk_status)`
- `def update_trade_result(indicators, profit, loss, context)`
- `def learn()`
- `def calibrate()`
- `def save()`
- `def load()`
- `def __init__(self, db_path)`
- `def conn(self)`
- `def _init_db(self)`
- `def save_trade(self, trade)`
- `def save_indicator_weights(self, weights)`
- `def load_indicator_weights(self)`
- `def load_recent_trades(self, days)`
- `def prune_old_data(self, days)`
- `def __init__(self, log_path)`
- `def log_decision(self, entry)`
- `def __init__(self, state_dir)`
- `def _state_file(self)`
- `def _load_state(self)`
- `def _save_state(self)`
- `def _init_default_weights(self)`
- `def get_threshold(self, market_context)`
- `def get_confidence(self, indicators, market_context)`
- `def _normalise_indicator(self, name, value)`
- `def get_risk(self, risk_status)`
- `def get_position_advice(self, risk_status, risk_params)`
- `def update_trade_result(self, indicators, profit, loss, context)`
- `def calibrate(self)`
- `def learn(self)`
- `def save(self)`
- `def load(self)`
- `def get_brain(self)`

### backup_v7/dynamic_penalty.py
**Functions:**
- `def get_session(hour)`
- `def _load_analysis()`
- `def load_rules()`
- `def get_dynamic_penalty(signal, hour, regime)`
- `def get_pair_penalty(symbol)`
- `def get_penalty_summary()`

### backup_v7/indicators.py
**Functions:**
- `def rsi_wilder(close, period)`
- `def atr(df, period)`
- `def bollinger_bands(close, period, std_dev)`
- `def stochastic(df, k_period, d_period)`
- `def adx(df, period)`
- `def volume_analysis(df, period)`
- `def rsi_divergence(close, rsi, lookback)`
- `def macd_divergence(close, macd_hist, lookback)`
- `def support_resistance(df, window)`
- `def candle_patterns(df)`
- `def bb_squeeze_score(bb_width, lookback)`
- `def volume_dry_up(vol_ratio, window)`
- `def volume_expansion(vol_ratio, window)`
- `def macd_momentum_building(macd_hist)`
- `def rsi_pre_signal(rsi)`
- `def price_compression(df, window)`
- `def ema_convergence(ema9, ema20, ema50)`
- `def stoch_pre_cross(stoch_k, stoch_d)`
- `def higher_low_detection(df, window)`
- `def institutional_ai_v4(df)`

### backup_v7/main.py
**Functions:**
- `def _check_single_instance()`
- `def _release_lock()`
- `def filter_correlated_signals(signals, max_total, max_same_direction)`
- `def calculate_correlation_exposure(signals)`
- `def calculate_position_sizes(signals, total_risk_capital, min_size)`
- `def get_regime_risk_multiplier(market_context)`
- `def apply_regime_risk_adjustment(positions, market_context)`
- `def _build_cooldown_info()`
- `def job_scan()`
- `def job_daily_report()`
- `def job_weekly_report()`
- `def job_health_check()`
- `def run_startup_backtest(send_telegram)`
- `def main()`
- `def _cmd_loop()`

### backup_v7/market_context.py
**Functions:**
- `def get_fear_greed()`
- `def get_funding_rates(symbols)`
- `def get_funding_rate(symbol)`
- `def get_btc_trend()`
- `def get_market_context()`
- `def get_btc_change_pct()`
- `def is_btc_dump(threshold)`
- `def is_btc_pump(threshold)`
- `def detect_market_regime(symbol, timeframe)`
- `def get_global_regime(symbols, timeframe)`

### backup_v7/risk_manager.py
**Classes:**
- `class RiskState()`
**Functions:**
- `def kelly_criterion(win_rate_pct, avg_win_pct, avg_loss_pct)`
- `def check_risk_approval(symbol, timeframe, signal, entry, sl, win_rate, avg_pnl, wr_is_default, similar_cases)`
- `def record_trade_result(symbol, timeframe, signal, pnl_usdt, win)`
- `def open_position(symbol, timeframe, signal, risk_pct)`
- `def reset_positions()`
- `def get_risk_status()`
- `def resume_trading(manual)`
- `def print_risk_status()`
- `def __init__(self)`
- `def _load(self)`
- `def save(self)`
- `def reset_daily(self)`
- `def update_balance(self, pnl_usdt, win)`
- `def current_drawdown_pct(self)`
- `def portfolio_heat(self)`
- `def add_position(self, key, risk_pct)`
- `def remove_position(self, key)`
- `def reset_positions(self)`

### backup_v7/scanner.py
**Functions:**
- `def _init_cooldown_table()`
- `def _load_cooldown_state()`
- `def _save_cooldown_state(key, signal_type, last_time)`
- `def _cast_df(df)`
- `def _safe(val, default)`
- `def _get_macd_cross(last, prev)`
- `def _get_ema_trend(last)`
- `def _calculate_tp_levels(entry, sl, signal, atr, regime, smc_score)`
- `def _calculate_position_size(entry, sl, risk_pct, balance)`
- `def _apply_rate_limit()`
- `def _cached_fetch(symbol, timeframe, limit)`
- `def _fetch_with_retry(symbol, timeframe, limit)`
- `def _is_duplicate(symbol, timeframe, signal_type, confidence)`
- `def _analyse_single(symbol, timeframe, min_score)`
- `def scan_all_fast(symbols, timeframe, min_score)`
- `def get_dynamic_threshold(ctx, signal_type)`
- `def _correlation_filter(signals, max_same_direction)`
- `def get_top_signals(results, top_n, threshold)`
- `def simple_correlation_filter(signals)`

### backup_v7/trade_analyzer.py
**Functions:**
- `def load_trades()`
- `def win_rate(df)`
- `def profit_factor(df)`
- `def avg_rr(df)`
- `def max_drawdown(df)`
- `def session_label(hour)`
- `def analyze()`
- `def print_report(result)`
- `def analyze_regime(df)`
- `def build_penalty_rules(df)`

### backup_v7/volume_profile.py
**Functions:**
- `def _fetch_trades(symbol, limit)`
- `def get_volume_profile(symbol)`
- `def _calc_vp_adj(vp)`
- `def vp_score_adjustment(vp, signal)`

### blacklist.py
**Functions:**
- `def _load()`
- `def _save(data)`
- `def is_blacklisted(symbol)`
- `def report_false_signal(symbol)`
- `def add_loss_cooldown(symbol)`
- `def is_in_cooldown(symbol)`
- `def get_blacklist()`

### bot_auditor.py
**Functions:**
- `def get_db()`
- `def audit_win_rate()`
- `def audit_active_trades()`
- `def audit_consecutive_loss()`
- `def audit_log_errors()`
- `def run_audit()`
- `def get_summary_today()`

### code_auditor_llm.py
**Functions:**
- `def _load_rotation_state()`
- `def _save_rotation_state(state)`
- `def _list_candidate_files()`
- `def select_files_for_today()`
- `def audit_file_with_groq(file_path)`
- `def run_code_audit(send_telegram)`
- `def _send_audit_summary_telegram(now, files, critical_findings, high_findings, total_findings, log_filename)`
- `def score_file(path)`

### config.py
_(no top-level classes/functions found)_

### data_fetcher.py
**Functions:**
- `def _load_gate_symbols()`
- `def _to_gate_symbol(symbol)`
- `def fetch_ohlcv(symbol, timeframe, limit)`
- `def _fetch_cmc_data()`
- `def get_cmc_info(symbol)`
- `def fetch_symbols(min_volume_usdt)`
- `def get_top_gainers_losers(top_n)`
- `def get_volume_spike_pairs(top_n)`
- `def get_new_listings(min_volume_usdt)`
- `def fetch_batch(symbols, timeframe, delay)`
- `async def _get_session()`
- `async def async_fetch_ohlcv(symbol, timeframe, limit)`
- `async def close_async_session()`
- `def get_realtime_price(symbol)`
- `def _fetch(sym)`

### database.py
**Functions:**
- `def get_conn()`
- `def init_db()`
- `def save_signal(s)`
- `def get_recent_signals(limit)`
- `def get_today_signals()`
- `def update_signal_result(symbol, signal, entry, exit_price)`
- `def get_realtime_winrate(symbol)`
- `def cleanup_old_data(days)`

### divergence_detector.py
**Functions:**
- `def get_rsi(close, period)`
- `def get_macd(close, fast, slow, signal)`
- `def detect_divergence(df, lookback)`
- `def get_divergence_score(df, signal)`

### dynamic_penalty.py
**Functions:**
- `def get_session(hour)`
- `def _load_analysis()`
- `def load_rules()`
- `def get_dynamic_penalty(signal, hour, regime)`
- `def get_pair_penalty(symbol)`
- `def get_penalty_summary()`

### email_reporter.py
**Functions:**
- `def _badge(signal)`
- `def _bar(score)`
- `def build_html(signals, ai_analysis)`
- `def send_email_report(signals, ai_analysis)`

### exit_monitor.py
**Functions:**
- `def _save_trades()`
- `def _load_trades()`
- `def add_trade(signal)`
- `def get_current_price(symbol)`
- `def check_exits(send_alert_fn)`
- `def start_exit_monitor(send_alert_fn, interval)`
- `def _run()`

### export_dashboard_data.py
**Functions:**
- `def safe_round(v, n)`
- `def export_virtual_trades(db_path)`
- `def export_signals(db_path, limit)`
- `def export_performance(db_path)`
- `def export_risk_state(path)`
- `def compute_summary(trades)`
- `def main()`

### indicators.py
**Functions:**
- `def rsi_wilder(close, period)`
- `def atr(df, period)`
- `def bollinger_bands(close, period, std_dev)`
- `def stochastic(df, k_period, d_period)`
- `def adx(df, period)`
- `def volume_analysis(df, period)`
- `def rsi_divergence(close, rsi, lookback)`
- `def macd_divergence(close, macd_hist, lookback)`
- `def support_resistance(df, window)`
- `def candle_patterns(df)`
- `def bb_squeeze_score(bb_width, lookback)`
- `def volume_dry_up(vol_ratio, window)`
- `def volume_expansion(vol_ratio, window)`
- `def macd_momentum_building(macd_hist)`
- `def rsi_pre_signal(rsi)`
- `def price_compression(df, window)`
- `def ema_convergence(ema9, ema20, ema50)`
- `def stoch_pre_cross(stoch_k, stoch_d)`
- `def higher_low_detection(df, window)`
- `def institutional_ai_v4(df)`
- `def _vwap_deviation(df)`
- `def _cvd_proxy(df)`
- `def _absorption_detection(df, vol_ratio, atr_pct_threshold)`
- `def _multi_timeframe_confluence(df, df_htf)`
- `def institutional_ai_v7(df, df_htf)`
- `def get_institutional_summary_v7(last_row)`
- `def _g(key, default)`

### institutional_v7_addon.py
**Functions:**
- `def _vwap_deviation(df)`
- `def _cvd_proxy(df)`
- `def _absorption_detection(df, vol_ratio, atr_pct_threshold)`
- `def _multi_timeframe_confluence(df, df_htf)`
- `def institutional_ai_v7(df, df_htf)`
- `def get_institutional_summary_v7(last_row)`
- `def _g(key, default)`

### liquidity_filter.py
**Functions:**
- `def _get_price(symbol)`
- `def _get_vol24(symbol)`
- `def check_liquidity(symbol, ob_features)`
- `def liquidity_score_adj(liq_data)`

### logger_config.py
**Functions:**
- `def _wib_time()`
- `def setup_logging(level)`
- `def get_logger(name)`

### main.py
**Functions:**
- `def _check_single_instance()`
- `def _release_lock()`
- `def _wib_converter()`
- `def filter_correlated_signals(signals, max_total, max_same_direction)`
- `def calculate_correlation_exposure(signals)`
- `def calculate_position_sizes(signals, total_risk_capital, min_size)`
- `def get_regime_risk_multiplier(market_context)`
- `def apply_regime_risk_adjustment(positions, market_context)`
- `def _build_cooldown_info()`
- `def job_scan()`
- `def job_daily_report()`
- `def job_weekly_report()`
- `def job_health_check()`
- `def job_system_health_check()`
- `def job_code_audit()`
- `def run_startup_backtest(send_telegram)`
- `def main()`
- `def _cmd_loop()`

### market_context.py
**Functions:**
- `def get_fear_greed()`
- `def get_funding_rates(symbols)`
- `def get_funding_rate(symbol)`
- `def get_btc_trend()`
- `def get_market_context()`
- `def get_btc_change_pct()`
- `def is_btc_dump(threshold)`
- `def is_btc_pump(threshold)`
- `def detect_market_regime(symbol, timeframe)`
- `def get_global_regime(symbols, timeframe)`

### module_auditor.py
**Functions:**
- `def get_conn()`
- `def get_last_audited_id()`
- `def save_last_audited_id(trade_id)`
- `def fetch_trades_since(last_id)`
- `def fetch_balance()`
- `def analyse_module(trades, module, cols)`
- `def analyse_regime(trades)`
- `def analyse_timeframe(trades)`
- `def analyse_hour(trades)`
- `def build_report(trades, batch_num)`
- `def run_audit(force)`
- `def watch_mode(check_interval_sec)`
- `def stats(group)`

### monitor_trades.py
**Functions:**
- `def monitor()`

### orderbook_features.py
**Functions:**
- `def _fetch_orderbook(symbol, depth)`
- `def _fetch_funding(symbol)`
- `def get_orderbook_features(symbol)`
- `def ob_score_adjustment(ob_features, signal)`

### patch_dashboard.py
_(no top-level classes/functions found)_

### patch_timezone_wib.py
**Functions:**
- `def patch_bot_auditor()`
- `def patch_database()`
- `def patch_api_server()`

### query.py
_(no top-level classes/functions found)_

### retest_filter.py
**Functions:**
- `def is_retest(df, signal, tolerance)`
- `def get_retest_score(df, signal)`

### risk_manager.py
**Classes:**
- `class RiskState()`
**Functions:**
- `def kelly_criterion(win_rate_pct, avg_win_pct, avg_loss_pct)`
- `def check_risk_approval(symbol, timeframe, signal, entry, sl, win_rate, avg_pnl, wr_is_default, similar_cases)`
- `def record_trade_result(symbol, timeframe, signal, pnl_usdt, win)`
- `def open_position(symbol, timeframe, signal, risk_pct)`
- `def reset_positions()`
- `def get_risk_status()`
- `def resume_trading(manual)`
- `def print_risk_status()`
- `def __init__(self)`
- `def _load(self)`
- `def save(self)`
- `def reset_daily(self)`
- `def update_balance(self, pnl_usdt, win)`
- `def current_drawdown_pct(self)`
- `def portfolio_heat(self)`
- `def add_position(self, key, risk_pct)`
- `def remove_position(self, key)`
- `def reset_positions(self)`

### scanner.py
**Functions:**
- `def _init_cooldown_table()`
- `def _load_cooldown_state()`
- `def _save_cooldown_state(key, signal_type, last_time)`
- `def get_and_reset_sr_guard_log()`
- `def _cast_df(df)`
- `def _safe(val, default)`
- `def _get_macd_cross(last, prev)`
- `def _get_ema_trend(last)`
- `def _calculate_tp_levels(entry, sl, signal, atr, regime, smc_score)`
- `def _calculate_position_size(entry, sl, risk_pct, balance)`
- `def _apply_rate_limit()`
- `def _cached_fetch(symbol, timeframe, limit)`
- `def _fetch_with_retry(symbol, timeframe, limit)`
- `def _is_duplicate(symbol, timeframe, signal_type, confidence)`
- `def _bump_block(reason)`
- `def _analyse_single(symbol, timeframe, min_score)`
- `def scan_all_fast(symbols, timeframe, min_score)`
- `def get_dynamic_threshold(ctx, signal_type)`
- `def _correlation_filter(signals, max_same_direction)`
- `def get_top_signals(results, top_n, threshold)`
- `def simple_correlation_filter(signals)`

### scanner_backup_20260624.py
**Functions:**
- `def _init_cooldown_table()`
- `def _load_cooldown_state()`
- `def _save_cooldown_state(key, signal_type, last_time)`
- `def _cast_df(df)`
- `def _safe(val, default)`
- `def _get_macd_cross(last, prev)`
- `def _get_ema_trend(last)`
- `def _calculate_tp_levels(entry, sl, signal, atr, regime, smc_score)`
- `def _calculate_position_size(entry, sl, risk_pct, balance)`
- `def _apply_rate_limit()`
- `def _cached_fetch(symbol, timeframe, limit)`
- `def _fetch_with_retry(symbol, timeframe, limit)`
- `def _is_duplicate(symbol, timeframe, signal_type, confidence)`
- `def _analyse_single(symbol, timeframe, min_score)`
- `def scan_all_fast(symbols, timeframe, min_score)`
- `def get_dynamic_threshold(ctx, signal_type)`
- `def _correlation_filter(signals, max_same_direction)`
- `def get_top_signals(results, top_n, threshold)`
- `def simple_correlation_filter(signals)`

### scanner_cooldown.py
**Functions:**
- `def init_db()`
- `def load_state()`
- `def _save(key, signal_type, last_time)`
- `def is_duplicate(symbol, timeframe, signal_type, confidence)`
- `def reset(symbol, timeframe)`
- `def get_state_snapshot()`

### scanner_fetcher.py
**Functions:**
- `def cast_df(df)`
- `def safe_float(val, default)`
- `def apply_rate_limit()`
- `def cached_fetch(symbol, timeframe, limit)`
- `def fetch_with_retry(symbol, timeframe, limit)`
- `def get_indicator_cache(key)`
- `def set_indicator_cache(key, df, max_size)`
- `def clear_fetch_cache()`

### scanner_main_refactor.py
**Functions:**
- `def _get_win_rate(symbol, timeframe, signal, last, df)`
- `def _analyse_single(symbol, timeframe, min_score)`
- `def scan_all_fast(symbols, timeframes, min_score)`
- `def get_dynamic_threshold(ctx, signal_type)`
- `def _correlation_filter(signals, max_same_direction)`
- `def get_top_signals(results, top_n, threshold)`
- `def simple_correlation_filter(signals)`

### scanner_refactored.py
**Functions:**
- `def _get_win_rate(symbol, timeframe, signal, last, df)`
- `def _analyse_single(symbol, timeframe, min_score)`
- `def scan_all_fast(symbols, timeframes, min_score)`
- `def get_dynamic_threshold(ctx, signal_type)`
- `def _correlation_filter(signals, max_same_direction)`
- `def get_top_signals(results, top_n, threshold)`
- `def simple_correlation_filter(signals)`

### scanner_signals.py
**Functions:**
- `def _safe(val, default)`
- `def calculate_tp_levels(entry, sl, signal, atr, regime, smc_score)`
- `def calculate_position_size(entry, sl, risk_pct, balance)`
- `def get_macd_cross(last, prev)`
- `def get_ema_trend(last)`
- `def get_volume_label(vol_ratio)`
- `def get_bb_position(bb_pct)`
- `def get_candle_patterns(last)`
- `def calculate_rr_ratio(entry, sl, tp1, tp2, tp3)`
- `def calculate_trailing_stop(entry, atr, signal)`

### self_learning.py
**Functions:**
- `def should_retrain(retrain_every_n)`
- `def get_current_auc()`
- `def retrain_with_protection()`
- `def run_self_learning(retrain_every_n)`

### send_dashboard_email.py
**Functions:**
- `def main()`

### smart_zone_engine.py
**Functions:**
- `def detect_fvg(df)`
- `def detect_liquidity_sweep(df, lookback)`
- `def detect_market_structure(df)`
- `def get_fvg_score(df, signal)`
- `def get_smc_analysis(df, signal)`

### smc_scorer.py
**Functions:**
- `def smc_confidence(df, signal)`
- `def format_smc_report(result, symbol, signal)`

### smc_trade_counter.py
**Classes:**
- `class SMCTradeCounter()`
**Functions:**
- `def get_smc_counter()`
- `def __init__(self, db_path, threshold)`
- `def _init_db(self)`
- `def get_smc_count(self)`
- `def record_trade(self, symbol, timeframe, signal_type, smc_score, has_smc)`
- `def _trigger_retrain(self, count)`
- `def _run_retrain(self)`
- `def _log_retrain(self, count, status)`
- `def get_status(self)`

### system_health_auditor.py
**Functions:**
- `def check_duplicate_process()`
- `def check_log_health()`
- `def check_database_integrity()`
- `def check_system_resources()`
- `def check_process_uptime()`
- `def _format_duration(td)`
- `def check_signal_to_trade_ratio()`
- `def run_system_health_check(send_telegram)`

### telegram_sender.py
**Functions:**
- `def should_send_signal(symbol, signal, score)`
- `def _send(text)`
- `def _chunks(text, limit)`
- `def fmt_price(val)`
- `def _fmt_smc(s)`
- `def get_alert_level(s)`
- `def format_signal(s)`
- `def send_signal(signal)`
- `def send_top_signals(signals, delay)`
- `def send_daily_report(signals, ai_analysis)`
- `def send_test_message()`
- `def send_alert(message)`
- `def get_updates()`
- `def handle_commands(scan_fn)`

### test_alert_level.py
_(no top-level classes/functions found)_

### trade_analyzer.py
**Functions:**
- `def load_trades()`
- `def win_rate(df)`
- `def profit_factor(df)`
- `def avg_rr(df)`
- `def max_drawdown(df)`
- `def session_label(hour)`
- `def analyze()`
- `def print_report(result)`
- `def analyze_regime(df)`
- `def build_penalty_rules(df)`

### trend_filter.py
**Functions:**
- `def get_ema(series, period)`
- `def get_adx(df, period)`
- `def analyze_trend(df, timeframe)`
- `def is_trend_aligned(signal, trend_info)`
- `def get_trend_score(df, signal)`

### validators.py
**Functions:**
- `def clamp(value, min_val, max_val, name)`
- `def validate_score(score, name)`
- `def validate_price(price, name)`
- `def validate_pct(pct, name)`
- `def validate_signal_dict(s)`
- `def validate_trade_params(entry, sl, tp1, signal)`

### virtual_trader.py
**Functions:**
- `def is_duplicate_position(symbol, timeframe, signal)`
- `def init_virtual_db()`
- `def get_balance()`
- `def add_virtual_trade(signal)`
- `def close_virtual_trade(symbol, timeframe, signal, pnl_pct)`
- `def get_summary()`
- `def send_virtual_summary(send_alert_fn)`

### volume_filter.py
**Functions:**
- `def is_doji(df, threshold)`
- `def is_impulsive_candle(df, multiplier)`
- `def get_volume_ratio(df, period)`
- `def analyze_volume(df, signal)`
- `def get_volume_score(df, signal)`

### volume_profile.py
**Functions:**
- `def _fetch_trades(symbol, limit)`
- `def get_volume_profile(symbol)`
- `def _calc_vp_adj(vp)`
- `def vp_score_adjustment(vp, signal)`

### win_rate_predictor.py
**Functions:**
- `def _normalize_features(df)`
- `def _weighted_distance(row_a, row_b)`
- `def _simulate_outcome(df, signal_idx, signal, atr)`
- `def predict_win_rate(symbol, timeframe, signal, current_features, df_cached)`
- `def _default_prediction(reason)`

### xgb_trainer.py
**Classes:**
- `class XGBTrainer()`
**Functions:**
- `def load_trades(db_path, min_trades)`
- `def __init__(self)`
- `def train(self, db_path)`
- `def predict(self, features)`

### zone_detector.py
**Functions:**
- `def detect_zones(df, lookback)`
- `def _score_zones(zones, closes, zone_type)`
- `def get_zone_score(df, signal)`
