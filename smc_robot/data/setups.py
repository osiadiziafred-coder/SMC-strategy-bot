from __future__ import annotations

import numpy as np

from smc_robot.data.synthetic import candles_from_ohlc
from smc_robot.models import Candle


def structure_from_swings(
    points: list[tuple[int, str, float]],
    n_bars: int,
    minutes: int,
    wick: float = 0.25,
    extra_n: int = 5,
) -> list[Candle]:
    xs = np.array([i for i, _, _ in points], dtype=float)
    ys = np.array([price for _, _, price in points], dtype=float)
    closes = [float(np.interp(i, xs, ys)) for i in range(n_bars)]
    rows: list[tuple[float, float, float, float]] = []
    kind_at = {index: (kind, price) for index, kind, price in points}
    for i, close in enumerate(closes):
        open_ = closes[i - 1] if i else close
        high = max(open_, close) + wick
        low = min(open_, close) - wick
        if i in kind_at:
            kind, price = kind_at[i]
            if kind == "H":
                high = price
                close = price - wick
                open_ = close - wick
                low = min(open_, close) - wick
            else:
                low = price
                close = price + wick
                open_ = close + wick
                high = max(open_, close) + wick
        rows.append((open_, high, low, close))

    for index, kind, price in points:
        start = max(0, index - extra_n)
        end = min(n_bars, index + extra_n + 1)
        for j in range(start, end):
            if j == index:
                continue
            o, h, l, c = rows[j]
            if kind == "H" and h >= price:
                h = price - 0.15
                c = min(c, h - 0.05)
                o = min(o, h - 0.05)
                l = min(l, o, c) - wick
            if kind == "L" and l <= price:
                l = price + 0.15
                c = max(c, l + 0.05)
                o = max(o, l + 0.05)
                h = max(h, o, c) + wick
            rows[j] = (o, h, l, c)
    return candles_from_ohlc(rows, minutes=minutes)


def bullish_structure_candles(n: int = 96, minutes: int = 60) -> list[Candle]:
    return structure_from_swings(
        [
            (8, "L", 2000.0),
            (22, "H", 2024.0),
            (36, "L", 2008.0),
            (50, "H", 2036.0),
            (64, "L", 2016.0),
            (78, "H", 2048.0),
        ],
        n_bars=n,
        minutes=minutes,
        extra_n=5,
    )


def _set_bar(candle: Candle, open_: float, high: float, low: float, close: float) -> Candle:
    assert high >= max(open_, close) and low <= min(open_, close)
    return candle.model_copy(update={"open": open_, "high": high, "low": low, "close": close})


def m15_buy_setup() -> list[Candle]:
    candles = [c.model_copy() for c in bullish_structure_candles(n=110, minutes=15)]
    for j in range(79, 110):
        candles[j] = _set_bar(candles[j], 2042.0, 2043.4, 2041.2, 2042.2)

    high_i = 93
    s = 100
    sweep = 103
    ob = 104
    impulse_mid = 105
    impulse_right = 106
    pull = 107
    tap = 109
    internal_high = 2043.0
    swing_low = 2036.2

    candles[high_i] = _set_bar(candles[high_i], 2041.2, internal_high, 2040.8, 2042.4)
    for j in (high_i - 2, high_i - 1, high_i + 1, high_i + 2):
        candles[j] = _set_bar(candles[j], 2041.0, 2042.4, 2040.2, 2041.4)
    candles[s] = _set_bar(candles[s], 2037.6, 2038.4, swing_low, 2036.9)
    for j in (s - 2, s - 1, s + 1, s + 2):
        candles[j] = _set_bar(candles[j], 2038.0, 2039.2, 2037.5, 2038.3)
    candles[sweep] = _set_bar(candles[sweep], 2037.4, 2038.8, swing_low - 0.9, 2037.8)
    candles[ob] = _set_bar(candles[ob], 2038.1, 2038.5, 2036.4, 2036.7)
    candles[impulse_mid] = _set_bar(candles[impulse_mid], 2036.8, 2041.8, 2036.6, 2041.4)
    candles[impulse_right] = _set_bar(candles[impulse_right], 2041.5, 2045.2, 2041.2, 2044.8)
    candles[pull] = _set_bar(candles[pull], 2044.6, 2045.0, 2041.0, 2041.6)
    candles[108] = _set_bar(candles[108], 2041.5, 2042.4, 2040.4, 2041.0)
    candles[tap] = _set_bar(candles[tap], 2041.2, 2042.6, 2037.2, 2039.8)
    return candles
