from __future__ import annotations

import pandas as pd


def ohlc(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    data = []
    for i, (open_, high, low, close) in enumerate(rows):
        data.append(
            {
                "time": i,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1.0,
            }
        )
    return pd.DataFrame(data)


def mountain(start: float, peak: float, end: float, up: int = 8, down: int = 8) -> list[tuple[float, float, float, float]]:
    """Unique peak/trough candles so fractal swings are unambiguous."""
    rows: list[tuple[float, float, float, float]] = []
    price = start
    step_up = (peak - start) / up
    for i in range(up):
        nxt = price + step_up
        high = nxt + 0.05
        low = min(price, nxt) - 0.05
        rows.append((price, high, low, nxt))
        price = nxt
    step_down = (end - peak) / down
    for i in range(down):
        nxt = price + step_down
        high = max(price, nxt) + 0.05
        low = nxt - 0.05
        rows.append((price, high, low, nxt))
        price = nxt
    return rows


def impulse_up(start: float = 2000.0, cycles: int = 3, min_bars: int = 0) -> pd.DataFrame:
    """Bullish structure: higher highs, higher lows, then a bullish FVG tap."""
    rows: list[tuple[float, float, float, float]] = []
    price = start
    cycle = 0
    while cycle < cycles or len(rows) < min_bars:
        peak = price + 12 + (cycle % 5) * 2
        trough = peak - 4
        rows.extend(mountain(price, peak, trough, up=7, down=4))
        price = trough
        cycle += 1
    # Final displacement that breaks the last high, leaves a FVG, then taps it.
    last_high = max(r[1] for r in rows[-12:])
    displacement_close = last_high + 8
    rows.append((price, price + 0.2, price - 0.4, price - 0.2))  # last down candle / OB
    rows.append((price - 0.2, last_high + 0.1, price - 0.3, last_high + 0.05))
    rows.append((last_high + 0.05, displacement_close + 0.3, last_high + 0.2, displacement_close))
    fvg_low = last_high + 0.2
    fvg_high = last_high + 3.0
    rows.append((displacement_close, displacement_close + 0.5, fvg_high, displacement_close + 0.2))
    tap = (fvg_high + fvg_low) / 2
    rows.append((displacement_close + 0.2, displacement_close + 0.4, tap - 0.1, tap))
    return ohlc(rows)
