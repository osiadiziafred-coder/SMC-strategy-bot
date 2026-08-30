"""Smart Money Concepts (SMC) forex strategy backtesting bot.

This package implements a small, self-contained toolkit for experimenting with
Smart Money Concepts trading ideas on foreign-exchange candle data:

* :mod:`smc_bot.data` - load OHLC data from CSV or generate reproducible
  synthetic candles so the bot runs fully offline.
* :mod:`smc_bot.indicators` - detect swing points, market-structure shifts
  (BOS / CHoCH), order blocks and fair value gaps.
* :mod:`smc_bot.strategy` - turn the SMC structure into entry/exit signals.
* :mod:`smc_bot.backtester` - a simple event-driven backtest engine.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
