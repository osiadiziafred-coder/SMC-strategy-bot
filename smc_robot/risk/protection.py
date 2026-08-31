from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from smc_robot.config import Settings
from smc_robot.risk.sizing import SymbolSpec


@dataclass
class Quote:
    bid: float
    ask: float
    time: datetime
    spread_points: float


class ExecutionGuard:
    """Spread / staleness / spike protection. News is not blocked."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._spreads: deque[float] = deque(maxlen=settings.protection.spread_window)

    def observe(self, spread_points: float) -> None:
        self._spreads.append(spread_points)

    def recent_spreads(self) -> list[float]:
        return list(self._spreads)

    def check(self, quote: Quote, spec: SymbolSpec) -> tuple[bool, str]:
        cfg = self.settings.protection
        now = datetime.now(timezone.utc)
        quote_time = quote.time
        if quote_time.tzinfo is None:
            quote_time = quote_time.replace(tzinfo=timezone.utc)
        age_ms = (now - quote_time).total_seconds() * 1000.0
        if age_ms > cfg.max_quote_age_ms:
            return False, f"stale_quote_{age_ms:.0f}ms"
        if quote.spread_points > cfg.max_spread_points:
            return False, f"spread_{quote.spread_points:.1f}_gt_{cfg.max_spread_points}"
        if self._spreads:
            median = sorted(self._spreads)[len(self._spreads) // 2]
            if median > 0 and quote.spread_points >= median * cfg.spread_spike_mult:
                return False, f"spread_spike_{quote.spread_points:.1f}_vs_{median:.1f}"
        if quote.ask <= 0 or quote.bid <= 0 or quote.ask < quote.bid:
            return False, "invalid_quote"
        min_stop = max(cfg.min_stop_points, spec.trade_stops_level)
        if min_stop < 0:
            return False, "invalid_stops_level"
        return True, "ok"
