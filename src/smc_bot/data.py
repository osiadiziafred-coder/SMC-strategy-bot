"""Data access helpers for the SMC bot.

The bot is designed to run fully offline for backtesting, so in addition to
loading candles from a CSV file it can generate reproducible synthetic OHLC
data with a configurable trend and volatility. This avoids any dependency on a
broker API or network access (and therefore any secrets) for the demo flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("open", "high", "low", "close")


@dataclass(frozen=True)
class SyntheticConfig:
    """Parameters controlling synthetic candle generation."""

    n: int = 1500
    start_price: float = 1.1000
    drift: float = 0.00003
    volatility: float = 0.0009
    seed: int = 7
    trend_cycles: int = 3
    timeframe_minutes: int = 15


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load OHLC candles from a CSV file.

    The file must contain ``open``, ``high``, ``low`` and ``close`` columns
    (case-insensitive). A ``time``/``timestamp``/``date`` column, if present, is
    parsed and used as the index.
    """

    path = Path(path)
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    time_col = next((c for c in ("time", "timestamp", "date", "datetime") if c in df.columns), None)
    if time_col is not None:
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.set_index(time_col).sort_index()

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV {path} is missing required columns: {missing}")

    return validate_ohlc(df[list(REQUIRED_COLUMNS)].astype(float))


def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Validate basic OHLC invariants, raising ``ValueError`` on violation."""

    if df.empty:
        raise ValueError("OHLC frame is empty")

    highs_ok = (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    lows_ok = (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    if not highs_ok:
        raise ValueError("Found candles where high is below open/close")
    if not lows_ok:
        raise ValueError("Found candles where low is above open/close")

    return df


def generate_synthetic(config: SyntheticConfig | None = None) -> pd.DataFrame:
    """Generate reproducible synthetic OHLC candles.

    The price path is a geometric random walk with a slowly oscillating drift so
    that the series contains alternating bullish/bearish trends. This produces
    realistic-looking market structure (swings, breaks of structure, order
    blocks and fair value gaps) for the strategy to trade against.
    """

    config = config or SyntheticConfig()
    rng = np.random.default_rng(config.seed)

    n = config.n
    # Oscillating drift creates multiple up/down trends across the series.
    phase = np.linspace(0.0, config.trend_cycles * 2.0 * np.pi, n)
    drift = config.drift * np.sin(phase)

    shocks = rng.normal(loc=0.0, scale=config.volatility, size=n)
    log_returns = drift + shocks
    close = config.start_price * np.exp(np.cumsum(log_returns))

    # Build OHLC around each close using intrabar noise.
    open_ = np.empty(n)
    open_[0] = config.start_price
    open_[1:] = close[:-1]

    body_high = np.maximum(open_, close)
    body_low = np.minimum(open_, close)
    wick = np.abs(rng.normal(loc=0.0, scale=config.volatility * 0.6, size=n)) * close
    high = body_high + wick
    low = body_low - np.abs(rng.normal(loc=0.0, scale=config.volatility * 0.6, size=n)) * close

    index = pd.date_range(
        start="2024-01-01",
        periods=n,
        freq=f"{config.timeframe_minutes}min",
        name="time",
    )
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=index,
    )
    return validate_ohlc(df.round(5))
