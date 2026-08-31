"""Historical-style OHLCV used when MT5 is not connected.

Bars are generated as a time-ordered gold-like series, then aggregated to M30/H1.
Training labels still come from future candles only, never from these helpers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from smc_robot.models import Candle


def gold_like_m15(n: int = 720, seed: int = 11, start_price: float = 2340.0) -> list[Candle]:
    rng = np.random.default_rng(seed)
    price = start_price
    stamp = datetime(2023, 6, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i in range(n):
        regime = np.sin(i / 55.0) * 0.35 + np.sin(i / 17.0) * 0.12
        shock = float(rng.normal(0.0, 1.15))
        open_ = price
        close = max(10.0, open_ + regime + shock)
        wick_up = abs(float(rng.normal(0.45, 0.25)))
        wick_dn = abs(float(rng.normal(0.45, 0.25)))
        high = max(open_, close) + wick_up
        low = min(open_, close) - wick_dn
        volume = float(rng.integers(180, 2800))
        spread = float(max(8.0, rng.normal(18.0, 4.0)))
        candles.append(
            Candle(
                time=stamp,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                spread=spread,
            )
        )
        price = close
        stamp += timedelta(minutes=15)
    return candles


def aggregate(candles: list[Candle], group: int) -> list[Candle]:
    out: list[Candle] = []
    for i in range(0, len(candles) - group + 1, group):
        chunk = candles[i : i + group]
        out.append(
            Candle(
                time=chunk[-1].time,
                open=chunk[0].open,
                high=max(c.high for c in chunk),
                low=min(c.low for c in chunk),
                close=chunk[-1].close,
                volume=sum(c.volume for c in chunk),
                spread=chunk[-1].spread,
            )
        )
    return out


def training_frames(n: int = 720, seed: int = 11) -> tuple[list[Candle], list[Candle], list[Candle]]:
    m15 = gold_like_m15(n=n, seed=seed)
    return aggregate(m15, 4), aggregate(m15, 2), m15
