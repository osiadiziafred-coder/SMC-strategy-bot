from __future__ import annotations

import pandas as pd

from smc_robot.config import LiquiditySweep, LiquidityZone, Swing
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


def detect_liquidity_zones(
    df: pd.DataFrame,
    left: int = 2,
    right: int = 2,
    equal_tolerance: float = 0.80,
    swings: list[Swing] | None = None,
    sweeps: list[LiquiditySweep] | None = None,
) -> list[LiquidityZone]:
    """Build liquidity pools from swing highs/lows and equal highs/lows.

    A swing low is sell-side liquidity (stops under the lows). A swing high
    is buy-side liquidity (stops above the highs). Two swings within
    `equal_tolerance` become an equal-high / equal-low zone.
    """
    src = ensure_ohlc(df)
    swings = list(swings) if swings is not None else detect_swings(src, left=left, right=right)
    if not swings:
        return []
    sweeps = list(sweeps) if sweeps is not None else detect_liquidity_sweeps(src, left, right, swings)

    swept_lows = {s.swept_price for s in sweeps if s.direction == "bullish"}
    swept_highs = {s.swept_price for s in sweeps if s.direction == "bearish"}

    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]
    zones: list[LiquidityZone] = []
    used_highs: set[int] = set()
    used_lows: set[int] = set()

    for i, swing in enumerate(highs):
        partner = _nearest_equal(swing, highs, i, equal_tolerance)
        if partner is not None:
            a, b = sorted((swing, partner), key=lambda s: s.index)
            if a.index not in used_highs and b.index not in used_highs:
                used_highs.add(a.index)
                used_highs.add(b.index)
                zones.append(
                    LiquidityZone(
                        index=b.index,
                        time=b.time,
                        low=min(a.price, b.price),
                        high=max(a.price, b.price),
                        direction="bearish",
                        kind="equal",
                        swept=a.price in swept_highs or b.price in swept_highs,
                    )
                )

    for i, swing in enumerate(lows):
        partner = _nearest_equal(swing, lows, i, equal_tolerance)
        if partner is not None:
            a, b = sorted((swing, partner), key=lambda s: s.index)
            if a.index not in used_lows and b.index not in used_lows:
                used_lows.add(a.index)
                used_lows.add(b.index)
                zones.append(
                    LiquidityZone(
                        index=b.index,
                        time=b.time,
                        low=min(a.price, b.price),
                        high=max(a.price, b.price),
                        direction="bullish",
                        kind="equal",
                        swept=a.price in swept_lows or b.price in swept_lows,
                    )
                )

    for swing in highs:
        if swing.index in used_highs:
            continue
        zones.append(
            LiquidityZone(
                index=swing.index,
                time=swing.time,
                low=swing.price,
                high=swing.price,
                direction="bearish",
                kind="swing",
                swept=swing.price in swept_highs,
            )
        )
    for swing in lows:
        if swing.index in used_lows:
            continue
        zones.append(
            LiquidityZone(
                index=swing.index,
                time=swing.time,
                low=swing.price,
                high=swing.price,
                direction="bullish",
                kind="swing",
                swept=swing.price in swept_lows,
            )
        )

    zones.sort(key=lambda z: z.index)
    return zones


def _nearest_equal(swing: Swing, group: list[Swing], index: int, tolerance: float) -> Swing | None:
    best: Swing | None = None
    best_dist = tolerance + 1.0
    for j, other in enumerate(group):
        if j == index:
            continue
        dist = abs(other.price - swing.price)
        if dist <= tolerance and dist < best_dist:
            best = other
            best_dist = dist
    return best


def recent_sweeps(sweeps: list[LiquiditySweep], bar_index: int, lookback: int) -> list[LiquiditySweep]:
    return [s for s in sweeps if 0 <= bar_index - s.index <= lookback]


def recent_zones(zones: list[LiquidityZone], bar_index: int, lookback: int) -> list[LiquidityZone]:
    return [z for z in zones if 0 <= bar_index - z.index <= lookback]
