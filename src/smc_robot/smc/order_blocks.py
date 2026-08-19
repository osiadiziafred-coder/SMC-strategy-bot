"""Order Block detection from displacement that causes BOS / CHoCH / MSS."""

from __future__ import annotations

import pandas as pd

from smc_robot.smc.models import OrderBlock, StructureEvent, require_ohlc
from smc_robot.smc.structure import detect_structure


def _last_opposite_candle(
    data: pd.DataFrame,
    event: StructureEvent,
    lookback: int,
) -> int | None:
    start = max(0, event.index - lookback)
    if event.direction == "bullish":
        for i in range(event.index - 1, start - 1, -1):
            if float(data.at[i, "close"]) < float(data.at[i, "open"]):
                return i
    else:
        for i in range(event.index - 1, start - 1, -1):
            if float(data.at[i, "close"]) > float(data.at[i, "open"]):
                return i
    return None


def detect_order_blocks(
    df: pd.DataFrame,
    events: list[StructureEvent] | None = None,
    lookback: int = 12,
    swing_length: int = 5,
    close_break: bool = True,
    displacement_body_atr: float = 1.2,
    mark_mitigation: bool = True,
) -> list[OrderBlock]:
    """The last opposing candle before a structure break is the order block."""
    data = require_ohlc(df)
    if events is None:
        events = detect_structure(
            data,
            swing_length=swing_length,
            close_break=close_break,
            displacement_body_atr=displacement_body_atr,
        )

    blocks: list[OrderBlock] = []
    for event in events:
        idx = _last_opposite_candle(data, event, lookback)
        if idx is None:
            continue
        top = float(data.at[idx, "high"])
        bottom = float(data.at[idx, "low"])
        block = OrderBlock(
            index=idx,
            direction=event.direction,
            top=top,
            bottom=bottom,
            origin_event=event.kind,
        )
        if mark_mitigation:
            block = _with_mitigation(block, data, after=event.index)
        blocks.append(block)
    return blocks


def _with_mitigation(block: OrderBlock, data: pd.DataFrame, after: int) -> OrderBlock:
    for j in range(after + 1, len(data)):
        low = float(data.at[j, "low"])
        high = float(data.at[j, "high"])
        if block.direction == "bullish" and low <= block.bottom:
            return OrderBlock(
                index=block.index,
                direction=block.direction,
                top=block.top,
                bottom=block.bottom,
                origin_event=block.origin_event,
                mitigated=True,
            )
        if block.direction == "bearish" and high >= block.top:
            return OrderBlock(
                index=block.index,
                direction=block.direction,
                top=block.top,
                bottom=block.bottom,
                origin_event=block.origin_event,
                mitigated=True,
            )
    return block


def unmitigated_blocks(
    blocks: list[OrderBlock],
    direction: str | None = None,
) -> list[OrderBlock]:
    out = [b for b in blocks if not b.mitigated]
    if direction:
        out = [b for b in out if b.direction == direction]
    return out


def price_in_ob(price: float, block: OrderBlock) -> bool:
    return block.bottom <= price <= block.top
