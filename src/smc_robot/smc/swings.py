"""Swing high / swing low detection for SMC market structure."""

from __future__ import annotations

import numpy as np
import pandas as pd

from smc_robot.smc.models import SwingPoint, require_ohlc


def detect_swings(df: pd.DataFrame, length: int = 5) -> list[SwingPoint]:
    """Return confirmed fractal swing highs and lows.

    A bar is a swing high when its high is strictly the highest of the
    ``length`` bars on each side. Same idea for swing lows.
    """
    if length < 1:
        raise ValueError("swing length must be >= 1")
    data = require_ohlc(df)
    highs = data["high"].to_numpy(dtype=float)
    lows = data["low"].to_numpy(dtype=float)
    n = len(data)
    swings: list[SwingPoint] = []

    for i in range(length, n - length):
        left_h = highs[i - length : i]
        right_h = highs[i + 1 : i + length + 1]
        left_l = lows[i - length : i]
        right_l = lows[i + 1 : i + length + 1]
        # Left-strict so a plateau counts once (the first bar of the run).
        is_high = bool(highs[i] > left_h.max() and highs[i] >= right_h.max())
        is_low = bool(lows[i] < left_l.min() and lows[i] <= right_l.min())
        if is_high:
            swings.append(SwingPoint(index=i, price=float(highs[i]), kind="high"))
        if is_low:
            swings.append(SwingPoint(index=i, price=float(lows[i]), kind="low"))

    swings.sort(key=lambda s: (s.index, 0 if s.kind == "low" else 1))
    return swings


def swings_as_series(df: pd.DataFrame, length: int = 5) -> pd.DataFrame:
    data = require_ohlc(df)
    out = data.copy()
    out["swing_high"] = np.nan
    out["swing_low"] = np.nan
    for swing in detect_swings(data, length=length):
        if swing.kind == "high":
            out.at[swing.index, "swing_high"] = swing.price
        else:
            out.at[swing.index, "swing_low"] = swing.price
    return out
