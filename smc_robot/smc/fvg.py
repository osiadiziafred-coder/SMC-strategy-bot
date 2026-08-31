"""Fair Value Gap detection.

Exact programmable rules
------------------------
A Fair Value Gap is a three-candle imbalance centred on bar i-1:

    Bullish FVG at i:  low[i] > high[i-2]
        zone = [high[i-2], low[i]]

    Bearish FVG at i:  high[i] < low[i-2]
        zone = [high[i], low[i-2]]

Minimum size:
    (zone.high - zone.low) >= fvg_min_atr_mult * ATR(14)

Fill / invalidation:
    Bullish FVG is fully filled when a later bar's low <= zone.low
    Bearish FVG is fully filled when a later bar's high >= zone.high
    Partial fills remain valid confluence until the gap is fully traded through.

Interaction for entry:
    The current bar's range overlaps the unfilled zone, and the close has not
    broken through the far side of the gap.
"""

from __future__ import annotations

from smc_robot.models import Candle, Direction, Zone, ZoneKind
from smc_robot.smc.indicators import atr


def detect_fvgs(
    candles: list[Candle],
    min_atr_mult: float,
    atr_period: int,
) -> list[Zone]:
    if len(candles) < 3:
        return []
    current_atr = atr(candles, atr_period)
    min_size = min_atr_mult * current_atr if current_atr > 0 else 0.0
    gaps: list[Zone] = []
    for i in range(2, len(candles)):
        left = candles[i - 2]
        right = candles[i]
        if right.low > left.high:
            low, high = left.high, right.low
            if high - low >= min_size:
                gaps.append(
                    _gap(Direction.BUY, i, right, low, high, candles[i - 1].body)
                )
        elif right.high < left.low:
            low, high = right.high, left.low
            if high - low >= min_size:
                gaps.append(
                    _gap(Direction.SELL, i, right, low, high, candles[i - 1].body)
                )
    return gaps


def _gap(
    direction: Direction,
    index: int,
    candle: Candle,
    low: float,
    high: float,
    impulse_body: float,
) -> Zone:
    return Zone(
        kind=ZoneKind.FVG,
        direction=direction,
        index=index,
        time=candle.time,
        low=low,
        high=high,
        extra={"impulse_body": impulse_body},
    )


def unfilled_fvgs(candles: list[Candle], gaps: list[Zone]) -> list[Zone]:
    live: list[Zone] = []
    for gap in gaps:
        filled = False
        for candle in candles[gap.index + 1 :]:
            if gap.direction == Direction.BUY and candle.low <= gap.low:
                filled = True
                break
            if gap.direction == Direction.SELL and candle.high >= gap.high:
                filled = True
                break
        extra = dict(gap.extra)
        extra["filled"] = filled
        updated = gap.model_copy(update={"extra": extra})
        if not filled:
            live.append(updated)
    return live


def interacting_fvgs(candles: list[Candle], gaps: list[Zone], direction: Direction) -> list[Zone]:
    if not candles:
        return []
    last = candles[-1]
    out: list[Zone] = []
    for gap in gaps:
        if gap.direction != direction:
            continue
        if not gap.overlaps(last.low, last.high) and not gap.contains(last.close):
            continue
        if gap.direction == Direction.BUY and last.close < gap.low:
            continue
        if gap.direction == Direction.SELL and last.close > gap.high:
            continue
        out.append(gap)
    return out
