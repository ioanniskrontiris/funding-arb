from typing import Dict, List

def build_messages(ctx: Dict) -> List[Dict[str, str]]:
    """
    ctx has keys like:
      bpsd_eth, bpsd_btc, asset, bpsd_raw, spread_bps,
      vol_proxy, pos_open, perp_side, notional,
      error_rate, runtime_min, persistence
    """
    sys = {
        "role": "system",
        "content": (
    "You are a trading decision AI for a delta-neutral funding strategy.\n"
    "Return one of: OPEN_SHORT, OPEN_LONG, CLOSE, HOLD.\n"
    "Rules:\n"
    "- OPEN_SHORT only if bpsd_raw > 0 (positive carry to shorts).\n"
    "- OPEN_LONG only if bpsd_raw < 0 (positive carry to longs).\n"
    "- CLOSE only if pos_open is true AND abs(bpsd_raw) < close_th.\n"
    "- Otherwise, HOLD.\n"
    "You must NEVER say CLOSE if abs(bpsd_raw) >= close_th.\n"
    "Output strict JSON: {\"intent\",\"asset\",\"confidence\",\"rationale\"}."
        )
    }
    user = {
        "role": "user",
        "content": f"Context: {ctx}"
    }
    return [sys, user]