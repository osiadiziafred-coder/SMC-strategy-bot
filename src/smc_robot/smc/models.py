from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


Direction = Literal["bullish", "bearish"]
EventKind = Literal["BOS", "CHOCH", "MSS"]
Side = Literal["buy", "sell"]


REQUIRED_COLUMNS = ("open", "high", "low", "close")


def require_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"OHLC dataframe missing columns: {missing}")
    out = df.copy()
    if "volume" not in out.columns:
        out["volume"] = 1.0
    return out.reset_index(drop=True)


def average_true_range(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def candle_direction(open_: float, close: float) -> Direction | None:
    if close > open_:
        return "bullish"
    if close < open_:
        return "bearish"
    return None


@dataclass(slots=True, frozen=True)
class SwingPoint:
    index: int
    price: float
    kind: Literal["high", "low"]


@dataclass(slots=True, frozen=True)
class StructureEvent:
    index: int
    kind: EventKind
    direction: Direction
    level: float
    broken_index: int
    displacement: bool = False


@dataclass(slots=True, frozen=True)
class FairValueGap:
    index: int
    direction: Direction
    top: float
    bottom: float
    mitigated: bool = False
    mitigate_index: int | None = None

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def size(self) -> float:
        return abs(self.top - self.bottom)


@dataclass(slots=True, frozen=True)
class OrderBlock:
    index: int
    direction: Direction
    top: float
    bottom: float
    origin_event: EventKind
    mitigated: bool = False

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass(slots=True)
class TradeSetup:
    timeframe: str
    side: Side
    entry: float
    sl: float
    tp: float
    score: int
    reason: str
    event_kind: EventKind
    ob: OrderBlock | None = None
    fvg: FairValueGap | None = None
    bar_index: int = -1

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def reward(self) -> float:
        return abs(self.tp - self.entry)

    @property
    def rr(self) -> float:
        if self.risk == 0:
            return 0.0
        return self.reward / self.risk
