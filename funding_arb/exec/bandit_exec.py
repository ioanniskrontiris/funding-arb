import time
import numpy as np
from funding_arb.exec.baseline import Intent, simulate_fill
from funding_arb.models import ExecOutcome
from funding_arb.ml.bandit import LinTS
from funding_arb.ml.features import FeatureBuilder

class BanditExecutor:
    def __init__(self):
        self.fb = FeatureBuilder()
        self.bandit = LinTS(d=8, actions=[0,1,2,3])
        self.last_action = 0

    def _as_vec(self, feats):
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
        # normalize
        x[0] /= 10.0; x[1] /= 10.0; x[2] /= 10.0; x[3] /= 10.0
        return x

    def decide_and_execute(self, lob, symbol, side="buy", deadline_ms=500):
        bid_px = [px for px, _ in lob["bids"]]
        ask_px = [px for px, _ in lob["asks"]]
        bid_sz = [sz for _, sz in lob["bids"]]
        ask_sz = [sz for _, sz in lob["asks"]]
        ts_ms = int(time.time() * 1000)

        feats = self.fb.push_and_compute(ts_ms, bid_px, ask_px, bid_sz, ask_sz, last_action=self.last_action)
        if not feats:
            return None, None, None  # no features yet

        x = self._as_vec(feats)
        action = self.bandit.choose(x)

        intent = Intent(symbol=symbol, side=side, qty=100.0, deadline_ms=deadline_ms)
        sim = simulate_fill(action, intent, lob, ts_ms)
        if sim is None:
            return None, None, None

        # reward: negative cost
        reward = -sim["realized_cost_bps"]
        self.bandit.update(action, x, reward)
        self.last_action = action

        # return outcome row
        return action, ts_ms, sim