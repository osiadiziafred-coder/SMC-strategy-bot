"""ML trend/pullback scalper — Python brain, MQL5 execution.

Completely separate from any Smart Money Concepts (SMC) stack. No order
blocks, BOS, MSS, CHoCH, FVG or liquidity-sweep logic lives in this package.

Instruments: Volatility 50 (1s) Index, Volatility 75 Index, XAUUSD.
Each instrument has its own configuration and trained model.
"""

from .config import Config, INSTRUMENTS, resolve_symbol

__all__ = ["Config", "INSTRUMENTS", "resolve_symbol"]
__version__ = "1.0.0"
