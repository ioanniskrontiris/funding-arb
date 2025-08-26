from sqlalchemy.orm import Session
from time import time
from .models import LOBSnapshot

def save_lob(session: Session, symbol: str, bids, asks, latency_ms: int):
    ts_ms = int(time() * 1000)
    bid_px = [px for px, _ in bids]
    bid_sz = [sz for _, sz in bids]
    ask_px = [px for px, _ in asks]
    ask_sz = [sz for _, sz in asks]
    row = LOBSnapshot(ts_ms=ts_ms, symbol=symbol,
                      bid_px=bid_px, bid_sz=bid_sz,
                      ask_px=ask_px, ask_sz=ask_sz,
                      latency_ms=latency_ms)
    session.add(row)