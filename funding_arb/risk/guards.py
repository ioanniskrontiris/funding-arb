from dataclasses import dataclass
import time

@dataclass
class RiskConfig:
    max_notional: float = 2000.0          # USDT cap for a single position
    max_runtime_minutes: int = 120        # safety timer
    stale_lob_ms: int = 1500              # if LOB older than this → halt
    max_error_rate: float = 0.05          # API error rate over the window
    min_api_calls_for_rate: int = 20      # don’t judge until we have some calls
    pnl_stop_loss_usdt: float = -5.0      # if paper PnL < this → flatten & halt
    pnl_take_profit_usdt: float = 999999  # optional take profit (disabled by default)

class RiskState:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.start_ts = time.time()
        self.api_calls = 0
        self.api_errors = 0
        self.last_lob_ts_ms = 0

    def record_api(self, ok: bool, ts_ms: int | None = None):
        self.api_calls += 1
        if not ok:
            self.api_errors += 1
        if ts_ms is not None:
            self.last_lob_ts_ms = ts_ms

    def must_halt(self, notional_usdt: float, est_pnl_usdt: float, now_ms: int):
        # 1) runtime
        if (time.time() - self.start_ts) > (self.cfg.max_runtime_minutes * 60):
            return True, "runtime_limit"

        # 2) notional cap
        if notional_usdt > self.cfg.max_notional:
            return True, "notional_limit"

        # 3) stale LOB
        if self.last_lob_ts_ms and (now_ms - self.last_lob_ts_ms) > self.cfg.stale_lob_ms:
            return True, "stale_lob"

        # 4) API error rate
        if self.api_calls >= self.cfg.min_api_calls_for_rate:
            err_rate = self.api_errors / max(1, self.api_calls)
            if err_rate > self.cfg.max_error_rate:
                return True, "api_error_rate"

        # 5) PnL stops (paper)
        if est_pnl_usdt <= self.cfg.pnl_stop_loss_usdt:
            return True, "pnl_stop_loss"
        if est_pnl_usdt >= self.cfg.pnl_take_profit_usdt:
            return True, "pnl_take_profit"

        return False, ""