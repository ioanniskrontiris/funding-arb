# funding_arb/monitor_equity.py
import os, time, math
from datetime import datetime
from dotenv import load_dotenv

from funding_arb.exec.real import BinanceUSDM_TestnetTrader  # we’re on testnet
from funding_arb.notify import send_telegram

load_dotenv()

SEND_EVERY_SEC = int(os.getenv("EQUITY_NOTIFY_EVERY_SEC", "300"))  # default 5 min

def _fmt_usd(x):
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return str(x)

def get_equity_snapshot(trader):
    """
    Returns a dict with:
      - balance_free
      - balance_total
      - unrealized_pnl
      - equity (balance_total + unrealized_pnl)
      - positions: list of small dicts
    Robust to minor ccxt schema differences.
    """
    ex = trader.ex
    bal = ex.fetch_balance() or {}
    usdt = bal.get("USDT") or bal.get("USDC") or {}
    free = float(usdt.get("free") or 0.0)
    total = float(usdt.get("total") or (free + float(usdt.get("used") or 0.0)))

    unrealized_total = 0.0
    positions = []
    try:
        # If you want to limit to a couple of symbols, set FILTER_SYMBOLS in env: "BTC/USDT:USDT,ETH/USDT:USDT"
        filt = [s.strip() for s in os.getenv("FILTER_SYMBOLS","").split(",") if s.strip()]
        raw_positions = ex.fetch_positions() or []
        for p in raw_positions:
            sym = p.get("symbol") or p.get("info",{}).get("symbol")
            if filt and sym not in filt:
                continue
            upnl = p.get("unrealizedPnl")
            if upnl is None:
                upnl = p.get("info",{}).get("unRealizedProfit")
            try:
                upnl = float(upnl or 0.0)
            except Exception:
                upnl = 0.0
            size = p.get("contracts") or p.get("contractsSize") or p.get("info",{}).get("positionAmt")
            try:
                size = float(size or 0.0)
            except Exception:
                size = 0.0
            unrealized_total += upnl
            positions.append({"symbol": sym, "upnl": upnl, "size": size})
    except Exception:
        pass

    equity = total + unrealized_total
    return {
        "balance_free": free,
        "balance_total": total,
        "unrealized_pnl": unrealized_total,
        "equity": equity,
        "positions": positions,
    }

def fmt_equity_msg(snap, base=None):
    # base is the equity at script start, to show change
    eq = snap["equity"]
    free = snap["balance_free"]
    upnl = snap["unrealized_pnl"]
    pos_lines = []
    for p in snap["positions"]:
        if not p["symbol"]:
            continue
        pos_lines.append(f"• {p['symbol']}: uPNL {_fmt_usd(p['upnl'])}, size {p['size']}")
    delta_line = ""
    if base is not None:
        d = eq - base
        sign = "▲" if d >= 0 else "▼"
        pct = (d / base * 100.0) if base and base != 0 else 0.0
        delta_line = f"\nΔ since start: {sign} {_fmt_usd(d)} ({pct:+.3f}%)"

    body = (
        f"⏱ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"Equity: {_fmt_usd(eq)} USDT\n"
        f"Free:   {_fmt_usd(free)} USDT\n"
        f"uPNL:   {_fmt_usd(upnl)} USDT"
        f"{delta_line}"
    )
    if pos_lines:
        body += "\nPositions:\n" + "\n".join(pos_lines)
    return body

def main():
    # ensure keys exist (env already set for your trader)
    assert (os.getenv("BINANCE_USDM_API_KEY") or os.getenv("BINANCE_API_KEY")), \
        "Missing Binance API key env vars"
    assert (os.getenv("BINANCE_USDM_API_SECRET") or os.getenv("BINANCE_API_SECRET")), \
        "Missing Binance API secret env vars"

    trader = BinanceUSDM_TestnetTrader()

    # baseline on start
    start_snap = get_equity_snapshot(trader)
    base_equity = start_snap["equity"]
    send_telegram("🔔 Equity monitor started.\n" + fmt_equity_msg(start_snap, base=base_equity))

    last_sent = 0.0
    while True:
        now = time.time()
        if now - last_sent >= SEND_EVERY_SEC:
            snap = get_equity_snapshot(trader)
            send_telegram(fmt_equity_msg(snap, base=base_equity))
            last_sent = now
        time.sleep(2)

if __name__ == "__main__":
    main()