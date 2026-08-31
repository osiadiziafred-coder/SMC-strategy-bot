"""User-facing settings. MIN_ML_SCORE is the default ML gate."""

from python_smc_ml_robot._paths import ROOT  # noqa: F401

from smc_robot.config import Settings, load_config

MIN_ML_SCORE = 0.70
ALLOWED_ML_THRESHOLDS = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85)

__all__ = ["ALLOWED_ML_THRESHOLDS", "MIN_ML_SCORE", "Settings", "load_config"]
