import ccxt
import time

class BinanceUSDM_Public:
    """Public-only access to Binance USDM (no API keys needed)."""
    def __init__(self):
        self.ex = ccxt.binanceusdm({
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

    def fetch_lob(self, symbol="BTC/USDT", depth=5):
        t0 = time.time()
        book = self.ex.fetch_order_book(symbol, limit=depth)  # public endpoint
        latency_ms = int((time.time() - t0) * 1000)
        bids = book.get("bids", [])[:depth]
        asks = book.get("asks", [])[:depth]
        return {"bids": bids, "asks": asks, "latency_ms": latency_ms}