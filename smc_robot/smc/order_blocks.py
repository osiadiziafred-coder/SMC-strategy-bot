"""Order block detection.

Exact programmable rules
------------------------
Bullish order block (demand):
    After a bullish BOS or MSS at bar i, look back up to ``ob_lookback_bars``
    candles. The last down-close candle (close < open) in that window is the
    order block. Zone = [that candle's low, that candle's high].

Bearish order block (supply):
    After a bearish BOS or MSS at bar i, the last up-close candle in the
    lookback window. Zone = [low, high] of that candle.

Impulse filter:
    The absolute move from the OB candle close to the structure-break close
    must be >= ``ob_impulse_atr_mult * ATR(14)``. Weak / overlapping breaks
    do not create order blocks.

Mitigation:
    Bullish OB is fully mitigated when a later bar closes below zone.low.
    Bearish OB is fully mitigated when a later bar closes above zone.high.
    A tap (range overlap without a closing break) is allowed and is the
    intended entry interaction.

Age:
    An OB older than ``ob_max_age_bars`` from the last bar is ignored for
    new entries, even if unmitigated.
"""

from __future__ import annotations

from smc_robot.models import Candle, Direction, EventType, StructureEvent, Zone, ZoneKind
from smc_robot.smc.indicators import atr


def detect_order_blocks(
    candles: list[Candle],
    events: list[StructureEvent],
    lookback: int,
    impulse_atr_mult: float,
    atr_period: int,
) -> list[Zone]:
    if len(candles) < 5:
        return []
    current_atr = atr(candles, atr_period)
    min_impulse = impulse_atr_mult * current_atr if current_atr > 0 else 0.0
    blocks: list[Zone] = []
    seen: set[int] = set()
    for event in events:
        if event.event_type not in (EventType.BOS, EventType.MSS):
            continue
        start = max(0, event.index - lookback)
        ob_index: int | None = None
        if event.direction == Direction.BUY:
            for j in range(event.index - 1, start - 1, -1):
                if candles[j].bearish:
                    ob_index = j
                    break
        else:
            for j in range(event.index - 1, start - 1, -1):
                if candles[j].bullish:
                    ob_index = j
                    break
        if ob_index is None or ob_index in seen:
            continue
        ob_candle = candles[ob_index]
        impulse = abs(candles[event.index].close - ob_candle.close)
        if impulse < min_impulse:
            continue
        seen.add(ob_index)
        blocks.append(
            Zone(
                kind=ZoneKind.ORDER_BLOCK,
                direction=event.direction,
                index=ob_index,
                time=ob_candle.time,
                low=ob_candle.low,
                high=ob_candle.high,
                extra={
                    "created_by": event.event_type.value,
                    "event_index": event.index,
                    "impulse": impulse,
                },
            )
        )
    return blocks


def annotate_mitigation(candles: list[Candle], blocks: list[Zone]) -> list[Zone]:
    live: list[Zone] = []
    for block in blocks:
        mitigated = False
        for candle in candles[block.index + 1 :]:
            if block.direction == Direction.BUY and candle.close < block.low:
                mitigated = True
                break
            if block.direction == Direction.SELL and candle.close > block.high:
                mitigated = True
                break
        extra = dict(block.extra)
        extra["mitigated"] = mitigated
        extra["tapped"] = _tapped(candles, block)
        updated = block.model_copy(update={"extra": extra})
        if not mitigated:
            live.append(updated)
    return live


def _tapped(candles: list[Candle], block: Zone) -> bool:
    for candle in candles[block.index + 1 :]:
        if block.overlaps(candle.low, candle.high):
            return True
    return False


def interacting_blocks(
    candles: list[Candle],
    blocks: list[Zone],
    direction: Direction,
    max_age: int,
) -> list[Zone]:
    if not candles:
        return []
    last = candles[-1]
    last_index = len(candles) - 1
    out: list[Zone] = []
    for block in blocks:
        if block.direction != direction:
            continue
        if last_index - block.index > max_age:
            continue
        if not block.overlaps(last.low, last.high) and not block.contains(last.close):
            continue
        if block.direction == Direction.BUY and last.close < block.low:
            continue
        if block.direction == Direction.SELL and last.close > block.high:
            continue
        out.append(block)
    return out
