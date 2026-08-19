"""BOS, CHoCH, and MSS market-structure engine."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from smc_robot.smc.models import StructureEvent, SwingPoint, average_true_range, require_ohlc
from smc_robot.smc.swings import detect_swings

Trend = Literal["bullish", "bearish"]


def _is_displacement(
    df: pd.DataFrame,
    index: int,
    atr: pd.Series,
    body_atr: float,
) -> bool:
    body = abs(float(df.at[index, "close"]) - float(df.at[index, "open"]))
    return body >= body_atr * float(atr.iloc[index])


def detect_structure(
    df: pd.DataFrame,
    swing_length: int = 5,
    close_break: bool = True,
    displacement_body_atr: float = 1.2,
) -> list[StructureEvent]:
    """Walk candles forward and classify BOS / CHoCH / MSS.

    * **BOS** — break of the latest swing in the current trend direction
      (continuation).
    * **CHoCH** — first break of the latest swing against the current trend.
    * **MSS** — CHoCH that prints with displacement (impulse body).
    """
    data = require_ohlc(df)
    swings = detect_swings(data, length=swing_length)
    if not swings:
        return []

    atr = average_true_range(data)
    events: list[StructureEvent] = []
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    trend: Trend | None = None
    # A fractal swing is only known after ``swing_length`` bars on the right.
    confirmed_at: dict[int, list[SwingPoint]] = {}
    for swing in swings:
        confirmed_at.setdefault(swing.index + swing_length, []).append(swing)

    for i in range(len(data)):
        for swing in confirmed_at.get(i, []):
            if swing.kind == "high":
                last_high = swing
            else:
                last_low = swing

        close = float(data.at[i, "close"])
        high = float(data.at[i, "high"])
        low = float(data.at[i, "low"])
        bull_break_level = close if close_break else high
        bear_break_level = close if close_break else low
        displaced = _is_displacement(data, i, atr, displacement_body_atr)

        if last_high is not None and i > last_high.index and bull_break_level > last_high.price:
            if trend == "bearish":
                kind = "MSS" if displaced else "CHOCH"
                events.append(
                    StructureEvent(
                        index=i,
                        kind=kind,
                        direction="bullish",
                        level=last_high.price,
                        broken_index=last_high.index,
                        displacement=displaced,
                    )
                )
                trend = "bullish"
            else:
                if trend is None:
                    trend = "bullish"
                events.append(
                    StructureEvent(
                        index=i,
                        kind="BOS",
                        direction="bullish",
                        level=last_high.price,
                        broken_index=last_high.index,
                        displacement=displaced,
                    )
                )
                trend = "bullish"
            last_high = None

        elif last_low is not None and i > last_low.index and bear_break_level < last_low.price:
            if trend == "bullish":
                kind = "MSS" if displaced else "CHOCH"
                events.append(
                    StructureEvent(
                        index=i,
                        kind=kind,
                        direction="bearish",
                        level=last_low.price,
                        broken_index=last_low.index,
                        displacement=displaced,
                    )
                )
                trend = "bearish"
            else:
                if trend is None:
                    trend = "bearish"
                events.append(
                    StructureEvent(
                        index=i,
                        kind="BOS",
                        direction="bearish",
                        level=last_low.price,
                        broken_index=last_low.index,
                        displacement=displaced,
                    )
                )
                trend = "bearish"
            last_low = None

    return events


def current_bias(events: list[StructureEvent]) -> Trend | None:
    if not events:
        return None
    return events[-1].direction
