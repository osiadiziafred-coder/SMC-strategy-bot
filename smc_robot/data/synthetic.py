from __future__ import annotations

from datetime import datetime, timedelta, timezone

from smc_robot.models import Candle


def candles_from_ohlc(
    rows: list[tuple[float, float, float, float]],
    start: datetime | None = None,
    minutes: int = 15,
) -> list[Candle]:
    stamp = start or datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    for open_, high, low, close in rows:
        out.append(
            Candle(
                time=stamp,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=100.0,
            )
        )
        stamp += timedelta(minutes=minutes)
    return out


def _bar(open_: float, close: float, wick: float = 0.4) -> tuple[float, float, float, float]:
    high = max(open_, close) + wick
    low = min(open_, close) - wick
    return (open_, high, low, close)


def trending_impulse(
    start: float,
    bars: int,
    step: float,
    pullback: float,
    cycle: int = 8,
    minutes: int = 15,
) -> list[Candle]:
    """Stair-step series: `cycle-2` bars with `step`, then 2-bar pullback."""
    rows: list[tuple[float, float, float, float]] = []
    price = start
    for i in range(bars):
        phase = i % cycle
        if phase >= cycle - 2:
            close = price - abs(pullback)
        else:
            close = price + step
        rows.append(_bar(price, close, wick=abs(step) * 0.35 + 0.15))
        price = close
    return candles_from_ohlc(rows, minutes=minutes)


def inject_sellside_sweep(candles: list[Candle], sweep_index: int) -> list[Candle]:
    """Force a confirmed swing low then a sweep bar that closes back above it."""
    if sweep_index < 6 or sweep_index >= len(candles):
        raise ValueError("sweep_index out of range")
    updated = [c.model_copy() for c in candles]
    base = min(updated[sweep_index - 5].low, updated[sweep_index - 1].low) - 1.5
    swing = updated[sweep_index - 3]
    updated[sweep_index - 3] = swing.model_copy(update={"low": base, "close": max(swing.close, base + 0.8)})
    for offset in (-5, -4, -2, -1):
        neighbor = updated[sweep_index + offset]
        updated[sweep_index + offset] = neighbor.model_copy(update={"low": base + 1.2})
    sweep = updated[sweep_index]
    updated[sweep_index] = sweep.model_copy(
        update={
            "low": base - 1.0,
            "open": base + 0.6,
            "close": base + 1.4,
            "high": max(sweep.high, base + 1.8),
        }
    )
    return updated
