import time
from funding_arb.data.exchanges import BinanceUSDM_Public
from funding_arb.data.funding import FundingFeed, funding_per_day_from_8h
from funding_arb.strategy.funding_signal import FundingSignal, SignalConfig
from funding_arb.exec.bandit_exec import BanditExecutor
from funding_arb.paper.positions import PaperBook
from funding_arb.db import SessionLocal
from funding_arb.loggers import log_funding, log_signal, log_position
from funding_arb.risk.guards import RiskConfig, RiskState

def net_bps_day(
    funding_day: float,
    fee_bps: float = 0.2,
    slip_bps: float = 0.1,
    borrow_bps: float = 0.0,
):
    """Conservative net estimate of funding in bps/day."""
    return 1e4 * (funding_day - (fee_bps / 1e4) - (slip_bps / 1e4) - (borrow_bps / 1e4))

def main():
    print("Funding paper loop (bandit for execution decisions; paper positions) + RISK GUARDS")
    lob_ex = BinanceUSDM_Public()
    fund = FundingFeed()
    signal = FundingSignal(SignalConfig(open_threshold_bpsd=1.0, close_threshold_bpsd=0.5, min_persistence=1))
    book = PaperBook()
    exec_bandit = BanditExecutor()
    risk = RiskState(RiskConfig())  # defaults; tune later

    symbol = "BTC/USDT"
    notional = 1000.0  # pretend EUR≈USDT for now
    last_ts = time.time()
    last_status_ts = 0.0

    end_time = time.time() + 180  # ~3 minutes demo
    while time.time() < end_time:
        # 1) funding & net EV
        rate8h, _ = fund.funding_rate_8h(symbol)
        f_day = funding_per_day_from_8h(rate8h)
        bpsd = net_bps_day(f_day)

        # log funding tick
        with SessionLocal() as s:
            log_funding(s, symbol, rate8h, f_day, bpsd)
            s.commit()

        # 2) decide open/close
        decision, _ = signal.decide(bpsd)

        # log signal
        with SessionLocal() as s:
            log_signal(s, symbol, decision, bpsd)
            s.commit()

        # 3) get current LOB & let bandit pick execution (paper)
        # risk: record API outcome (success if we have both sides populated)
        try:
            lob = lob_ex.fetch_lob(symbol, depth=5)
            now_ms = int(time.time() * 1000)
            ok = bool(lob["bids"] and lob["asks"])
            risk.record_api(ok=ok, ts_ms=now_ms)
        except Exception:
            lob = {"bids": [], "asks": [], "latency_ms": 0}
            now_ms = int(time.time() * 1000)
            risk.record_api(ok=False, ts_ms=now_ms)

        # 4) accrue funding between ticks
        now = time.time()
        dt = now - last_ts
        last_ts = now
        if book.pos.is_open:
            book.accrue_funding(bps_per_day=bpsd, seconds=dt)

        # 5) RISK CHECK (before any open/close)
        est_pnl = book.realized_pnl_usdt()
        halt, reason = risk.must_halt(
            notional_usdt=book.pos.notional_usdt if book.pos.is_open else notional,
            est_pnl_usdt=est_pnl,
            now_ms=now_ms,
        )
        if halt:
            print(f"RISK HALT: {reason} → flatten & exit loop")
            if book.pos.is_open:
                # simulate close via bandit (sell)
                chosen, ts_ms, sim = exec_bandit.decide_and_execute(lob, symbol, side="sell")
                if sim:
                    print(f"FLATTEN: bandit_action={chosen}, cost={sim['realized_cost_bps']:.3f} bps")
                book.close()
            break

        # 6) act on decision
        if decision == "OPEN" and not book.pos.is_open:
            # simulate open (buy)
            chosen, ts_ms, sim = exec_bandit.decide_and_execute(lob, symbol, side="buy")
            if sim:
                print(f"OPEN: bpsd={bpsd:.2f}, bandit_action={chosen}, cost={sim['realized_cost_bps']:.3f} bps")
            else:
                print("OPEN: no sim")
            book.open_delta_neutral(symbol, notional_usdt=notional)

        elif decision == "CLOSE" and book.pos.is_open:
            # simulate close (sell)
            chosen, ts_ms, sim = exec_bandit.decide_and_execute(lob, symbol, side="sell")
            if sim:
                print(f"CLOSE: bpsd={bpsd:.2f}, bandit_action={chosen}, cost={sim['realized_cost_bps']:.3f} bps")
            else:
                print("CLOSE: no sim")
            book.close()

        # 7) status + position snapshot once per second
        if now - last_status_ts >= 1.0:
            print(
                f"status: open={book.pos.is_open}, "
                f"accrued={book.pos.accrued_funding_bps:.4f} bps, "
                f"est_pnl={book.realized_pnl_usdt():.6f} USDT"
            )
            with SessionLocal() as s:
                log_position(
                    s,
                    symbol,
                    book.pos.is_open,
                    book.pos.notional_usdt,
                    book.pos.accrued_funding_bps,
                    book.realized_pnl_usdt(),
                )
                s.commit()
            last_status_ts = now

        time.sleep(0.25)

    # final report
    print("\n=== SUMMARY ===")
    print(
        f"open={book.pos.is_open}, "
        f"accrued_funding={book.pos.accrued_funding_bps:.3f} bps, "
        f"est_pnl={book.realized_pnl_usdt():.4f} USDT"
    )

if __name__ == "__main__":
    main()