from dataclasses import dataclass, field
import time

@dataclass
class Position:
    symbol: str
    notional_usdt: float = 0.0
    open_ts_ms: int = 0
    accrued_funding_bps: float = 0.0   # cumulative bps of funding (per notional)
    is_open: bool = False

@dataclass
class PaperBook:
    pos: Position = field(default_factory=lambda: Position(symbol="BTC/USDT"))

    def open_delta_neutral(self, symbol: str, notional_usdt: float):
        self.pos = Position(symbol=symbol, notional_usdt=notional_usdt,
                            open_ts_ms=int(time.time()*1000), accrued_funding_bps=0.0, is_open=True)

    def close(self):
        self.pos.is_open = False

    def accrue_funding(self, bps_per_day: float, seconds: float):
        """
        Add funding bps proportional to time.
        Example: if 10 bps/day and we pass 0.5 day -> +5 bps accrued.
        """
        if not self.pos.is_open: return
        self.pos.accrued_funding_bps += bps_per_day * (seconds / 86400.0)

    def realized_pnl_usdt(self, taker_fee_bps_total: float = 0.0):
        """Funding PnL ≈ notional * (accrued_bps / 1e4) - fees (approx)."""
        return self.pos.notional_usdt * (self.pos.accrued_funding_bps / 1e4) - \
               self.pos.notional_usdt * (taker_fee_bps_total / 1e4)