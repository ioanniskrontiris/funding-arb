from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, Float, String, BigInteger
from sqlalchemy import JSON as SA_JSON
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from .db import Base

# Use JSON; on SQLite we swap in SQLITE_JSON
JSONType = SA_JSON().with_variant(SQLITE_JSON, "sqlite")

class LOBSnapshot(Base):
    __tablename__ = "lob_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    bid_px: Mapped[dict] = mapped_column(JSONType)
    bid_sz: Mapped[dict] = mapped_column(JSONType)
    ask_px: Mapped[dict] = mapped_column(JSONType)
    ask_sz: Mapped[dict] = mapped_column(JSONType)
    latency_ms: Mapped[int] = mapped_column(Integer)

class ExecOutcome(Base):
    __tablename__ = "exec_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[int] = mapped_column(Integer)  # 0 maker_inside, 1 post_only_edge, 2 taker_now, 3 wait
    side: Mapped[str] = mapped_column(String(4))  # "buy" or "sell"
    fill_px: Mapped[float] = mapped_column(Float)
    bench_mid_px: Mapped[float] = mapped_column(Float)
    realized_cost_bps: Mapped[float] = mapped_column(Float)
    fee_bps: Mapped[float] = mapped_column(Float)
    partial_fill: Mapped[int] = mapped_column(Integer)  # 0/1
    time_to_fill_ms: Mapped[int] = mapped_column(Integer)

class BanditShadow(Base):
    __tablename__ = "bandit_shadow"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    action_bandit: Mapped[int] = mapped_column(Integer)
    action_baseline: Mapped[int] = mapped_column(Integer)
    realized_cost_bps: Mapped[float] = mapped_column(Float)  # from baseline execution