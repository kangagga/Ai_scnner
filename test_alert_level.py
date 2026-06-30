from telegram_sender import get_alert_level

cases = [
    ("SMC strong + wr0",   dict(score=70, win_rate=0,  smc_data=dict(score=75, valid=True))),
    ("SMC strong + wr60",  dict(score=70, win_rate=60, smc_data=dict(score=75, valid=True))),
    ("SMC siap entry",     dict(score=60, win_rate=0,  smc_data=dict(score=55, valid=True))),
    ("SMC watchlist",      dict(score=48, win_rate=80, smc_data=dict(score=20, valid=False))),
    ("SMC monitor",        dict(score=30, win_rate=80, smc_data=dict(score=20, valid=False))),
    ("no SMC eksekusi",    dict(score=70, win_rate=50, smc_data={})),
    ("no SMC siap entry",  dict(score=58, win_rate=36, smc_data={})),
    ("no SMC watchlist",   dict(score=46, win_rate=0,  smc_data={})),
    ("no SMC monitor",     dict(score=20, win_rate=0,  smc_data={})),
]

for label, sig in cases:
    level = get_alert_level(sig)
    would_trade = ("EKSEKUSI" in level) or ("SIAP ENTRY" in level)
    print(f"{label:20s} -> {level:35s} | would_trade={would_trade}")
