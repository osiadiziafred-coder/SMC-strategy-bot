from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Side = Literal["buy", "sell"]


@dataclass(slots=True)
class Position:
    ticket: int
    symbol: str
    side: Side
    volume: float
    entry: float
    sl: float
    tp: float
    timeframe: str
    opened_at: datetime
    original_sl: float
    original_risk: float
    breakeven: bool = False
    comment: str = ""
    closed: bool = False
    exit_price: float | None = None
    exit_reason: str | None = None
    profit: float = 0.0


@dataclass(slots=True)
class AccountState:
    balance: float
    equity: float
    positions: list[Position] = field(default_factory=list)

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if not p.closed]


class Broker(ABC):
    symbol: str

    @abstractmethod
    def account(self) -> AccountState: ...

    @abstractmethod
    def candles(self, timeframe: str, count: int = 300) -> object: ...

    @abstractmethod
    def bid_ask(self) -> tuple[float, float]: ...

    @abstractmethod
    def open_trade(
        self,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        timeframe: str,
        comment: str = "",
    ) -> Position: ...

    @abstractmethod
    def modify_sl(self, ticket: int, sl: float) -> None: ...

    @abstractmethod
    def close_trade(self, ticket: int, reason: str = "manual") -> Position: ...
