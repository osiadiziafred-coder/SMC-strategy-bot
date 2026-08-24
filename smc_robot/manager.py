"""Position manager: one open trade, move SL to breakeven at +1R."""

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

    def manage(self, symbol: str, quote: Quote) -> list[Position]:
        updated: list[Position] = []
        for position in self.broker.open_positions(symbol, self.settings.risk.magic):
            managed = self._maybe_breakeven(position, quote)
            updated.append(managed)
        return updated

    def _maybe_breakeven(self, position: Position, quote: Quote) -> Position:
        if position.breakeven_applied:
            return position
        if position.direction == Direction.BUY and position.sl >= position.entry > 0:
            return position.model_copy(update={"breakeven_applied": True})
        if position.direction == Direction.SELL and 0 < position.sl <= position.entry:
            return position.model_copy(update={"breakeven_applied": True})
        risk = position.initial_risk
        if risk <= 0:
            return position
        point = 0.01
        buffer = self.settings.risk.breakeven_buffer_points * point
        target_r = self.settings.risk.breakeven_r
        if position.direction == Direction.BUY:
            favorable = quote.bid - position.entry
            if favorable >= target_r * risk:
                new_sl = position.entry + buffer
                if new_sl > position.sl:
                    logger.info("Moving BUY %s SL to breakeven %.3f", position.ticket, new_sl)
                    moved = self.broker.modify_sl(position, new_sl)
                    return moved.model_copy(update={"breakeven_applied": True})
        else:
            favorable = position.entry - quote.ask
            if favorable >= target_r * risk:
                new_sl = position.entry - buffer
                if new_sl < position.sl or position.sl == 0:
                    logger.info("Moving SELL %s SL to breakeven %.3f", position.ticket, new_sl)
                    moved = self.broker.modify_sl(position, new_sl)
                    return moved.model_copy(update={"breakeven_applied": True})
        return position
