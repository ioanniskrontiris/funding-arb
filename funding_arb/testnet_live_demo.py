# funding_arb/testnet_live_demo.py
import time
from dotenv import load_dotenv

from funding_arb.exec.bandit_exec import BanditExecutor
from funding_arb.exec.real import BinanceUSDM_TestnetTrader
from funding_arb.db import SessionLocal
from funding_arb.models import ExecOutcome

load_dotenv()

def pick_symbol(ex) -> str:
    preferred = ["ETH/USDT:USDT", "BTC/USDT:USDT"]
    for sym in preferred:
        if sym in ex.symbols:
            return sym
    for sym in ex.symbols:
        if sym.endswith(":USDT"):
            return sym
    return ex.symbols[0]

def est_min_notional(ex, symbol: str) -> float:
    m = ex.market(symbol)
    min_amt = (m.get("limits", {}).get("amount", {}) or {}).get("min") or 0.0
    ob = ex.fetch_order_book(symbol, limit=5)
    bids, asks = ob.get("bids", []), ob.get("asks", [])
    mid = (bids and asks) and (bids[0][0] + asks[0][0]) / 2.0 or 0.0
    approx = float(min_amt) * float(mid) if mid else 0.0
    return max(20.0, approx)

def main():
    print("TESTNET LIVE (futures) — bandit chooses actions, real orders on testnet")
    trader = BinanceUSDM_TestnetTrader()
    bandit = BanditExecutor()

    symbol = pick_symbol(trader.ex)
    print("Using testnet symbol:", symbol)
    trader.set_leverage(symbol, leverage=1)

    floor = est_min_notional(trader.ex, symbol)
    notional = max(25.0, floor * 1.05)
    print(f"[info] using notional ≈ {notional:.2f} USDT (floor~{floor:.2f})")

    side = "buy"
    deadline_ms = 800
    end_time = time.time() + 20

    while time.time() < end_time:
        try:
            ob = trader.ex.fetch_order_book(symbol, limit=5)
        except Exception as e:
            print("order book error:", e)
            time.sleep(0.25)
            continue

        bids, asks = ob.get("bids", []), ob.get("asks", [])
        if not (bids and asks):
            time.sleep(0.25)
            continue

        lob = {"bids": bids, "asks": asks, "latency_ms": 0}
        action, ts_ms, sim = bandit.decide_and_execute(lob, symbol, side=side, deadline_ms=deadline_ms)
        if action is None:
            time.sleep(0.25)
            continue
        if action == 3:
            action = 2  # avoid noop in live demo

        real = trader.execute_action(action, symbol, side, notional, deadline_ms=deadline_ms, reduce_only=False)

        if real.get("price") is not None and real.get("mid") is not None:
            mid = real["mid"]; fill = real["price"]
            impact = (fill - mid) / mid if side == "buy" else (mid - fill) / mid
            cost_bps = impact * 1e4

            with SessionLocal() as s:
                s.add(ExecOutcome(
                    ts_ms=ts_ms, symbol=symbol, action=action, side=side,
                    fill_px=float(fill), bench_mid_px=float(mid),
                    realized_cost_bps=float(cost_bps), fee_bps=0.0,
                    partial_fill=0, time_to_fill_ms=deadline_ms,
                ))
                s.commit()

            print(f"LIVE order: sym={symbol}, action={action}, side={side}, "
                  f"fill={fill:.6f}, mid={mid:.6f}, cost={cost_bps:.3f} bps, status={real['status']}")
        else:
            print(f"LIVE order failed/ignored: status={real.get('status')}")

        time.sleep(0.25)

    print("Done testnet demo.")

if __name__ == "__main__":
    main()