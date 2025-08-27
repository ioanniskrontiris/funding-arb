# funding_arb/llm/prompt.py
import json

def build_messages(ctx: dict):
    """
    ctx keys (existing + new):
      - asset, bpsd_eth, bpsd_btc, bpsd_raw
      - pos_open (bool), perp_side ("short"/"long"/"")
      - notional, error_rate, close_th, open_th
      - features: dict(
          mid_px, spread_bps, imbalance_top,
          depth10_bid_usdt, depth10_ask_usdt, depth_imb10,
          depth50_bid_usdt, depth50_ask_usdt,
          vol_1m_ann,
          basis_bps, mark_px, index_px,
          taker_buy_sell_ratio_5m?, oi_change_pct_5m?, oi_sum?
        )
    Output JSON (strict):
      {"intent": "OPEN_SHORT|OPEN_LONG|CLOSE|HOLD",
       "asset": "<same as input asset>",
       "confidence": 0.0-1.0,
       "rationale": "short string"}
    """
    f = ctx.get("features", {})
    open_th = ctx.get("open_th", 1.0)
    close_th = ctx.get("close_th", 0.5)

    system = (
        "You are a quantitative trading assistant for funding carry on crypto perps. "
        "Goal: improve decision quality using funding carry and microstructure features. "
        "Hard safety rules:\n"
        "- If position is open and |bpsd_raw| >= close_th → prefer HOLD (carry is still attractive).\n"
        "- Only CLOSE if position is open AND |bpsd_raw| < close_th AND minimum hold was satisfied by the caller.\n"
        "- When flat, only OPEN if |bpsd_raw| >= open_th. If bpsd_raw > 0 → OPEN_SHORT. If bpsd_raw < 0 → OPEN_LONG.\n"
        "- Never OPEN if already open.\n"
        "Soft heuristics:\n"
        "- Very high vol_1m_ann → be conservative (lower confidence).\n"
        "- Large positive depth_imb10 or imbalance_top → near-term buy pressure; negative → sell pressure.\n"
        "- Very wide spread_bps → be conservative (lower confidence).\n"
        "- Positive basis_bps (mark > index) can mean perp rich → supports short bias; negative supports long bias.\n"
        "- taker_buy_sell_ratio_5m > 1.0 suggests recent aggressive buying; < 1.0 suggests selling.\n"
        "- Rising oi_change_pct_5m with strong imbalance may indicate continuation; falling may indicate mean reversion.\n"
        "Output strictly compact JSON with keys: intent, asset, confidence, rationale."
    )

    user = {
        "carry_context": {
            "asset": ctx.get("asset"),
            "bpsd_eth": ctx.get("bpsd_eth"),
            "bpsd_btc": ctx.get("bpsd_btc"),
            "bpsd_raw": ctx.get("bpsd_raw"),
            "open_th": open_th,
            "close_th": close_th,
        },
        "position": {
            "pos_open": ctx.get("pos_open"),
            "perp_side": ctx.get("perp_side"),
            "notional": ctx.get("notional"),
        },
        "risk": {
            "error_rate": ctx.get("error_rate", 0.0)
        },
        "features": f,
        "instruction": "Return only JSON: {intent, asset, confidence, rationale}. No code, no prose."
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]