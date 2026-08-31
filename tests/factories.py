from smc_robot.data.setups import bullish_structure_candles, m15_buy_setup, structure_from_swings
from smc_robot.data.synthetic import candles_from_ohlc
from smc_robot.models import Candle


def closes_to_candles(closes: list[float], minutes: int, wick: float = 0.25):
    rows: list[tuple[float, float, float, float]] = []
    prev = closes[0]
    for i, close in enumerate(closes):
        open_ = prev
        upper = wick
        lower = wick
        if 0 < i < len(closes) - 1:
            if close >= closes[i - 1] and close >= closes[i + 1]:
                upper = wick + 0.8
            if close <= closes[i - 1] and close <= closes[i + 1]:
                lower = wick + 0.8
        high = max(open_, close) + upper
        low = min(open_, close) - lower
        rows.append((open_, high, low, close))
        prev = close
    return candles_from_ohlc(rows, minutes=minutes)


__all__ = [
    "Candle",
    "bullish_structure_candles",
    "closes_to_candles",
    "m15_buy_setup",
    "structure_from_swings",
]
