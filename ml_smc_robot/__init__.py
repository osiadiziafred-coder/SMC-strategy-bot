"""ML + SMC trading robot (default symbol: Volatility 75 Index).

Symbol is configurable (see ``config.SYMBOL_PRESETS``); Volatility 75 Index and
XAUUSDm ship as presets.

A two-part system:

* **Python ML/SMC brain** - pulls multi-timeframe data from MetaTrader 5 (or an
  offline provider for training/testing), detects Smart Money Concepts (SMC)
  structure, engineers features, runs a *real* trained machine-learning model to
  score BUY/SELL setups, applies risk rules, and emits a trade command.
* **MQL5 safety bridge EA** (see ``mql5/SMC_Safety_Bridge.mq5``) - the only
  component that touches the broker. It executes commands written by Python and
  independently manages one-position protection, breakeven and trailing stops.

The Python side never talks to the broker directly and the EA never invents
BUY/SELL signals on its own.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
