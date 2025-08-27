# funding_arb/data/funding.py
import ccxt
import time

def _to_binance_symbol(unified_symbol: str) -> str:
    """
    Convert CCXT unified 'BASE/QUOTE' into Binance 'BASEQUOTE', e.g. 'BTC/USDT' -> 'BTCUSDT'
    """
    if "/" in unified_symbol:
        base, quote = unified_symbol.split("/")
        return f"{base}{quote}"
    return unified_symbol

class FundingFeed:
    """
    Real funding fetch for Binance USDM via raw premium-index endpoint.
    Returns (rate_per_8h, timestamp_ms).
    """
    def __init__(self):
        # public-only; no keys required
        self.ex = ccxt.binanceusdm({
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

    def funding_rate_8h(self, symbol: str = "BTC/USDT"):
        """
        rate is per 8h as a decimal (e.g., 0.0001 == 1 bp per 8h).
        """
        bsym = _to_binance_symbol(symbol)

        # Raw endpoint: GET /fapi/v1/premiumIndex
        # ccxt method: fapiPublicGetPremiumIndex
        resp = self.ex.fapiPublicGetPremiumIndex({"symbol": bsym})
        # Some ccxt versions return a list if symbol param is omitted; ensure we have a dict for our symbol
        if isinstance(resp, list):
            items = [it for it in resp if str(it.get("symbol")) == bsym]
            data = items[0] if items else {}
        else:
            data = resp or {}

        # Keys we care about:
        # - lastFundingRate (string)
        # - nextFundingTime (ms)
        # - time (ms)
        rate_str = data.get("lastFundingRate", "0")
        try:
            rate = float(rate_str)
        except Exception:
            rate = 0.0

        ts = int(data.get("time") or time.time() * 1000)
        return rate, ts

def funding_per_day_from_8h(rate_per_8h: float) -> float:
    """Binance funds every 8h → 3 periods per day."""
    return rate_per_8h * 3.0