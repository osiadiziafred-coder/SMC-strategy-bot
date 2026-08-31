"""Verify XAUUSDm exists, then load H1 → M30 → M15."""

from python_smc_ml_robot._paths import ROOT  # noqa: F401

from smc_robot.market_data import (
    REQUIRED_SYMBOL,
    inspect_market,
    load_mtf,
    symbol_snapshot,
    verify_quote,
    verify_symbol,
)

__all__ = [
    "REQUIRED_SYMBOL",
    "inspect_market",
    "load_mtf",
    "symbol_snapshot",
    "verify_quote",
    "verify_symbol",
]
