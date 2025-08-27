import ccxt
import os, math
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_USDM_API_KEY")
API_SECRET = os.getenv("BINANCE_USDM_API_SECRET")

def _ex():
    ex = ccxt.binanceusdm({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })
    ex.set_sandbox_mode(True)
    ex.load_markets()
    return ex

def flatten_symbol(symbol: str):
    ex = _ex()
    # positions for the symbol (linear USDT-margined)
    poss = ex.fetch_positions([symbol])
    if not poss:
        print("no positions"); return
    pos = poss[0]
    amt = float(pos.get("contracts") or pos.get("contractsSize") or 0)
    side = pos.get("side")  # 'long'/'short' or '' if flat

    if not amt or not side:
        print("already flat"); return

    # reduce-only market order in the OPPOSITE direction
    reduce_side = "sell" if side == "long" else "buy"
    # Binance uses absolute quantity; use amount precision
    amt_str = ex.amount_to_precision(symbol, amt)
    print(f"flattening {symbol}: {side} {amt_str} → {reduce_side} (reduce-only)")

    o = ex.create_order(symbol, "market", reduce_side, float(amt_str), None, {"reduceOnly": True})
    print("reduce-only close sent, id:", o["id"])

if __name__ == "__main__":
    # example: ETH/USDT:USDT
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "ETH/USDT:USDT"
    flatten_symbol(sym)