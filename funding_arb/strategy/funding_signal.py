from dataclasses import dataclass

@dataclass
class SignalConfig:
    open_threshold_bpsd: float = 1.0     # open if expected net bps/day > 4
    close_threshold_bpsd: float = 0.5    # close if falls below 1
    min_persistence: int = 1             # need N consecutive ticks above threshold

class FundingSignal:
    def __init__(self, cfg: SignalConfig):
        self.cfg = cfg
        self.persist = 0
        self.opened = False

    def decide(self, bps_per_day_net: float):
        """Return 'OPEN', 'CLOSE', or 'HOLD_*' with reason."""
        if bps_per_day_net > self.cfg.open_threshold_bpsd:
            self.persist += 1
            if not self.opened and self.persist >= self.cfg.min_persistence:
                self.opened = True
                return "OPEN", bps_per_day_net
            return ("HOLD_OPEN" if self.opened else "HOLD_WAIT"), bps_per_day_net
        else:
            self.persist = 0
            if self.opened and bps_per_day_net < self.cfg.close_threshold_bpsd:
                self.opened = False
                return "CLOSE", bps_per_day_net
            return ("HOLD_OPEN" if self.opened else "HOLD_CLOSED"), bps_per_day_net