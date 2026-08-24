from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from smc_robot.models import Candle, Direction, Position
from smc_robot.risk.sizing import SymbolSpec
from smc_robot.risk.protection import Quote


class Broker(ABC):
    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def symbol_spec(self, symbol: str) -> SymbolSpec:
        raise NotImplementedError

    @abstractmethod
    def account_balance(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        raise NotImplementedError

    @abstractmethod
    def quote(self, symbol: str) -> Quote:
        raise NotImplementedError

    @abstractmethod
    def open_positions(self, symbol: str, magic: int) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    def market_order(
        self,
        symbol: str,
        direction: Direction,
        lots: float,
        sl: float,
        tp: float,
        deviation_points: int,
        magic: int,
        comment: str,
    ) -> Position:
        raise NotImplementedError

    @abstractmethod
    def modify_sl(self, position: Position, sl: float) -> Position:
        raise NotImplementedError
