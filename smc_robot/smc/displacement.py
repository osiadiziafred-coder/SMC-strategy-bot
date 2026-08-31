"""Displacement: impulse body vs ATR, wick/body, consecutive closes."""

from __future__ import annotations

from smc_robot.models import Candle, Displacement
from smc_robot.smc.indicators import atr


def detect_displacement(
    candles: list[Candle],
    atr_period: int = 14,
    body_atr_min: float = 1.10,
    lookback: int = 4,
) -> Displacement:
    if len(candles) < 3:
        return Displacement()
    current_atr = atr(candles, atr_period)
    window = candles[-lookback:]
    best = max(window, key=lambda c: c.body)
    body_atr = (best.body / current_atr) if current_atr > 0 else 0.0
    wick_body = ((best.range - best.body) / best.body) if best.body > 0 else 99.0
    consecutive = 1
    last = candles[-1]
    for candle in reversed(candles[:-1]):
        same = (last.bullish and candle.bullish) or (last.bearish and candle.bearish)
        if not same:
            break
        consecutive += 1
        if consecutive >= 6:
            break
    return Displacement(
        body_atr=body_atr,
        wick_body_ratio=wick_body,
        consecutive=consecutive,
        strong=body_atr >= body_atr_min and wick_body <= 1.20,
    )
