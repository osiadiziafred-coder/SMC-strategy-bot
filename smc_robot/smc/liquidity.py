from __future__ import annotations

import pandas as pd

from smc_robot.config import LiquiditySweep, Swing
from smc_robot.smc.candles import ensure_ohlc
from smc_robot.smc.swings import detect_swings


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    left: int = 2,
    right: int = 2,
    swings: list[Swing] | None = None,
) -> list[LiquiditySweep]:
    """Mark stop-hunt sweeps of confirmed swing liquidity.

    Sell-side sweep (bullish): price wicks below a swing low, then closes back
    above it. Buy-side sweep (bearish): price wicks above a swing high, then
    closes back below it.
    """
    src = ensure_ohlc(df)
    swings = list(swings) if swings is not None else detect_swings(src, left=left, right=right)
    if not swings:
        return []

    highs = src["high"].to_numpy(dtype=float)
    lows = src["low"].to_numpy(dtype=float)
    closes = src["close"].to_numpy(dtype=float)
    times = src["time"].tolist()

    swing_ready_at: dict[int, list[Swing]] = {}
    for swing in swings:
        swing_ready_at.setdefault(swing.index + right, []).append(swing)

    known_highs: list[Swing] = []
    known_lows: list[Swing] = []
    swept_highs: set[int] = set()
    swept_lows: set[int] = set()
    sweeps: list[LiquiditySweep] = []

    for i in range(len(src)):
        for swing in swing_ready_at.get(i, []):
            if swing.kind == "high":
                known_highs.append(swing)
            else:
                known_lows.append(swing)

        for swing in known_lows:
            if swing.index in swept_lows or swing.index >= i:
                continue
            if lows[i] < swing.price and closes[i] > swing.price:
                sweeps.append(
                    LiquiditySweep(
                        index=i,
                        time=times[i],
                        direction="bullish",
                        swept_price=float(swing.price),
                        wick=float(lows[i]),
                        close=float(closes[i]),
                    )
                )
                swept_lows.add(swing.index)

        for swing in known_highs:
            if swing.index in swept_highs or swing.index >= i:
                continue
            if highs[i] > swing.price and closes[i] < swing.price:
                sweeps.append(
                    LiquiditySweep(
                        index=i,
                        time=times[i],
                        direction="bearish",
                        swept_price=float(swing.price),
                        wick=float(highs[i]),
                        close=float(closes[i]),
                    )
                )
                swept_highs.add(swing.index)

    return sweeps


def recent_sweeps(sweeps: list[LiquiditySweep], bar_index: int, lookback: int) -> list[LiquiditySweep]:
    return [s for s in sweeps if 0 <= bar_index - s.index <= lookback]
