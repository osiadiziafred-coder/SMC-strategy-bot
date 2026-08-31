"""One open trade, breakeven at +1R, price/structure trail from +1.5R. Never loosen SL."""

from __future__ import annotations

import logging

from smc_robot.broker.base import Broker
from smc_robot.bridge import sl_is_improvement
from smc_robot.config import Settings
from smc_robot.models import Direction, Position
from smc_robot.risk.protection import Quote

logger = logging.getLogger(__name__)


class PositionManager:
    def __init__(self, broker: Broker, settings: Settings):
        self.broker = broker
        self.settings = settings

    def open_count(self, symbol: str) -> int:
        return len(self.broker.open_positions(symbol, self.settings.risk.magic))

    def can_enter(self, symbol: str) -> bool:
        return self.open_count(symbol) < self.settings.risk.max_positions

    def manage(self, symbol: str, quote: Quote, structure_sl: float | None = None) -> list[Position]:
        updated: list[Position] = []
        for position in self.broker.open_positions(symbol, self.settings.risk.magic):
            managed = self._maybe_breakeven(position, quote)
            if self.settings.risk.trail_enabled:
                managed = self._maybe_trail(managed, quote, structure_sl)
            updated.append(managed)
        return updated

    def _r_multiple(self, position: Position, quote: Quote) -> float:
        if position.initial_risk <= 0:
            return 0.0
        if position.direction == Direction.BUY:
            return (quote.bid - position.entry) / position.initial_risk
        return (position.entry - quote.ask) / position.initial_risk

    def _apply_sl(self, position: Position, new_sl: float, why: str) -> Position:
        if not sl_is_improvement(position.direction.value, new_sl, position.sl):
            return position
        logger.info("%s %s SL %.3f -> %.3f", why, position.ticket, position.sl, new_sl)
        moved = self.broker.modify_sl(position, new_sl)
        extra = {"breakeven_applied": True}
        if why.startswith("trail"):
            extra["trailing_applied"] = True
        return moved.model_copy(update=extra)

    def _maybe_breakeven(self, position: Position, quote: Quote) -> Position:
        if position.breakeven_applied:
            return position
        if position.direction == Direction.BUY and position.sl >= position.entry > 0:
            return position.model_copy(update={"breakeven_applied": True})
        if position.direction == Direction.SELL and 0 < position.sl <= position.entry:
            return position.model_copy(update={"breakeven_applied": True})
        if self._r_multiple(position, quote) < self.settings.risk.breakeven_r:
            return position
        point = 0.01
        buffer = self.settings.risk.breakeven_buffer_points * point
        if position.direction == Direction.BUY:
            new_sl = position.entry + buffer
        else:
            new_sl = position.entry - buffer
        return self._apply_sl(position, new_sl, "breakeven")

    def _maybe_trail(self, position: Position, quote: Quote, structure_sl: float | None) -> Position:
        if self._r_multiple(position, quote) < self.settings.risk.trail_start_r:
            return position
        candidates: list[float] = []
        if structure_sl is not None:
            candidates.append(structure_sl)
        lock = self.settings.risk.trail_lock_r * position.initial_risk
        if position.direction == Direction.BUY:
            candidates.append(quote.bid - lock)
        else:
            candidates.append(quote.ask + lock)
        if position.direction == Direction.BUY:
            new_sl = max(candidates)
            if new_sl >= quote.bid:
                return position
        else:
            new_sl = min(candidates)
            if new_sl <= quote.ask:
                return position
        return self._apply_sl(position, new_sl, "trail")
