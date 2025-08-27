import time
from sqlalchemy.orm import Session
from funding_arb.models import FundingTick, SignalTick, PositionSnap

def log_funding(session: Session, symbol: str, rate8h: float, rate_day: float, bps_day_net: float):
    session.add(FundingTick(
        ts_ms=int(time.time()*1000),
        symbol=symbol,
        rate_8h=rate8h,
        rate_day=rate_day,
        bps_day_net=bps_day_net,
    ))

def log_signal(session: Session, symbol: str, decision: str, bps_day_net: float):
    session.add(SignalTick(
        ts_ms=int(time.time()*1000),
        symbol=symbol,
        decision=decision,
        bps_day_net=bps_day_net,
    ))

def log_position(session: Session, symbol: str, is_open: bool, notional: float, accrued_bps: float, est_pnl: float):
    session.add(PositionSnap(
        ts_ms=int(time.time()*1000),
        symbol=symbol,
        is_open=1 if is_open else 0,
        notional_usdt=notional,
        accrued_bps=accrued_bps,
        est_pnl_usdt=est_pnl,
    ))