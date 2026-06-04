from data_fetcher import fetch_ohlcv
from indicators import institutional_ai_v4

for symbol in ["BTCUSDT", "XRPUSDT"]:
    df = fetch_ohlcv(symbol, "1h", limit=300)
    df = institutional_ai_v4(df)
    last = df.iloc[-1]
    print(f"\n{symbol}:")
    print(f"  trend_down     : {last['trend_down']}")
    print(f"  trend_down_weak: {last['trend_down_weak']}")
    print(f"  strong_trend   : {last['strong_trend']}")
    print(f"  macd_hist      : {last['macd_hist']:.4f}")
    print(f"  stoch_k        : {last['stoch_k']:.1f}")
    print(f"  stoch_d        : {last['stoch_d']:.1f}")
    print(f"  obv_bull       : {last['obv_bull']}")
    print(f"  near_resistance: {last['near_resistance']}")
    print(f"  rsi_div        : {last['rsi_div']}")
    print(f"  bear_engulf    : {last['bear_engulf']}")
    print(f"  shooting_star  : {last['shooting_star']}")
    print(f"  reversal_bear  : {last['reversal_bear']}")
