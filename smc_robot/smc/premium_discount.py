"""Premium / discount from the relevant external swing range."""

from __future__ import annotations

from smc_robot.models import Candle, Direction, PremiumDiscount, Swing, SwingKind


def structure_premium_discount(
    candles: list[Candle],
    external_swings: list[Swing],
    direction: Direction,
    discount_max: float = 0.50,
    premium_min: float = 0.50,
) -> PremiumDiscount:
    highs = [s.price for s in external_swings if s.kind == SwingKind.HIGH]
    lows = [s.price for s in external_swings if s.kind == SwingKind.LOW]
    if len(highs) < 1 or len(lows) < 1 or not candles:
        return PremiumDiscount()
    range_high = max(highs[-4:]) if len(highs) >= 4 else max(highs)
    range_low = min(lows[-4:]) if len(lows) >= 4 else min(lows)
    width = range_high - range_low
    if width <= 0:
        return PremiumDiscount(range_low=range_low, range_high=range_high, position=0.5)
    price = candles[-1].close
    position = max(0.0, min(1.0, (price - range_low) / width))
    in_discount = position <= discount_max
    in_premium = position >= premium_min
    return PremiumDiscount(
        range_low=range_low,
        range_high=range_high,
        position=position,
        in_discount=in_discount if direction == Direction.BUY else False,
        in_premium=in_premium if direction == Direction.SELL else False,
    )


def favors_setup(pd: PremiumDiscount, direction: Direction) -> bool:
    if direction == Direction.BUY:
        return pd.in_discount
    return pd.in_premium
