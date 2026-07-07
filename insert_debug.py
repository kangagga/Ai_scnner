import re

with open('indicators.py', 'r') as f:
    content = f.read()

target = "    data['signal'] = \"NO TRADE\""

debug_code = '''    debug_pair = "ETHUSDT"
    if 'symbol' in data.columns:
        _mask = data['symbol'] == debug_pair
    else:
        _mask = [True] * len(data)
    if any(_mask):
        last = data[_mask].iloc[-1] if 'symbol' in data.columns else data.iloc[-1]
        print(f"=== DEBUG {debug_pair} ===")
        print(f"adx={last['adx']:.1f} rsi={last['rsi']:.1f} macd_hist={last['macd_hist']:.4f}")
        print(f"trend_up_weak={last['trend_up_weak']} trend_down_weak={last['trend_down_weak']}")
        print(f"trend_up={last['trend_up']} trend_down={last['trend_down']}")
        print(f"buy_combined={last['buy_combined']:.1f} sell_combined={last['sell_combined']:.1f}")
        print(f"rvol={last['rvol']:.2f} atr={last['atr']:.4f} atr_ma={last['atr_ma']:.4f}")
        print(f"market_regime={last['market_regime']}")
        print(f"fake_breakout={last['fake_breakout']} volume_exhaustion={last['volume_exhaustion']}")
        print(f"_fake_signal={_fake_signal[_mask].iloc[-1] if 'symbol' in data.columns else _fake_signal.iloc[-1]}")
        print(f"buy_momentum_cond={buy_momentum_cond[_mask].iloc[-1] if 'symbol' in data.columns else buy_momentum_cond.iloc[-1]}")
        print(f"buy_breakout_cond={buy_breakout_cond[_mask].iloc[-1] if 'symbol' in data.columns else buy_breakout_cond.iloc[-1]}")
        print(f"buy_setup_cond={buy_setup_cond[_mask].iloc[-1] if 'symbol' in data.columns else buy_setup_cond.iloc[-1]}")
        print(f"buy_confirm_cond={buy_confirm_cond[_mask].iloc[-1] if 'symbol' in data.columns else buy_confirm_cond.iloc[-1]}")

'''

if target not in content:
    print("❌ Baris target tidak ketemu persis. Cek ulang indentasi.")
else:
    content = content.replace(target, debug_code + target, 1)
    with open('indicators.py', 'w') as f:
        f.write(content)
    print("✅ Debug code berhasil disisipkan sebelum baris signal = NO TRADE")
