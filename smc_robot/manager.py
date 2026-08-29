"""One open trade, breakeven at +1R, optional structure-based trailing."""

from __future__ import annotations

import logging

from smc_robot.broker.base import Broker
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
            if new_sl > position.sl:
                logger.info("Moving BUY %s SL to breakeven %.3f", position.ticket, new_sl)
                moved = self.broker.modify_sl(position, new_sl)
                return moved.model_copy(update={"breakeven_applied": True})
        else:
            new_sl = position.entry - buffer
            if new_sl < position.sl or position.sl == 0:
                logger.info("Moving SELL %s SL to breakeven %.3f", position.ticket, new_sl)
                moved = self.broker.modify_sl(position, new_sl)
                return moved.model_copy(update={"breakeven_applied": True})
        return position

    def _maybe_trail(self, position: Position, quote: Quote, structure_sl: float | None) -> Position:
        if structure_sl is None:
            return position
        if self._r_multiple(position, quote) < self.settings.risk.trail_start_r:
            return position
        if position.direction == Direction.BUY:
            if structure_sl > position.sl and structure_sl < quote.bid:
                logger.info("Trail BUY %s SL to structure %.3f", position.ticket, structure_sl)
                moved = self.broker.modify_sl(position, structure_sl)
                return moved.model_copy(update={"trailing_applied": True, "breakeven_applied": True})
        elif structure_sl < position.sl or position.sl == 0:
            if structure_sl > quote.ask:
                logger.info("Trail SELL %s SL to structure %.3f", position.ticket, structure_sl)
                moved = self.broker.modify_sl(position, structure_sl)
                return moved.model_copy(update={"trailing_applied": True, "breakeven_applied": True})
        return position
