from __future__ import annotations

import pandas as pd

from smc_robot.config import Swing
from smc_robot.smc.candles import ensure_ohlc


def detect_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> list[Swing]:
    """Fractal swing highs and lows.

    A swing high is a local peak: strictly higher than `left` bars before it,
    and at least as high as `right` bars after it. Lows are the mirror image.
    """
    src = ensure_ohlc(df)
    if len(src) < left + right + 1:
        return []

    highs = src["high"].to_numpy(dtype=float)
    lows = src["low"].to_numpy(dtype=float)
    times = src["time"].tolist()
    swings: list[Swing] = []

    for i in range(left, len(src) - right):
        left_highs = highs[i - left : i]
        right_highs = highs[i + 1 : i + right + 1]
        left_lows = lows[i - left : i]
        right_lows = lows[i + 1 : i + right + 1]
        if left_highs.size and right_highs.size and highs[i] > left_highs.max() and highs[i] >= right_highs.max():
            swings.append(Swing(index=i, time=times[i], price=float(highs[i]), kind="high"))
        if left_lows.size and right_lows.size and lows[i] < left_lows.min() and lows[i] <= right_lows.min():
            swings.append(Swing(index=i, time=times[i], price=float(lows[i]), kind="low"))

    swings.sort(key=lambda s: (s.index, 0 if s.kind == "high" else 1))
    return swings
