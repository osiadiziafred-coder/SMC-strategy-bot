"""Market structure: trend, BOS, CHoCH, and MSS.

Exact programmable rules
------------------------
Trend is read from the last two *confirmed external* swing highs and lows
(using ``swing_n_external``):

    BULLISH  last two highs are higher highs AND last two lows are higher lows
    BEARISH  last two highs are lower highs AND last two lows are lower lows
    RANGING  any mixed combination (HH+LL, LH+HL, or fewer than two of either)

Breaks are evaluated on **candle close only**, never on a wick.

BOS — Break of Structure (trend continuation)
    BULLISH: current trend is BULLISH and close > last confirmed *internal* swing high
    BEARISH: current trend is BEARISH and close < last confirmed *internal* swing low

CHoCH — Change of Character (first internal reversal warning)
    BULLISH: current trend is BEARISH and close > last confirmed *internal* swing high
    BEARISH: current trend is BULLISH and close < last confirmed *internal* swing low

MSS — Market Structure Shift (external reversal confirmation)
    BULLISH: current trend is BEARISH and close > last confirmed *external* swing high
    BEARISH: current trend is BULLISH and close < last confirmed *external* swing low

Priority on a single bar (strongest event wins):
    MSS > CHoCH > BOS

A swing is only used as a break level after it is confirmed (index + n < current bar).
Trend is recomputed from external swings confirmed before the bar being evaluated,
so events do not look ahead.
"""

from __future__ import annotations

from smc_robot.models import (
    Candle,
    Direction,
    EventType,
    StructureEvent,
    Swing,
    SwingKind,
    Trend,
)
from smc_robot.smc.swings import detect_swings, last_swings


def classify_trend(swings: list[Swing], before_index: int) -> Trend:
    highs = last_swings(swings, SwingKind.HIGH, before_index, 2)
    lows = last_swings(swings, SwingKind.LOW, before_index, 2)
    if len(highs) < 2 or len(lows) < 2:
        return Trend.RANGING
    higher_highs = highs[-1].price > highs[-2].price
    higher_lows = lows[-1].price > lows[-2].price
    lower_highs = highs[-1].price < highs[-2].price
    lower_lows = lows[-1].price < lows[-2].price
    if higher_highs and higher_lows:
        return Trend.BULLISH
    if lower_highs and lower_lows:
        return Trend.BEARISH
    return Trend.RANGING


def _confirmed(swings: list[Swing], n: int, before_index: int, kind: SwingKind) -> list[Swing]:
    return [
        s
        for s in swings
        if s.kind == kind and s.index < before_index and s.index + n < before_index
    ]


def detect_structure_events(
    candles: list[Candle],
    internal_n: int,
    external_n: int,
) -> tuple[list[StructureEvent], Trend, list[Swing], list[Swing]]:
    internal = detect_swings(candles, internal_n)
    external = detect_swings(candles, external_n)
    events: list[StructureEvent] = []
    start = max(2 * external_n + 1, 2 * internal_n + 1)
    for i in range(start, len(candles)):
        trend = classify_trend(external, i)
        candle = candles[i]
        int_highs = _confirmed(internal, internal_n, i, SwingKind.HIGH)
        int_lows = _confirmed(internal, internal_n, i, SwingKind.LOW)
        ext_highs = _confirmed(external, external_n, i, SwingKind.HIGH)
        ext_lows = _confirmed(external, external_n, i, SwingKind.LOW)
        last_ih = int_highs[-1] if int_highs else None
        last_il = int_lows[-1] if int_lows else None
        last_eh = ext_highs[-1] if ext_highs else None
        last_el = ext_lows[-1] if ext_lows else None

        event: StructureEvent | None = None
        if trend == Trend.BEARISH and last_eh and candle.close > last_eh.price:
            event = _event(EventType.MSS, Direction.BUY, i, candle, last_eh.price)
        elif trend == Trend.BULLISH and last_el and candle.close < last_el.price:
            event = _event(EventType.MSS, Direction.SELL, i, candle, last_el.price)
        elif trend == Trend.BEARISH and last_ih and candle.close > last_ih.price:
            event = _event(EventType.CHOCH, Direction.BUY, i, candle, last_ih.price)
        elif trend == Trend.BULLISH and last_il and candle.close < last_il.price:
            event = _event(EventType.CHOCH, Direction.SELL, i, candle, last_il.price)
        elif trend == Trend.BULLISH and last_ih and candle.close > last_ih.price:
            event = _event(EventType.BOS, Direction.BUY, i, candle, last_ih.price)
        elif trend == Trend.BEARISH and last_il and candle.close < last_il.price:
            event = _event(EventType.BOS, Direction.SELL, i, candle, last_il.price)
        elif trend == Trend.RANGING:
            if last_eh and candle.close > last_eh.price:
                event = _event(EventType.MSS, Direction.BUY, i, candle, last_eh.price)
            elif last_el and candle.close < last_el.price:
                event = _event(EventType.MSS, Direction.SELL, i, candle, last_el.price)

        if event is not None:
            events.append(event)

    current_trend = classify_trend(external, len(candles))
    return events, current_trend, internal, external


def _event(
    event_type: EventType,
    direction: Direction,
    index: int,
    candle: Candle,
    level: float,
) -> StructureEvent:
    return StructureEvent(
        event_type=event_type,
        direction=direction,
        index=index,
        time=candle.time,
        level=level,
        close=candle.close,
    )


def recent_events(
    events: list[StructureEvent],
    last_index: int,
    max_age: int,
    direction: Direction | None = None,
) -> list[StructureEvent]:
    out = [e for e in events if 0 <= last_index - e.index <= max_age]
    if direction is not None:
        out = [e for e in out if e.direction == direction]
    return out
