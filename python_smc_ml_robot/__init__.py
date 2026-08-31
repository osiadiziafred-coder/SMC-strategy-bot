"""Python ML + SMC trading brain. MQL5 only executes command.json."""

from python_smc_ml_robot._paths import ROOT  # noqa: F401
from python_smc_ml_robot.config import MIN_ML_SCORE, Settings, load_config

__all__ = ["MIN_ML_SCORE", "Settings", "load_config"]
__version__ = "3.1.0"
