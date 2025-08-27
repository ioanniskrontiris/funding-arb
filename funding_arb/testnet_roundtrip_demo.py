import time
from dotenv import load_dotenv
from funding_arb.exec.bandit_exec import BanditExecutor
from funding_arb.exec.real import BinanceUSDM_TestnetTrader
from funding_arb.db import SessionLocal
from funding_arb.models import ExecOutcome

load_dotenv()

def pick_symbol(ex) -> str:
    for s in ["ETH/USDT:USDT", "BTC/USDT:USDT"]:
        if s in ex.symbols: return s
    for s in ex.symbols:
        if s.endswith(":USDT"): return s
    return ex.symbols[0]

def est_min_notional(ex, symbol: str) -> float:
    m = ex.market(symbol)
    min_amt = (m.get("limits", {}).get("amount", {}) or {}).get("min") or 0.0
    ob = ex.fetch_order_book(symbol, limit=5)
    bids, asks = ob.get("bids", []), ob.get("asks", [])
    mid = (bids[0][0] + asks[0][0]) / 2.0 if bids and asks else 0.0
    approx = float(min_amt) * float(mid) if mid else 0.0
    return max(20.0, approx)

def log_exec(ts_ms, symbol, action, side, fill, mid, cost_bps):
    from funding_arb.models import ExecOutcome
    with SessionLocal() as s:
        s.add(ExecOutcome(
            ts_ms=ts_ms, symbol=symbol, action=action, side=side,
            fill_px=float(fill), bench_mid_px=float(mid),
            realized_cost_bps=float(cost_bps), fee_bps=0.0,
            partial_fill=0, time_to_fill_ms=0,
        ))
        s.commit()

def main():
    print("TESTNET ROUND-TRIP — open then reduce-only close each cycle")
    trader = BinanceUSDM_TestnetTrader()
    bandit = BanditExecutor()

    symbol = pick_symbol(trader.ex)
    print("Using:", symbol)
    trader.set_leverage(symbol, 1)

    floor = est_min_notional(trader.ex, symbol)
    notional = max(25.0, floor * 1.05)
    print(f"[info] notional ≈ {notional:.2f} USDT")

    deadline_ms = 800
    end_time = time.time() + 20

    while time.time() < end_time:
        ob = trader.ex.fetch_order_book(symbol, limit=5)
        bids, asks = ob.get("bids", []), ob.get("asks", [])
        if not (bids and asks):
            time.sleep(0.25); continue
        lob = {"bids": bids, "asks": asks, "latency_ms": 0}

        # OPEN (let bandit pick; if wait=3, map to taker 2 for demo)
        action, ts_ms, sim = bandit.decide_and_execute(lob, symbol, side="buy", deadline_ms=deadline_ms)
        if action is None:
            time.sleep(0.25); continue
        if action == 3: action = 2

        real_open = trader.execute_action(action, symbol, "buy", notional, deadline_ms=deadline_ms, reduce_only=False)
        if not (real_open.get("price") and real_open.get("mid")):
            print("open failed:", real_open.get("status")); continue

        mid_o, fill_o = real_open["mid"], real_open["price"]
        cost_o = (fill_o - mid_o) / mid_o * 1e4
        log_exec(ts_ms, symbol, action, "buy", fill_o, mid_o, cost_o)
        print(f"OPEN: action={action}, fill={fill_o:.6f}, mid={mid_o:.6f}, cost={cost_o:.2f} bps")

        # CLOSE immediately reduce-only (sell)
        real_close = trader.execute_action(2, symbol, "sell", notional, deadline_ms=deadline_ms, reduce_only=True)
        if not (real_close.get("price") and real_close.get("mid")):
            print("close failed:", real_close.get("status")); continue

        mid_c, fill_c = real_close["mid"], real_close["price"]
        cost_c = (mid_c - fill_c) / mid_c * 1e4  # for a sell, same sign convention (cost >0 = worse)
        log_exec(ts_ms+1, symbol, 2, "sell", fill_c, mid_c, cost_c)
        print(f"CLOSE: taker, fill={fill_c:.6f}, mid={mid_c:.6f}, cost={cost_c:.2f} bps")

        time.sleep(0.5)

    print("done.")

if __name__ == "__main__":
    main()