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