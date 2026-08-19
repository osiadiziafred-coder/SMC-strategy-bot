"""Fair Value Gap (FVG / imbalance) detection and mitigation."""

from __future__ import annotations

import pandas as pd

from smc_robot.smc.models import FairValueGap, require_ohlc


def detect_fvgs(
    df: pd.DataFrame,
    min_size: float = 0.0,
    mark_mitigation: bool = True,
) -> list[FairValueGap]:
    """Detect 3-candle fair value gaps.

    Bullish FVG: ``high[i-2] < low[i]`` (gap up).
    Bearish FVG: ``low[i-2] > high[i]`` (gap down).
    The middle candle is the displacement candle at index ``i-1``.
    """
    data = require_ohlc(df)
    highs = data["high"].to_numpy(dtype=float)
    lows = data["low"].to_numpy(dtype=float)
    n = len(data)
    gaps: list[FairValueGap] = []

    for i in range(2, n):
        # Bullish imbalance between candle i-2 high and candle i low.
        if lows[i] > highs[i - 2]:
            bottom = float(highs[i - 2])
            top = float(lows[i])
            if top - bottom >= min_size:
                gaps.append(
                    FairValueGap(index=i - 1, direction="bullish", top=top, bottom=bottom)
                )
        # Bearish imbalance between candle i-2 low and candle i high.
        elif highs[i] < lows[i - 2]:
            top = float(lows[i - 2])
            bottom = float(highs[i])
            if top - bottom >= min_size:
                gaps.append(
                    FairValueGap(index=i - 1, direction="bearish", top=top, bottom=bottom)
                )

    if mark_mitigation:
        return [_with_mitigation(gap, data) for gap in gaps]
    return gaps


def _with_mitigation(gap: FairValueGap, data: pd.DataFrame) -> FairValueGap:
    for j in range(gap.index + 2, len(data)):
        low = float(data.at[j, "low"])
        high = float(data.at[j, "high"])
        if gap.direction == "bullish" and low <= gap.bottom:
            return FairValueGap(
                index=gap.index,
                direction=gap.direction,
                top=gap.top,
                bottom=gap.bottom,
                mitigated=True,
                mitigate_index=j,
            )
        if gap.direction == "bearish" and high >= gap.top:
            return FairValueGap(
                index=gap.index,
                direction=gap.direction,
                top=gap.top,
                bottom=gap.bottom,
                mitigated=True,
                mitigate_index=j,
            )
    return gap


def unmitigated(gaps: list[FairValueGap], direction: str | None = None) -> list[FairValueGap]:
    out = [g for g in gaps if not g.mitigated]
    if direction:
        out = [g for g in out if g.direction == direction]
    return out


def price_in_fvg(price: float, gap: FairValueGap) -> bool:
    return gap.bottom <= price <= gap.top
