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
    for _ in range(up):
        nxt = price + step_up
        high = nxt + 0.05
        low = min(price, nxt) - 0.05
        rows.append((price, high, low, nxt))
        price = nxt
    step_down = (end - peak) / down
    for _ in range(down):
        nxt = price + step_down
        high = max(price, nxt) + 0.05
        low = nxt - 0.05
        rows.append((price, high, low, nxt))
        price = nxt
    return rows


def mirror(df: pd.DataFrame, mid: float = 4000.0) -> pd.DataFrame:
    out = df.copy()
    out["open"] = mid - df["open"]
    out["close"] = mid - df["close"]
    out["high"] = mid - df["low"]
    out["low"] = mid - df["high"]
    return out


def smc_buy_setup(start: float = 2000.0, min_bars: int = 0) -> pd.DataFrame:
    """Bullish SMC: structure, sell-side liquidity sweep, FVG, then a fresh tap."""
    rows: list[tuple[float, float, float, float]] = []
    price = start
    pad = max(12, min_bars) if min_bars else 12
    for i in range(pad):
        nxt = price + 0.35
        rows.append((price, nxt + 0.12, price - 0.12, nxt))
        price = nxt

    for cycle in range(3):
        peak = price + 14 + cycle * 2
        trough = peak - 5
        rows.extend(mountain(price, peak, trough, up=7, down=4))
        price = trough

    trough = price - 14
    rows.extend(mountain(price, price + 3, trough, up=3, down=8))
    price = trough
    swing_low = min(r[2] for r in rows[-12:])

    peak = price + 11
    rows.extend(mountain(price, peak, price + 4, up=6, down=3))
    price = price + 4

    rows.append((price, price + 0.4, swing_low - 1.5, swing_low + 1.0))
    price = swing_low + 1.0

    ob_open = price
    ob_high = ob_open + 0.25
    ob_close = ob_open - 0.8
    rows.append((ob_open, ob_high, ob_close - 0.2, ob_close))

    last_high = max(r[1] for r in rows[-24:])
    mid_close = last_high + 8
    rows.append((ob_close, mid_close + 0.4, ob_close - 0.05, mid_close))

    fvg_high = ob_high + 2.5
    displacement_close = last_high + 16
    rows.append((mid_close, displacement_close + 0.5, fvg_high, displacement_close))

    rows.append((displacement_close, displacement_close + 0.8, displacement_close - 0.15, displacement_close + 0.4))

    tap = (ob_high + fvg_high) / 2
    rows.append((displacement_close + 0.4, displacement_close + 0.5, tap - 0.12, tap))
    return ohlc(rows)
