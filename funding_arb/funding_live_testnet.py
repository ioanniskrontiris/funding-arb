import time, json, os
from dotenv import load_dotenv

from funding_arb.data.funding import FundingFeed, funding_per_day_from_8h
from funding_arb.exec.bandit_exec import BanditExecutor
from funding_arb.exec.real import BinanceUSDM_TestnetTrader
from funding_arb.paper.positions import PaperBook
from funding_arb.risk.guards import RiskConfig, RiskState
from funding_arb.notify import send_telegram, fmt_status, fmt_open, fmt_close, fmt_risk
from funding_arb.db import SessionLocal
from funding_arb.loggers import log_funding, log_signal, log_position

# NEW features + LLM
from funding_arb.features import VolEstimator, compute_features
from funding_arb.llm.provider import get_provider
from funding_arb.llm.prompt import build_messages

load_dotenv()

# thresholds & pacing
OPEN_COOLDOWN_S = 20.0
MIN_HOLD_S      = 60.0
OPEN_TH         = 0.5     # relaxed so we’ll actually trade
CLOSE_TH        = 0.25
LLM_PERIOD_S    = 7.5

def spread_bps_from_ob(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2.0
    return 0.0 if mid <= 0 else (ask - bid) / mid * 1e4

def est_min_notional(ex, symbol: str) -> float:
    m = ex.market(symbol)
    min_amt = (m.get("limits", {}).get("amount", {}) or {}).get("min") or 0.0
    ob = ex.fetch_order_book(symbol, limit=5)
    bids, asks = ob.get("bids", []), ob.get("asks", [])
    mid = (bids[0][0] + asks[0][0]) / 2.0 if bids and asks else 0.0
    approx = float(min_amt) * float(mid) if mid else 0.0
    return max(20.0, approx)

def map_asset_to_testnet_symbol(ex, asset: str) -> str:
    base = asset.split("/")[0].upper()
    prefer = f"{base}/USDT:USDT"
    if prefer in ex.symbols:
        return prefer
    for s in ex.symbols:
        if s.startswith(f"{base}/") and s.endswith(":USDT"):
            return s
    return ex.symbols[0]

def fallback_rule_intent(bpsd_raw: float, pos_open: bool) -> str:
    if not pos_open and abs(bpsd_raw) >= OPEN_TH:
        return "OPEN_SHORT" if bpsd_raw > 0 else "OPEN_LONG"
    if pos_open and abs(bpsd_raw) < CLOSE_TH:
        return "CLOSE"
    return "HOLD"

def guardrails(intent: str, bpsd_raw: float, pos_open: bool, last_open_ts: float) -> str:
    now = time.time()
    if intent in ("OPEN_SHORT", "OPEN_LONG") and pos_open:
        return "HOLD"
    if intent == "OPEN_SHORT" and not (bpsd_raw > 0):
        return "HOLD"
    if intent == "OPEN_LONG" and not (bpsd_raw < 0):
        return "HOLD"
    if intent == "CLOSE":
        if not pos_open:
            return "HOLD"
        if abs(bpsd_raw) >= CLOSE_TH:
            return "HOLD"
        if last_open_ts and (now - last_open_ts) < MIN_HOLD_S:
            return "HOLD"
    return intent

def get_error_rate_safe(risk) -> float:
    try:
        return float(risk.error_rate())
    except Exception:
        try:
            return float(getattr(risk, "error_rate", 0.0))
        except Exception:
            return 0.0

def debug_print_llm(label, obj):
    try:
        print(f"[LLM] {label}: " + json.dumps(obj, ensure_ascii=False))
    except Exception:
        print(f"[LLM] {label}: {obj}")

def main():
    print("Funding LIVE (testnet) — LLM supervisor + bandit + risk + telegram + logging")

    fund   = FundingFeed()
    bandit = BanditExecutor()
    trader = BinanceUSDM_TestnetTrader()
    book   = PaperBook()
    risk   = RiskState(RiskConfig(
        max_notional=2000.0, max_runtime_minutes=180,
        stale_lob_ms=2000, max_error_rate=0.08, min_api_calls_for_rate=20,
        pnl_stop_loss_usdt=-5.0
    ))

    # LLM + vol estimator
    llm = get_provider()
    last_llm_ts = 0.0
    cached_decision = {"intent": "HOLD", "asset": "ETH/USDT", "confidence": 0.0, "rationale": "init"}
    vol = VolEstimator()

    # start ETH by default
    asset  = "ETH/USDT"
    symbol = map_asset_to_testnet_symbol(trader.ex, asset)
    trader.set_leverage(symbol, 1)
    floor = est_min_notional(trader.ex, symbol)
    notional = max(25.0, floor * 1.05)
    print(f"Using testnet symbol: {symbol}")
    print(f"[info] using notional ≈ {notional:.2f} USDT (floor~{floor:.2f})")

    perp_side       = None
    last_ts         = time.time()
    last_status_ts  = 0.0
    last_tele_ts    = 0.0  # muted in code below, but keeping if you re-enable
    last_open_ts    = 0.0
    end_time        = time.time() + 300  # extend/daemonize on VPS as you like

    while time.time() < end_time:
        # 1) funding snapshot
        r8h_eth, _ = fund.funding_rate_8h("ETH/USDT")
        r8h_btc, _ = fund.funding_rate_8h("BTC/USDT")
        bpsd_eth = 1e4 * funding_per_day_from_8h(r8h_eth)
        bpsd_btc = 1e4 * funding_per_day_from_8h(r8h_btc)

        # choose asset unless forced
        force = os.getenv("FORCE_ASSET")
        if force in ("ETH/USDT", "BTC/USDT"):
            asset = force
            bpsd_raw = bpsd_eth if force == "ETH/USDT" else bpsd_btc
            print(f"[force] asset pinned via FORCE_ASSET={force}, bpsd={bpsd_raw:.2f}")
        else:
            if abs(bpsd_btc) > abs(bpsd_eth):
                asset = "BTC/USDT"; bpsd_raw = bpsd_btc
            else:
                asset = "ETH/USDT"; bpsd_raw = bpsd_eth

        # switch symbol only when flat
        if not book.pos.is_open:
            new_symbol = map_asset_to_testnet_symbol(trader.ex, asset)
            if new_symbol != symbol:
                symbol = new_symbol
                trader.set_leverage(symbol, 1)
                floor = est_min_notional(trader.ex, symbol)
                notional = max(25.0, floor * 1.05)
                vol.reset()  # reset vol after asset/symbol switch
                print(f"[switch] symbol={symbol} (asset={asset}); notional≈{notional:.2f}")

        # 2) order book
        try:
            ob = trader.ex.fetch_order_book(symbol, limit=25)
            bids, asks = ob.get("bids", []), ob.get("asks", [])
        except Exception:
            time.sleep(0.25)
            continue
        if not (bids and asks):
            time.sleep(0.25)
            continue

        bid, ask = bids[0][0], asks[0][0]
        spread_bps = spread_bps_from_ob(bid, ask)
        vol.update((bid + ask) / 2.0)

        # 3) paper accrual
        now = time.time()
        dt = now - last_ts
        last_ts = now
        if book.pos.is_open:
            signed_bpsd = bpsd_raw if perp_side == "short" else (-bpsd_raw)
            book.accrue_funding(bps_per_day=signed_bpsd, seconds=dt)

        # 4) risk check
        est_pnl = book.realized_pnl_usdt()
        halt, reason = risk.must_halt(
            notional_usdt=book.pos.notional_usdt if book.pos.is_open else notional,
            est_pnl_usdt=est_pnl, now_ms=int(now*1000)
        )
        if halt:
            print(f"RISK HALT: {reason}")
            send_telegram(fmt_risk(reason, est_pnl))
            if book.pos.is_open:
                side = "buy" if perp_side == "short" else "sell"
                trader.execute_action(2, symbol, side, notional, deadline_ms=1200, reduce_only=True)
                book.close(); perp_side = None
            break

        # 5) FEATURES (the new part)
        feats = compute_features(trader.ex, symbol, asset, bids, asks, vol)

        # 6) LLM decision
        do_llm = (now - last_llm_ts) >= LLM_PERIOD_S
        if do_llm and llm.available():
            ctx = {
                "asset": asset,
                "bpsd_eth": bpsd_eth, "bpsd_btc": bpsd_btc, "bpsd_raw": bpsd_raw,
                "pos_open": book.pos.is_open, "perp_side": perp_side or "",
                "notional": notional, "error_rate": get_error_rate_safe(risk),
                "close_th": CLOSE_TH, "open_th": OPEN_TH,
                "features": feats,
            }
            try:
                raw = llm.chat_json(build_messages(ctx))
                if isinstance(raw, dict) and {"intent","asset","confidence","rationale"} <= raw.keys():
                    cached_decision = raw
                else:
                    cached_decision = {
                        "intent": fallback_rule_intent(bpsd_raw, book.pos.is_open),
                        "asset": asset, "confidence": 0.4, "rationale": "fallback:bad_json"
                    }
                debug_print_llm("decision", cached_decision)
            except Exception:
                cached_decision = {
                    "intent": fallback_rule_intent(bpsd_raw, book.pos.is_open),
                    "asset": asset, "confidence": 0.4, "rationale": "fallback:exception"
                }
            last_llm_ts = now
        else:
            if "intent" not in cached_decision:
                cached_decision = {
                    "intent": fallback_rule_intent(bpsd_raw, book.pos.is_open),
                    "asset": asset, "confidence": 0.4, "rationale": "fallback:init"
                }

        intent = guardrails(cached_decision["intent"], bpsd_raw, book.pos.is_open, last_open_ts)
        if cached_decision.get("confidence", 1.0) < 0.4:
            intent = "HOLD"
        if intent in ("OPEN_SHORT", "OPEN_LONG") and (now - last_open_ts) < OPEN_COOLDOWN_S:
            debug_print_llm("cooldown_hold", {"intent": intent, "since_open_s": now - last_open_ts})
            intent = "HOLD"
        if (intent == "HOLD") and (not book.pos.is_open) and (abs(bpsd_raw) >= OPEN_TH):
            intent = "OPEN_SHORT" if bpsd_raw > 0 else "OPEN_LONG"
            debug_print_llm("override_to_rule", {"intent": intent, "bpsd_raw": bpsd_raw})

        with SessionLocal() as s:
            log_signal(s, symbol, intent, bpsd_raw); s.commit()

        # 7) act
        if intent in ("OPEN_SHORT","OPEN_LONG") and not book.pos.is_open:
            side = "sell" if intent == "OPEN_SHORT" else "buy"
            action, ts_ms, _ = bandit.decide_and_execute(
                {"bids":bids,"asks":asks,"latency_ms":0}, symbol, side=side, deadline_ms=1200
            )
            if action is None or action == 3:
                action = 2
            real = trader.execute_action(action, symbol, side, notional, deadline_ms=1200, reduce_only=False)
            if real.get("price"):
                perp_side = "short" if side == "sell" else "long"
                book.open_delta_neutral(symbol, notional_usdt=notional)
                print(f"OPEN {perp_side} ({asset}): bpsd={bpsd_raw:.2f}, action={action}, status={real['status']}")
                send_telegram(fmt_open(bpsd_raw, action, 0.0))
                last_open_ts = time.time()

        elif intent == "CLOSE" and book.pos.is_open:
            side = "buy" if perp_side == "short" else "sell"
            real = trader.execute_action(2, symbol, side, notional, deadline_ms=1200, reduce_only=True)
            if real.get("price"):
                print(f"CLOSE {perp_side} (reduce-only {side}) | |bpsd|→{abs(bpsd_raw):.2f}")
                send_telegram(fmt_close(bpsd_raw, 2, 0.0))
                book.close(); perp_side = None

        # 8) status + persist once per second (telegram heartbeat muted)
        if now - last_status_ts >= 1.0:
            print(
                f"status: open={book.pos.is_open}, accrued={book.pos.accrued_funding_bps:.4f} bps, "
                f"est_pnl={book.realized_pnl_usdt():.6f} USDT, bpsd={bpsd_raw:.2f}, "
                f"side={perp_side}, asset={asset}, symbol={symbol}, llm={'on' if llm.available() else 'off'}"
            )
            with SessionLocal() as s:
                log_funding(
                    s, asset,
                    (r8h_btc if asset=='BTC/USDT' else r8h_eth),
                    funding_per_day_from_8h(r8h_btc if asset=='BTC/USDT' else r8h_eth),
                    bpsd_raw
                )
                log_position(s, symbol, book.pos.is_open, book.pos.notional_usdt,
                             book.pos.accrued_funding_bps, book.realized_pnl_usdt())
                s.commit()
            last_status_ts = now

        time.sleep(0.25)

    print("\n=== SUMMARY ===")
    print(
        f"open={book.pos.is_open}, accrued={book.pos.accrued_funding_bps:.3f} bps, "
        f"est_pnl={book.realized_pnl_usdt():.4f} USDT, side={perp_side}, symbol={symbol}"
    )
    send_telegram(
        f"SUMMARY open={book.pos.is_open}, "
        f"accrued={book.pos.accrued_funding_bps:.3f} bps, "
        f"est_pnl={book.realized_pnl_usdt():.4f} USDT, side={perp_side}, symbol={symbol}"
    )

if __name__ == "__main__":
    main()