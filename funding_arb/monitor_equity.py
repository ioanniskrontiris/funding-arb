# funding_arb/monitor_equity.py
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from dotenv import load_dotenv

from funding_arb.exec.real import BinanceUSDM_TestnetTrader
from funding_arb.notify import send_telegram

load_dotenv()

# --------- knobs ---------
SNAPSHOT_EVERY_S = 60          # send a full equity snapshot this often
POLL_EVERY_S = 5               # poll exchange this often
ALERT_DROP_PCT = -0.005        # -0.5% since baseline → alert
ALERT_GAIN_PCT = 0.010         # +1.0% since baseline → alert
# -------------------------


def ts_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")


def fmt_pct(x: float) -> str:
    return f"{x*100:.3f}%"


def get_equity_state(trader: BinanceUSDM_TestnetTrader) -> Tuple[float, float, float, List[Dict]]:
    """
    Returns: equity, free, total_unrealized_pnl, open_positions
    open_positions: [{"symbol": "...", "contracts": float, "upnl": float}]
    """
    bal = trader.ex.fetch_balance(params={"type": "future"})
    equity = float(bal.get("total", {}).get("USDT", 0.0))
    free = float(bal.get("free", {}).get("USDT", 0.0))

    positions = trader.ex.fetch_positions()
    opens = []
    upnl_total = 0.0
    for p in positions:
        amt = float(p.get("contracts") or p.get("contractSize") or 0.0)
        # ccxt uses positive/negative amt for side on some exchanges; on binance it's size>0 when open
        if abs(amt) > 0:
            upnl = float(p.get("unrealizedPnl", 0.0))
            opens.append({
                "symbol": p.get("symbol"),
                "contracts": amt,
                "upnl": upnl,
            })
            upnl_total += upnl

    return equity, free, upnl_total, opens


def snapshot_message(equity: float, free: float, upnl: float,
                     positions: List[Dict], delta_pct_since_baseline: float,
                     started_at: str) -> str:
    lines = []
    lines.append("🔔 Equity snapshot")
    lines.append(f"⏱ {ts_utc()}")
    lines.append(f"Equity: {equity:,.2f} USDT")
    lines.append(f"Free:   {free:,.2f} USDT")
    lines.append(f"uPNL:   {upnl:,.2f} USDT")
    arrow = "▲" if delta_pct_since_baseline >= 0 else "▼"
    lines.append(f"Δ since start ({started_at}): {arrow} {fmt_pct(delta_pct_since_baseline)}")
    lines.append("Positions:")
    if positions:
        for p in positions:
            lines.append(f"• {p['symbol']}: uPNL {p['upnl']:.2f}, size {p['contracts']}")
    else:
        lines.append("• (none)")
    return "\n".join(lines)


def positions_index(positions: List[Dict]) -> Dict[str, float]:
    """symbol -> contracts"""
    return {p["symbol"]: float(p["contracts"]) for p in positions}


def main():
    print("📡 Equity monitor starting…")
    trader = BinanceUSDM_TestnetTrader()

    # initial state
    equity, free, upnl, positions = get_equity_state(trader)
    baseline_equity = equity
    baseline_at = ts_utc()
    last_snapshot = 0.0
    prev_pos_idx = positions_index(positions)

    # first snapshot
    send_telegram(
        snapshot_message(equity, free, upnl, positions, 0.0, baseline_at)
    )
    print("First snapshot sent.")

    while True:
        try:
            equity, free, upnl, positions = get_equity_state(trader)
        except Exception as e:
            # Don’t spam Telegram for transient API errors; just print.
            print(f"[monitor] fetch error: {e}")
            time.sleep(POLL_EVERY_S)
            continue

        # status line for local logs
        print(f"[{ts_utc()}] equity={equity:.2f} free={free:.2f} upnl={upnl:.2f}")

        # position open/close alerts
        cur_pos_idx = positions_index(positions)
        # opened
        for sym, sz in cur_pos_idx.items():
            if sym not in prev_pos_idx:
                send_telegram(f"🟢 Position OPENED: {sym} size {sz}")
        # closed
        for sym, sz in prev_pos_idx.items():
            if sym not in cur_pos_idx:
                send_telegram(f"🔴 Position CLOSED: {sym} (prev size {sz})")
        prev_pos_idx = cur_pos_idx

        # equity change alerts
        delta_pct = 0.0 if baseline_equity == 0 else (equity - baseline_equity) / baseline_equity
        if delta_pct <= ALERT_DROP_PCT:
            send_telegram(f"⚠️ Equity DOWN {fmt_pct(delta_pct)} from baseline ({baseline_at}). Baseline reset.")
            baseline_equity = equity
            baseline_at = ts_utc()
        elif delta_pct >= ALERT_GAIN_PCT:
            send_telegram(f"🚀 Equity UP {fmt_pct(delta_pct)} from baseline ({baseline_at}). Baseline reset.")
            baseline_equity = equity
            baseline_at = ts_utc()

        # periodic snapshot
        now = time.time()
        if now - last_snapshot >= SNAPSHOT_EVERY_S:
            snap = snapshot_message(equity, free, upnl, positions,
                                    0.0 if equity == baseline_equity else (equity - baseline_equity) / baseline_equity,
                                    baseline_at)
            send_telegram(snap)
            last_snapshot = now

        time.sleep(POLL_EVERY_S)


if __name__ == "__main__":
    main()