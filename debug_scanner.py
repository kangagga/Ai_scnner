import logging
logging.basicConfig(level=logging.DEBUG)

from scanner import _analyse_single

# Test langsung pair yang tadi muncul SELL di indicators
for pair in [("ETHUSDT","1h"), ("SOLUSDT","1h"), ("BNBUSDT","1h")]:
    sym, tf = pair
    print(f"\n{'='*40}")
    print(f"Testing {sym}/{tf}")
    result = _analyse_single(sym, tf, min_score=0)
    if result:
        print(f"✅ LOLOS: signal={result['signal']} conf={result['confidence']}")
    else:
        print(f"❌ DIBLOKIR — cek log DEBUG di atas")
