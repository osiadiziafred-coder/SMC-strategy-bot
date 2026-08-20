from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from smc_robot.config import Position, Side


class Broker(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...

    @abstractmethod
    def balance(self) -> float: ...

    @abstractmethod
    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame: ...

    @abstractmethod
    def open_positions(self, magic: int | None = None) -> list[Position]: ...

    @abstractmethod
    def open_trade(
        self,
        symbol: str,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        comment: str,
        magic: int,
    ) -> Position: ...

    @abstractmethod
    def modify_sl(self, ticket: int, sl: float) -> None: ...

    @abstractmethod
    def bid_ask(self, symbol: str) -> tuple[float, float]: ...
