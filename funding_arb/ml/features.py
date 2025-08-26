from dataclasses import dataclass
import math
from collections import deque

@dataclass
class ExecFeatures:
    spread_bp: float
    mid_return_1s: float
    mid_return_5s: float
    vol_proxy_5s: float
    depth_imb_top5: float
    last_action: int
    time_of_day_sin: float
    time_of_day_cos: float

class FeatureBuilder:
    """
    Builds live features from a stream of (ts_ms, bid_px[], ask_px[], bid_sz[], ask_sz[]).
    Keep minimal state in-memory.
    """
    def __init__(self):
        self.mids = deque(maxlen=50)   # ~12.5s at 250ms
        self.times = deque(maxlen=50)

    @staticmethod
    def _mid(bid_px0, ask_px0):
        return (bid_px0 + ask_px0) / 2.0

    @staticmethod
    def _ret(p_now, p_then):
        if p_then == 0 or p_then is None:
            return 0.0
        return (p_now - p_then) / p_then

    def _time_of_day(self, ts_ms):
        # seconds since midnight (approx with 86400s)
        sec = (ts_ms // 1000) % 86400
        ang = 2 * math.pi * (sec / 86400.0)
        return math.sin(ang), math.cos(ang)

    def push_and_compute(self, ts_ms, bid_px, ask_px, bid_sz, ask_sz, last_action:int=0):
        # expect arrays; guard if empty
        if not bid_px or not ask_px:
            return None

        mid = self._mid(bid_px[0], ask_px[0])
        self.mids.append(mid)
        self.times.append(ts_ms)

        # spread in bps
        spread = max(ask_px[0] - bid_px[0], 0.0)
        spread_bp = (spread / mid) * 1e4 if mid else 0.0

        # compute returns approx at 1s and 5s back
        def value_at(delta_s):
            if len(self.times) < 2:
                return None
            target = ts_ms - int(delta_s * 1000)
            # find the closest older point
            for i in range(len(self.times)-1, -1, -1):
                if self.times[i] <= target:
                    return self.mids[i]
            return self.mids[0]  # fallback oldest

        mid_1s = value_at(1.0)
        mid_5s = value_at(5.0)

        r1 = self._ret(mid, mid_1s) if mid_1s else 0.0
        r5 = self._ret(mid, mid_5s) if mid_5s else 0.0

        # simple vol proxy over last ~5s: std of last 20 mids / mid
        window = list(self.mids)[-20:]
        if len(window) >= 2:
            mu = sum(window) / len(window)
            var = sum((x - mu) ** 2 for x in window) / (len(window) - 1)
            vol_proxy = (var ** 0.5) / mid if mid else 0.0
        else:
            vol_proxy = 0.0

        # depth imbalance top-5
        sum_b = sum(bid_sz[:5]) if bid_sz else 0.0
        sum_a = sum(ask_sz[:5]) if ask_sz else 0.0
        denom = (sum_b + sum_a) or 1.0
        imb = (sum_b - sum_a) / denom

        s, c = self._time_of_day(ts_ms)
        return ExecFeatures(
            spread_bp=spread_bp,
            mid_return_1s=r1 * 1e4,   # bps
            mid_return_5s=r5 * 1e4,   # bps
            vol_proxy_5s=vol_proxy * 1e4,  # scale to bps for readability
            depth_imb_top5=imb,
            last_action=last_action,
            time_of_day_sin=s,
            time_of_day_cos=c,
        )