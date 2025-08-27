# funding_arb/features.py
import math
import time
import statistics
from typing import Dict, List
import requests

__all__ = [
    "VolEstimator",
    "compute_features",
]

_EPS = 1e-12


class VolEstimator:
    """
    Simple realized volatility estimator over a rolling time window.
    Stores (ts, mid) and computes annualized vol from recent log-returns.
    """
    def __init__(self, max_points: int = 2000):
        self.max_points = max_points
        self.buf: List[tuple[float, float]] = []

    def reset(self):
        self.buf.clear()

    def update(self, mid: float, ts: float | None = None):
        if not ts:
            ts = time.time()
        self.buf.append((float(ts), float(mid)))
        if len(self.buf) > self.max_points:
            # drop oldest
            self.buf = self.buf[-self.max_points :]

    def vol_ann(self, window_s: float = 60.0) -> float:
        """
        Annualized realized vol from last `window_s` seconds.
        Returns 0.0 if insufficient data.
        """
        if len(self.buf) < 2:
            return 0.0
        now = time.time()
        pts = [p for p in self.buf if now - p[0] <= window_s]
        if len(pts) < 2:
            return 0.0

        rets = []
        dts = []
        for i in range(1, len(pts)):
            p0, p1 = pts[i - 1][1], pts[i][1]
            t0, t1 = pts[i - 1][0], pts[i][0]
            if p0 > 0 and p1 > 0 and t1 > t0:
                rets.append(math.log(p1 / p0))
                dts.append(t1 - t0)

        if len(rets) < 2 or sum(dts) <= 0:
            return 0.0

        avg_dt = sum(dts) / len(dts)
        if avg_dt <= 0:
            return 0.0

        # per-step std -> per-second std -> annualized
        step_std = statistics.pstdev(rets)
        per_sec_std = step_std / math.sqrt(avg_dt)
        annualize = math.sqrt(365 * 24 * 60 * 60)
        return per_sec_std * annualize


def _spread_bps(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2.0
    return 0.0 if mid <= 0 else (ask - bid) / mid * 1e4


def _depth_within_bps(bids: List[List[float]], asks: List[List[float]], mid: float, bps: float) -> dict:
    """
    Sums notional depth within +/- bps of mid on each side, in USDT.
    bids: [[price, size], ...] descending
    asks: [[price, size], ...] ascending
    """
    if mid <= 0:
        return dict(bid_usdt=0.0, ask_usdt=0.0)

    bid_cut = mid * (1 - bps / 1e4)
    ask_cut = mid * (1 + bps / 1e4)

    bid_usdt = 0.0
    for px, sz in bids:
        if px < bid_cut:
            break
        bid_usdt += float(px) * float(sz)

    ask_usdt = 0.0
    for px, sz in asks:
        if px > ask_cut:
            break
        ask_usdt += float(px) * float(sz)

    return dict(bid_usdt=bid_usdt, ask_usdt=ask_usdt)


def _top_imbalance(bids: List[List[float]], asks: List[List[float]]) -> float:
    """
    (bid_size - ask_size) / (bid_size + ask_size)
    """
    if not (bids and asks):
        return 0.0
    bsz = float(bids[0][1])
    asz = float(asks[0][1])
    denom = bsz + asz + _EPS
    return (bsz - asz) / denom


def _binance_symbol_raw(asset_ccy: str) -> str:
    # "ETH/USDT" -> "ETHUSDT"
    return asset_ccy.replace("/", "")


def _external_binance_metrics(asset_ccy: str) -> dict:
    """
    Optional: mainnet-only public stats (works even when you trade testnet).
    - Taker buy/sell ratio (5m)
    - Open interest change (5m)
    If endpoints fail, returns empty dict.
    """
    out = {}
    try:
        sym = _binance_symbol_raw(asset_ccy)
        base = "https://fapi.binance.com"

        # Taker long/short (buy/sell) ratio
        try:
            url = f"{base}/futures/data/takerlongshortRatio?symbol={sym}&interval=5m&limit=1"
            r = requests.get(url, timeout=3)
            d = r.json()
            if isinstance(d, list) and d:
                last = d[-1]
                # Binance returns different keys across time; use whatever exists
                ratio = float(last.get("buySellRatio") or last.get("longShortRatio") or 1.0)
                out["taker_buy_sell_ratio_5m"] = ratio
        except Exception:
            pass

        # Open interest hist (5m change)
        try:
            url = f"{base}/futures/data/openInterestHist?symbol={sym}&period=5m&limit=2"
            r = requests.get(url, timeout=3)
            d = r.json()
            if isinstance(d, list) and len(d) >= 2:
                prev = float(d[-2].get("sumOpenInterest", 0.0))
                cur = float(d[-1].get("sumOpenInterest", 0.0))
                if prev > 0:
                    out["oi_change_pct_5m"] = (cur - prev) / prev
                out["oi_sum"] = cur
        except Exception:
            pass

    except Exception:
        # swallow — features are optional
        return out

    return out


def _basis_features(ex, symbol: str) -> dict:
    """
    Basis (mark - index)/index in bps using fetch_ticker() if available.
    """
    try:
        t = ex.fetch_ticker(symbol)
        info = t.get("info", {}) if isinstance(t, dict) else {}
        mark = float(info.get("markPrice") or t.get("mark", 0.0) or t.get("last", 0.0) or 0.0)
        index = float(info.get("indexPrice") or t.get("index", 0.0) or 0.0)
        basis_bps = 0.0
        if mark > 0 and index > 0:
            basis_bps = (mark - index) / index * 1e4
        return {"basis_bps": basis_bps, "mark_px": mark, "index_px": index}
    except Exception:
        return {"basis_bps": 0.0, "mark_px": 0.0, "index_px": 0.0}


def compute_features(
    ex,
    symbol: str,
    asset_ccy: str,
    bids: List[List[float]],
    asks: List[List[float]],
    vol: VolEstimator,
) -> Dict:
    """
    Aggregate microstructure + external features into a dict safe for LLM.
    """
    if not (bids and asks):
        return {}

    bid0, ask0 = float(bids[0][0]), float(asks[0][0])
    mid = (bid0 + ask0) / 2.0
    vol.update(mid)

    spread = _spread_bps(bid0, ask0)
    imb_top = _top_imbalance(bids, asks)

    depth10 = _depth_within_bps(bids, asks, mid, 10.0)
    depth50 = _depth_within_bps(bids, asks, mid, 50.0)

    # normalized depth imbalance (within 10 bps)
    denom10 = depth10["bid_usdt"] + depth10["ask_usdt"] + _EPS
    depth_imb10 = (depth10["bid_usdt"] - depth10["ask_usdt"]) / denom10

    basis = _basis_features(ex, symbol)
    ext = _external_binance_metrics(asset_ccy)

    return {
        "mid_px": mid,
        "spread_bps": spread,
        "imbalance_top": imb_top,
        "depth10_bid_usdt": depth10["bid_usdt"],
        "depth10_ask_usdt": depth10["ask_usdt"],
        "depth_imb10": depth_imb10,
        "depth50_bid_usdt": depth50["bid_usdt"],
        "depth50_ask_usdt": depth50["ask_usdt"],
        "vol_1m_ann": vol.vol_ann(window_s=60.0),
        **basis,
        **ext,
    }