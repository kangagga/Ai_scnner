import sqlite3
from data_fetcher import get_realtime_price

# Threshold jarak ke TP/SL buat dianggap "dekat" (dalam persen)
ALERT_THRESHOLD = 1.0  # %

def monitor():
    conn = sqlite3.connect('virtual_trading.db')
    cur = conn.cursor()
    cur.execute("SELECT id, symbol, signal, entry, sl, tp1, tp2, tp3 FROM virtual_trades WHERE closed=0 ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("Tidak ada open trade.")
        return

    print(f"{'SYMBOL':15} {'SIGNAL':6} {'NOW':12} {'PNL%':9} {'STATUS'}")
    print("-" * 70)

    for id_, symbol, signal, entry, sl, tp1, tp2, tp3 in rows:
        try:
            price = get_realtime_price(symbol)
            if not price:
                print(f"{symbol:15} no price data")
                continue

            if signal == 'BUY':
                pnl_pct = (price - entry) / entry * 100
                dist_sl = (price - sl) / price * 100
                dist_tp1 = (tp1 - price) / price * 100
            else:
                pnl_pct = (entry - price) / entry * 100
                dist_sl = (sl - price) / price * 100
                dist_tp1 = (price - tp1) / price * 100

            status = "🟢 PROFIT" if pnl_pct > 0 else "🔴 LOSS"
            alert = ""
            if abs(dist_tp1) <= ALERT_THRESHOLD:
                alert = " ⚠️ DEKAT TP1!"
            if abs(dist_sl) <= ALERT_THRESHOLD:
                alert = " ⚠️ DEKAT SL!"

            print(f"{symbol:15} {signal:6} {price:<12} {pnl_pct:+.2f}%   {status}{alert}")
        except Exception as e:
            print(f"{symbol}: error - {e}")

if __name__ == "__main__":
    monitor()
