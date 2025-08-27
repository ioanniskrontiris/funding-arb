import time
from funding_arb.init_db import init_db
from funding_arb.db import SessionLocal
from funding_arb.data.exchanges import BinanceUSDM_Public
from funding_arb.exec.bandit_exec import BanditExecutor
from funding_arb.models import ExecOutcome

def main():
    init_db()
    ex = BinanceUSDM_Public()
    executor = BanditExecutor()
    symbol = "BTC/USDT"

    print("Running bandit LIVE mode (simulated fills) for ~8s...")
    t_end = time.time() + 8

    while time.time() < t_end:
        lob = ex.fetch_lob(symbol, depth=5)
        action, ts_ms, sim = executor.decide_and_execute(lob, symbol, side="buy")
        if sim:
            with SessionLocal() as s:
                s.add(ExecOutcome(
                    ts_ms=ts_ms,
                    symbol=symbol,
                    action=action,
                    side="buy",
                    fill_px=sim["fill_px"],
                    bench_mid_px=sim["bench_mid_px"],
                    realized_cost_bps=sim["realized_cost_bps"],
                    fee_bps=sim["fee_bps"],
                    partial_fill=sim["partial_fill"],
                    time_to_fill_ms=sim["time_to_fill_ms"],
                ))
                s.commit()
        time.sleep(0.25)

    print("Done. Outcomes logged to exec_outcomes.")

if __name__ == "__main__":
    main()