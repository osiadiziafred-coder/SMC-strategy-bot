from __future__ import annotations

import numpy as np

from smc_robot.models import Candle


def true_ranges(candles: list[Candle]) -> np.ndarray:
    if not candles:
        return np.array([])
    highs = np.array([c.high for c in candles], dtype=float)
    lows = np.array([c.low for c in candles], dtype=float)
    closes = np.array([c.close for c in candles], dtype=float)
    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    return np.maximum(highs - lows, np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close)))


def atr(candles: list[Candle], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    tr = true_ranges(candles)
    window = tr[-period:] if len(tr) >= period else tr
    return float(np.mean(window))


def atr_series(candles: list[Candle], period: int = 14) -> np.ndarray:
    tr = true_ranges(candles)
    if tr.size == 0:
        return tr
    out = np.full(len(tr), np.nan, dtype=float)
    if len(tr) < period:
        out[:] = float(np.mean(tr))
        return out
    cumsum = np.cumsum(tr)
    out[period - 1] = cumsum[period - 1] / period
    for i in range(period, len(tr)):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    out[: period - 1] = out[period - 1]
    return out


def efficiency_ratio(candles: list[Candle], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    window = candles[-period:]
    net = abs(window[-1].close - window[0].open)
    path = sum(c.range for c in window)
    if path <= 0:
        return 0.0
    return float(net / path)


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return float(np.mean(values))
    k = 2.0 / (period + 1.0)
    current = float(np.mean(values[:period]))
    for value in values[period:]:
        current = value * k + current * (1.0 - k)
    return current
