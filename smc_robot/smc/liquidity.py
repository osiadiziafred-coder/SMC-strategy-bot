"""Liquidity zones and liquidity sweeps.

Exact programmable rules
------------------------
Liquidity pool:
    Every confirmed swing high is buy-side liquidity.
    Every confirmed swing low is sell-side liquidity.

Equal-high / equal-low zone:
    Two or more swing highs (or lows) whose prices are within
    ``equal_level_atr_mult * ATR`` of each other. The zone price is the
    mean of the clustered swings. Equal liquidity is treated as a stronger
    pool than a single swing.

Sell-side liquidity sweep (bullish catalyst):
    A bar prints low < pool.price AND closes back above pool.price.
    The pool must be a swing low confirmed before this bar.

Buy-side liquidity sweep (bearish catalyst):
    A bar prints high > pool.price AND closes back below pool.price.

A sweep is "recent" when it occurred on the current closed bar or within
``sweep_lookback_bars`` bars.
"""

from __future__ import annotations

from dataclasses import dataclass

from smc_robot.models import Candle, Direction, LiquiditySweep, Swing, SwingKind, Zone, ZoneKind
from smc_robot.smc.indicators import atr


@dataclass
class LiquidityPool:
    kind: SwingKind
    price: float
    index: int
    equal: bool
    members: int


def build_liquidity_pools(
    swings: list[Swing],
    candles: list[Candle],
    equal_atr_mult: float,
    atr_period: int,
) -> list[LiquidityPool]:
    current_atr = atr(candles, atr_period)
    tolerance = equal_atr_mult * current_atr if current_atr > 0 else 0.0
    pools: list[LiquidityPool] = []
    for kind in (SwingKind.HIGH, SwingKind.LOW):
        selected = [s for s in swings if s.kind == kind]
        used: set[int] = set()
        for i, swing in enumerate(selected):
            if i in used:
                continue
            cluster = [swing]
            used.add(i)
            for j in range(i + 1, len(selected)):
                if j in used:
                    continue
                if abs(selected[j].price - swing.price) <= tolerance:
                    cluster.append(selected[j])
                    used.add(j)
            price = sum(s.price for s in cluster) / len(cluster)
            last = max(cluster, key=lambda s: s.index)
            pools.append(
                LiquidityPool(
                    kind=kind,
                    price=price,
                    index=last.index,
                    equal=len(cluster) >= 2,
                    members=len(cluster),
                )
            )
    return pools


def liquidity_zones(pools: list[LiquidityPool], candles: list[Candle], atr_period: int) -> list[Zone]:
    pad = atr(candles, atr_period) * 0.05
    zones: list[Zone] = []
    for pool in pools:
        direction = Direction.SELL if pool.kind == SwingKind.HIGH else Direction.BUY
        candle = candles[pool.index]
        zones.append(
            Zone(
                kind=ZoneKind.LIQUIDITY,
                direction=direction,
                index=pool.index,
                time=candle.time,
                low=pool.price - pad,
                high=pool.price + pad,
                extra={"equal": pool.equal, "members": pool.members, "price": pool.price},
            )
        )
    return zones


def detect_sweeps(
    candles: list[Candle],
    pools: list[LiquidityPool],
) -> list[LiquiditySweep]:
    sweeps: list[LiquiditySweep] = []
    for i, candle in enumerate(candles):
        for pool in pools:
            if pool.index >= i:
                continue
            if pool.kind == SwingKind.LOW and candle.low < pool.price and candle.close > pool.price:
                sweeps.append(
                    LiquiditySweep(
                        direction=Direction.BUY,
                        index=i,
                        time=candle.time,
                        swept_price=pool.price,
                        wick=candle.low,
                        close=candle.close,
                        equal_liquidity=pool.equal,
                    )
                )
            elif pool.kind == SwingKind.HIGH and candle.high > pool.price and candle.close < pool.price:
                sweeps.append(
                    LiquiditySweep(
                        direction=Direction.SELL,
                        index=i,
                        time=candle.time,
                        swept_price=pool.price,
                        wick=candle.high,
                        close=candle.close,
                        equal_liquidity=pool.equal,
                    )
                )
    return _dedupe_sweeps(sweeps)


def _dedupe_sweeps(sweeps: list[LiquiditySweep]) -> list[LiquiditySweep]:
    best: dict[tuple[int, str], LiquiditySweep] = {}
    for sweep in sweeps:
        key = (sweep.index, sweep.direction.value)
        previous = best.get(key)
        if previous is None:
            best[key] = sweep
            continue
        if sweep.equal_liquidity and not previous.equal_liquidity:
            best[key] = sweep
            continue
        prev_ext = abs(previous.wick - previous.swept_price)
        new_ext = abs(sweep.wick - sweep.swept_price)
        if new_ext > prev_ext:
            best[key] = sweep
    return sorted(best.values(), key=lambda s: s.index)


def recent_sweeps(
    sweeps: list[LiquiditySweep],
    last_index: int,
    lookback: int,
    direction: Direction,
) -> list[LiquiditySweep]:
    return [
        s
        for s in sweeps
        if s.direction == direction and 0 <= last_index - s.index <= lookback
    ]
