"""Smart Money Concepts market-structure indicators.

This module implements the building blocks that the strategy relies on:

* **Swing points** - fractal highs/lows used to define market structure.
* **Break of Structure (BOS)** - continuation of the prevailing trend when
  price closes beyond the most recent swing in the trend direction.
* **Change of Character (CHoCH)** - the first structural break against the
  prevailing trend, signalling a potential reversal.
* **Order blocks** - the last opposite-colour candle before an impulsive move
  that breaks structure.
* **Fair Value Gaps (FVG)** - three-candle imbalances left by impulsive moves.

The functions are intentionally simple and vectorised where practical so they
are easy to test and reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float
    kind: str  # "high" or "low"


@dataclass(frozen=True)
class StructureEvent:
    index: int
    price: float
    event: str  # "BOS" or "CHoCH"
    direction: Direction


@dataclass(frozen=True)
class OrderBlock:
    index: int
    direction: Direction
    top: float
    bottom: float

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass(frozen=True)
class FairValueGap:
    index: int
    direction: Direction
    top: float
    bottom: float


def find_swing_points(df: pd.DataFrame, lookback: int = 3) -> list[SwingPoint]:
    """Return fractal swing highs and lows.

    A swing high at position ``i`` has a high strictly greater than the highs of
    the ``lookback`` candles on each side; a swing low is the mirror image.
    """

    if lookback < 1:
        raise ValueError("lookback must be >= 1")

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    swings: list[SwingPoint] = []

    for i in range(lookback, n - lookback):
        window_high = highs[i - lookback : i + lookback + 1]
        window_low = lows[i - lookback : i + lookback + 1]

        if highs[i] == window_high.max() and (window_high == highs[i]).sum() == 1:
            swings.append(SwingPoint(index=i, price=float(highs[i]), kind="high"))
        elif lows[i] == window_low.min() and (window_low == lows[i]).sum() == 1:
            swings.append(SwingPoint(index=i, price=float(lows[i]), kind="low"))

    return swings


def detect_structure(df: pd.DataFrame, lookback: int = 3) -> list[StructureEvent]:
    """Detect BOS and CHoCH events from confirmed swing points.

    The algorithm walks the candles forward, tracking the most recent confirmed
    swing high and swing low. When a candle *closes* beyond one of those swings,
    a structural break is recorded. A break that agrees with the current trend is
    a BOS; the first break that flips the trend is a CHoCH.
    """

    swings = find_swing_points(df, lookback=lookback)
    closes = df["close"].to_numpy()
    events: list[StructureEvent] = []

    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    trend: Direction | None = None

    # Swings are confirmed ``lookback`` candles after they occur.
    swing_by_confirm: dict[int, list[SwingPoint]] = {}
    for sw in swings:
        swing_by_confirm.setdefault(sw.index + lookback, []).append(sw)

    for i in range(len(df)):
        price = float(closes[i])

        if last_high is not None and price > last_high.price:
            direction = Direction.BULLISH
            event = "BOS" if trend == Direction.BULLISH else "CHoCH"
            events.append(StructureEvent(index=i, price=price, event=event, direction=direction))
            trend = Direction.BULLISH
            last_high = None  # require a fresh swing high before the next break
        elif last_low is not None and price < last_low.price:
            direction = Direction.BEARISH
            event = "BOS" if trend == Direction.BEARISH else "CHoCH"
            events.append(StructureEvent(index=i, price=price, event=event, direction=direction))
            trend = Direction.BEARISH
            last_low = None

        for sw in swing_by_confirm.get(i, []):
            if sw.kind == "high":
                last_high = sw
            else:
                last_low = sw

    return events


def find_order_block(df: pd.DataFrame, break_index: int, direction: Direction) -> OrderBlock | None:
    """Find the order block preceding a structural break.

    For a bullish break, the order block is the last bearish (down) candle
    before the impulsive move up; for a bearish break it is the last bullish
    (up) candle before the impulsive move down.
    """

    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    for i in range(break_index, -1, -1):
        is_bearish_candle = closes[i] < opens[i]
        is_bullish_candle = closes[i] > opens[i]
        if direction == Direction.BULLISH and is_bearish_candle:
            return OrderBlock(index=i, direction=direction, top=float(highs[i]), bottom=float(lows[i]))
        if direction == Direction.BEARISH and is_bullish_candle:
            return OrderBlock(index=i, direction=direction, top=float(highs[i]), bottom=float(lows[i]))

    return None


def find_fair_value_gaps(df: pd.DataFrame) -> list[FairValueGap]:
    """Detect three-candle fair value gaps (imbalances).

    A bullish FVG exists when candle ``i-2``'s high is below candle ``i``'s low,
    leaving an untraded gap; a bearish FVG is the mirror image.
    """

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    gaps: list[FairValueGap] = []

    for i in range(2, len(df)):
        if highs[i - 2] < lows[i]:
            gaps.append(
                FairValueGap(
                    index=i,
                    direction=Direction.BULLISH,
                    top=float(lows[i]),
                    bottom=float(highs[i - 2]),
                )
            )
        elif lows[i - 2] > highs[i]:
            gaps.append(
                FairValueGap(
                    index=i,
                    direction=Direction.BEARISH,
                    top=float(lows[i - 2]),
                    bottom=float(highs[i]),
                )
            )

    return gaps
