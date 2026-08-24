"""Swing high / swing low detection.

A swing is confirmed only after ``n`` bars have printed on both sides,
so historical swings do not repaint.

Rules
-----
Swing high at bar i:
    high[i] > high[j] for every j in [i-n, i) U (i, i+n]
    (strictly greater than the n bars to the left and the n bars to the right)

Swing low at bar i:
    low[i] < low[j] for every j in [i-n, i) U (i, i+n]

If two adjacent bars share the same extreme, the first bar that is strictly
greater/less than both sides wins. Unconfirmed bars at the right edge of the
series are ignored until ``n`` future bars exist.
"""

from __future__ import annotations

from smc_robot.models import Candle, Swing, SwingKind


def detect_swings(candles: list[Candle], n: int) -> list[Swing]:
    if n < 1 or len(candles) < (2 * n + 1):
        return []
    swings: list[Swing] = []
    for i in range(n, len(candles) - n):
        candle = candles[i]
        left = candles[i - n : i]
        right = candles[i + 1 : i + n + 1]
        if all(candle.high > other.high for other in left) and all(
            candle.high > other.high for other in right
        ):
            swings.append(
                Swing(kind=SwingKind.HIGH, index=i, time=candle.time, price=candle.high)
            )
        if all(candle.low < other.low for other in left) and all(
            candle.low < other.low for other in right
        ):
            swings.append(
                Swing(kind=SwingKind.LOW, index=i, time=candle.time, price=candle.low)
            )
    return swings


def last_swings(swings: list[Swing], kind: SwingKind, before_index: int, count: int = 2) -> list[Swing]:
    selected = [s for s in swings if s.kind == kind and s.index < before_index]
    return selected[-count:]
