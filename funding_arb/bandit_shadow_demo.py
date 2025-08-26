import time, json
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from funding_arb.init_db import init_db
from funding_arb.db import SessionLocal
from funding_arb.data.exchanges import BinanceUSDM_Public
from funding_arb.exec.baseline import Intent, simulate_fill, best_prices
from funding_arb.models import BanditShadow
from funding_arb.ml.features import FeatureBuilder
from funding_arb.ml.bandit import LinTS

def as_vec(feats) -> np.ndarray:
    # order must match features you return
    x = np.array([
        feats.spread_bp,
        feats.mid_return_1s,
        feats.mid_return_5s,
        feats.vol_proxy_5s,
        feats.depth_imb_top5,
        feats.last_action,
        feats.time_of_day_sin,
        feats.time_of_day_cos,
    ], dtype=float).reshape(-1, 1)
    # normalize a bit to avoid huge scales
    x[0] /= 10.0       # spread
    x[1] /= 10.0       # r1s
    x[2] /= 10.0       # r5s
    x[3] /= 10.0       # vol proxy
    return x

def main():
    init_db()
    ex = BinanceUSDM_Public()
    fb = FeatureBuilder()

    # 4 actions: 0 maker_inside, 1 post_only_edge, 2 taker_now, 3 wait
    bandit = LinTS(d=8, actions=[0,1,2,3])

    symbol = "BTC/USDT"
    deadline_ms = 500
    baseline_action = 2  # we execute "taker_now" for stability
    last_action = 0

    print("Running bandit in SHADOW mode for ~8 seconds...")
    t_end = time.time() + 8
    n_updates = 0

    while time.time() < t_end:
        lob = ex.fetch_lob(symbol, depth=5)

        # build features
        bid_px = [px for px, _ in lob["bids"]]
        ask_px = [px for px, _ in lob["asks"]]
        bid_sz = [sz for _, sz in lob["bids"]]
        ask_sz = [sz for _, sz in lob["asks"]]
        ts_ms = int(time.time() * 1000)

        feats = fb.push_and_compute(ts_ms, bid_px, ask_px, bid_sz, ask_sz, last_action=last_action)
        if not feats:
            time.sleep(0.25); continue

        x = as_vec(feats)
        action_bandit = bandit.choose(x)

        # execute BASELINE (taker_now), simulate fill & cost
        intent = Intent(symbol=symbol, side="buy", qty=100.0, deadline_ms=deadline_ms)
        sim = simulate_fill(baseline_action, intent, lob, ts_ms)
        if sim is None:
            time.sleep(0.25); continue

        realized_cost_bps = float(sim["realized_cost_bps"])
        reward = -realized_cost_bps  # we want to minimize cost

        # online update
        bandit.update(action_bandit, x, reward)
        n_updates += 1
        last_action = baseline_action  # last action we actually took

        # log to DB
        with SessionLocal() as s:
            s.add(BanditShadow(
                ts_ms=ts_ms,
                symbol=symbol,
                action_bandit=action_bandit,
                action_baseline=baseline_action,
                realized_cost_bps=realized_cost_bps,
            ))
            s.commit()

        time.sleep(0.25)

    print(f"Done. Shadow updates: {n_updates}")

if __name__ == "__main__":
    main()