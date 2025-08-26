import time
from dataclasses import dataclass

@dataclass
class Intent:
    symbol: str
    side: str       # "buy" or "sell"
    qty: float      # notional units in quote, simplified
    deadline_ms: int = 1000  # must fill within 1s or we cross

def best_prices(lob):
    bid = lob["bids"][0][0] if lob["bids"] else None
    ask = lob["asks"][0][0] if lob["asks"] else None
    mid = (bid + ask) / 2.0 if bid and ask else None
    return bid, ask, mid

def simulate_fill(action:int, intent: Intent, lob, start_ts_ms:int):
    """
    Simulate execution cost vs current LOB.
    action: 0 maker_inside, 1 post_only_edge, 2 taker_now, 3 wait
    - maker_inside: place post-only inside the spread; assume 50% chance to get hit within deadline
    - post_only_edge: post at best bid/ask; 30% chance to get hit within deadline
    - taker_now: cross immediately at best opp. price
    - wait: do nothing (small penalty)
    """
    bid, ask, mid = best_prices(lob)
    if not mid:
        return None

    fee_bps = 0.0  # paper mode for now
    time_to_fill_ms = 0
    partial_fill = 0

    if action == 2:  # taker_now
        # buy at ask, sell at bid
        if intent.side == "buy" and ask:
            fill_px = ask
        elif intent.side == "sell" and bid:
            fill_px = bid
        else:
            return None
    elif action in (0, 1):  # maker variants
        # assume probabilistic fill within deadline; if not filled, cross at deadline
        prob = 0.5 if action == 0 else 0.3
        filled_maker = (time.time_ns() % 1000) / 1000.0 < prob  # pseudo randomness
        if filled_maker:
            # maker price a tick inside for maker_inside; at edge for post_only_edge
            if intent.side == "buy":
                # maker buy posts below ask
                px = ask - (ask - bid) * (0.5 if action == 0 else 0.0)
            else:
                # maker sell posts above bid
                px = bid + (ask - bid) * (0.5 if action == 0 else 0.0)
            fill_px = px
            time_to_fill_ms = min(intent.deadline_ms, 250)
        else:
            # missed maker fill, cross at deadline
            time_to_fill_ms = intent.deadline_ms
            if intent.side == "buy" and ask:
                fill_px = ask
            elif intent.side == "sell" and bid:
                fill_px = bid
            else:
                return None
    elif action == 3:  # wait
        # no fill; assign a small penalty later via realized_cost calc
        fill_px = None
    else:
        return None

    # benchmark = mid at decision time
    bench_mid_px = mid

    if fill_px is None:
        # waiting: penalize tiny amount (e.g., 0.1 bps)
        realized_cost_bps = 0.1
        return {
            "fill_px": bench_mid_px,  # treat as no improvement
            "bench_mid_px": bench_mid_px,
            "fee_bps": fee_bps,
            "partial_fill": partial_fill,
            "time_to_fill_ms": 250,
            "realized_cost_bps": realized_cost_bps,
        }

    # side-adjusted execution cost in bps (buy wants lower than mid, sell wants higher than mid)
    side = intent.side
    if side == "buy":
        impact = (fill_px - bench_mid_px) / bench_mid_px
    else:
        impact = (bench_mid_px - fill_px) / bench_mid_px
    realized_cost_bps = impact * 1e4 + fee_bps

    return {
        "fill_px": float(fill_px),
        "bench_mid_px": float(bench_mid_px),
        "fee_bps": float(fee_bps),
        "partial_fill": partial_fill,
        "time_to_fill_ms": int(time_to_fill_ms),
        "realized_cost_bps": float(realized_cost_bps),
    }