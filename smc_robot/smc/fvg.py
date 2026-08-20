from __future__ import annotations

import pandas as pd

from smc_robot.config import Zone
from smc_robot.smc.candles import ensure_ohlc


def detect_fvg(df: pd.DataFrame) -> list[Zone]:
    """3-candle Fair Value Gaps.

    Bullish FVG: candle[i+1].low > candle[i-1].high (gap up left by displacement).
    Bearish FVG: candle[i+1].high < candle[i-1].low (gap down).
    A gap is mitigated once a later close fully trades through it.
    """
    src = ensure_ohlc(df)
    if len(src) < 3:
        return []

    highs = src["high"].to_numpy(dtype=float)
    lows = src["low"].to_numpy(dtype=float)
    closes = src["close"].to_numpy(dtype=float)
    times = src["time"].tolist()
    zones: list[Zone] = []

    for i in range(1, len(src) - 1):
        prev_high = highs[i - 1]
        prev_low = lows[i - 1]
        next_low = lows[i + 1]
        next_high = highs[i + 1]
        if next_low > prev_high:
            zones.append(
                Zone(
                    start_index=i - 1,
                    end_index=i + 1,
                    time=times[i],
                    low=float(prev_high),
                    high=float(next_low),
                    direction="bullish",
                    kind="FVG",
                    mitigated=_mitigated_after(closes, i + 2, float(prev_high), "bullish"),
                )
            )
        elif next_high < prev_low:
            zones.append(
                Zone(
                    start_index=i - 1,
                    end_index=i + 1,
                    time=times[i],
                    low=float(next_high),
                    high=float(prev_low),
                    direction="bearish",
                    kind="FVG",
                    mitigated=_mitigated_after(closes, i + 2, float(prev_low), "bearish"),
                )
            )
    return zones


def _mitigated_after(closes, start: int, level: float, direction: str) -> bool:
    if start >= len(closes):
        return False
    if direction == "bullish":
        return bool((closes[start:] < level).any())
    return bool((closes[start:] > level).any())


def unmitigated(zones: list[Zone], direction: str | None = None) -> list[Zone]:
    out = [z for z in zones if not z.mitigated]
    if direction:
        out = [z for z in out if z.direction == direction]
    return out


def price_in_zone(price_low: float, price_high: float, zone: Zone) -> bool:
    return price_low <= zone.high and price_high >= zone.low
