import time, random
from funding_arb.db import SessionLocal
from funding_arb.init_db import init_db
from funding_arb.data.exchanges import BinanceUSDM_Public
from funding_arb.exec.baseline import Intent, simulate_fill
from funding_arb.exec.outcome_log import log_outcome

def main():
    init_db()
    ex = BinanceUSDM_Public()
    symbol = "BTC/USDT"
    print("Paper-executing intents for ~5 seconds...")

    t_end = time.time() + 5
    while time.time() < t_end:
        lob = ex.fetch_lob(symbol, depth=5)

        # randomize side and action for demo (we just want data in DB)
        side = random.choice(["buy", "sell"])
        action = random.choice([0, 1, 2, 3])  # maker_inside, edge, taker, wait
        intent = Intent(symbol=symbol, side=side, qty=100.0, deadline_ms=500)

        sim = simulate_fill(action, intent, lob, int(time.time() * 1000))
        if sim:
            with SessionLocal() as s:
                log_outcome(s, symbol, action, side, sim)
                s.commit()

        time.sleep(0.25)

    print("Done. Logged some exec_outcomes.")

if __name__ == "__main__":
    main()