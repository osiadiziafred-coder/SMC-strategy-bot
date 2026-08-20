from __future__ import annotations

import pandas as pd

from smc_robot.config import StructureEvent, Zone
from smc_robot.smc.candles import ensure_ohlc


def detect_order_blocks(df: pd.DataFrame, events: list[StructureEvent], lookback: int = 15) -> list[Zone]:
    """Order blocks are the last opposite candle before a BOS / CHoCH / MSS impulse.

    Bullish OB: last bearish candle before a bullish structure break.
    Bearish OB: last bullish candle before a bearish structure break.
    """
    src = ensure_ohlc(df)
    if src.empty or not events:
        return []

    opens = src["open"].to_numpy(dtype=float)
    closes = src["close"].to_numpy(dtype=float)
    highs = src["high"].to_numpy(dtype=float)
    lows = src["low"].to_numpy(dtype=float)
    times = src["time"].tolist()
    zones: list[Zone] = []
    seen: set[int] = set()

    for event in events:
        start = max(0, event.index - lookback)
        ob_index = None
        if event.direction == "bullish":
            for i in range(event.index - 1, start - 1, -1):
                if closes[i] < opens[i]:
                    ob_index = i
                    break
        else:
            for i in range(event.index - 1, start - 1, -1):
                if closes[i] > opens[i]:
                    ob_index = i
                    break
        if ob_index is None or ob_index in seen:
            continue
        seen.add(ob_index)
        low = float(lows[ob_index])
        high = float(highs[ob_index])
        mitigated = False
        after = ob_index + 1
        if after < len(closes):
            if event.direction == "bullish":
                mitigated = bool((closes[after:] < low).any())
            else:
                mitigated = bool((closes[after:] > high).any())
        zones.append(
            Zone(
                start_index=ob_index,
                end_index=ob_index,
                time=times[ob_index],
                low=low,
                high=high,
                direction=event.direction,
                kind="OB",
                mitigated=mitigated,
            )
        )
    return zones
