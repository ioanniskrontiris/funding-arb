import time
from .data.exchanges import BinanceUSDM_Public
from .db import SessionLocal
from .init_db import init_db
from .persist import save_lob

def run():
    init_db()
    ex = BinanceUSDM_Public()
    symbol = "BTC/USDT"
    interval_s = 0.25  # 250 ms
    depth = 5
    print("MAIN MODULE LOADED")



    print("Streaming LOB every 250 ms (Ctrl+C to stop)...")
    while True:
        lob = ex.fetch_lob(symbol, depth=depth)
        print(f"{symbol} bids[0]={lob['bids'][0] if lob['bids'] else None} "
              f"asks[0]={lob['asks'][0] if lob['asks'] else None} "
              f"latency={lob['latency_ms']}ms")
        with SessionLocal() as s:
            save_lob(s, symbol, lob["bids"], lob["asks"], lob["latency_ms"])
            s.commit()
        time.sleep(interval_s)

if __name__ == "__main__":
    run()