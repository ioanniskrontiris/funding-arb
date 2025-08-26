import time
from sqlalchemy.orm import Session
from funding_arb.models import ExecOutcome

def log_outcome(session: Session, symbol: str, action: int, side: str, sim):
    row = ExecOutcome(
        ts_ms=int(time.time() * 1000),
        symbol=symbol,
        action=action,
        side=side,
        fill_px=sim["fill_px"],
        bench_mid_px=sim["bench_mid_px"],
        realized_cost_bps=sim["realized_cost_bps"],
        fee_bps=sim["fee_bps"],
        partial_fill=sim["partial_fill"],
        time_to_fill_ms=sim["time_to_fill_ms"],
    )
    session.add(row)