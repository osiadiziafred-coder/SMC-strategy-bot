"""Balance-step lots, structure SL, 1:2 RR, broker lot/stop normalization."""

from python_smc_ml_robot._paths import ROOT  # noqa: F401

from smc_robot.risk.sizing import (
    SymbolSpec,
    lots_from_balance,
    lots_from_risk_percent,
    normalize_lots,
)
from smc_robot.risk.trade_plan import build_trade_plan

__all__ = [
    "SymbolSpec",
    "build_trade_plan",
    "lots_from_balance",
    "lots_from_risk_percent",
    "normalize_lots",
]
