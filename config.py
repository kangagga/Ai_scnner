# ============================================================
#  config.py – Konfigurasi Bot Analisis Market
#  PERBAIKAN v2:
#  1. ACCOUNT_BALANCE & RISK_PER_TRADE dipindahkan ke sini
#     (tidak lagi hardcode di scanner.py & risk_manager.py)
# ============================================================

# Telegram
BOT_TOKEN   = "8676763268:AAH-qaC2uJBhzkbro0CC0Bgeli8nJ7CNNj4"
CHAT_ID     = "1029558875"

# Groq API
GROQ_API_KEY = "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"

# Gmail
EMAIL_SENDER    = "ranggazainalmahrez@gmail.com"
EMAIL_PASSWORD  = "lndw vpok kmfc jqpl"
EMAIL_RECEIVER  = "ranggazainalmahrez@gmail.com"

# Scanner settings
SCAN_INTERVAL     = 60        # interval scan dalam detik
MIN_SCORE         = 35        # minimal score indikator
SIGNAL_THRESHOLD  = 35        # minimal confidence untuk kirim sinyal
MAX_SIGNALS_PER_DAY = 50   # maksimal sinyal per hari

# Timeframes
TIMEFRAMES = ["15m", "1h", "4h"]

# Pair limit
PAIR_LIMIT = 100

# Risk management — [FIX] dipindahkan dari scanner.py & risk_manager.py
RISK_PER_TRADE   = 1.0        # % risiko per trade
ACCOUNT_BALANCE  = 1000.0     # saldo simulasi (USDT)

# Indikator
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9
RSI_PERIOD  = 14
VOLUME_MA   = 20

# Jadwal laporan harian
DAILY_REPORT_HOUR   = 0
DAILY_REPORT_MINUTE = 0

# Watchlist (100 crypto pair likuid)
WATCHLIST = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LTCUSDT",
    "BCHUSDT","ATOMUSDT","NEARUSDT","APTUSDT","SUIUSDT","INJUSDT","SEIUSDT","TIAUSDT","ICPUSDT","XLMUSDT",
    "ALGOUSDT","EGLDUSDT","VETUSDT","FTMUSDT","ONEUSDT",
    "UNIUSDT","AAVEUSDT","MKRUSDT","LDOUSDT","GMXUSDT","RUNEUSDT","CRVUSDT","SNXUSDT","COMPUSDT","DYDXUSDT",
    "YFIUSDT","BALUSDT","KAVAUSDT","SUSHIUSDT","1INCHUSDT",
    "ARBUSDT","OPUSDT","IMXUSDT","STRKUSDT","METISUSDT","LRCUSDT","SKLUSDT","STXUSDT",
    "FETUSDT","RENDERUSDT","WLDUSDT","AGIXUSDT","OCEANUSDT","TAOUSDT",
    "LINKUSDT","TRXUSDT","HBARUSDT","QNTUSDT","FILUSDT","ARUSDT","CELRUSDT","CFXUSDT","BANDUSDT","XTZUSDT",
    "DOGEUSDT","SHIBUSDT","PEPEUSDT","FLOKIUSDT","WIFUSDT","BONKUSDT",
    "AXSUSDT","SANDUSDT","MANAUSDT","GALAUSDT","GMTUSDT","ENJUSDT","CHRUSDT","ROSEUSDT",
    "JUPUSDT","ENAUSDT","NOTUSDT","ZROUSDT","EIGENUSDT","CATIUSDT","BOMEUSDT","BLURUSDT","TURBOUSDT","ILVUSDT",
    "OKBUSDT","BTTUSDT","HOTUSDT",
    "ETHBTC","BNBBTC","SOLBTC","XRPBTC","ADABTC","DOTBTC","AVAXBTC",
    # High volatility / trending
    "WUSDT","PYTHUSDT","JTOUSDT","MEMEUSDT","ACEUSDT","ALTUSDT","RONINUSDT",
    "PIXELUSDT","PORTALUSDT","STRKUSDT","DYMUSDT","AIUSDT","LPTUSDT",
    "ORDIUSDT","SATSUSDT","RATS1USDT","10000SATSUSDT",
    "MOVRUSDT","ZRXUSDT","UMAUSDT","API3USDT","ACHUSDT","HIGHUSDT",
    "MDTUSDT","ONGUSDT","FORTHUSDT","IDUSDT","AMBUSDT","CVXUSDT",
    "PENDLEUSDT","WLDUSDT","VANRYUSDT","AEVOUSDT","SAFEUSDT",
]

# Pastikan tepat 100
WATCHLIST = list(dict.fromkeys(WATCHLIST))[:150]
