"""Offline trainer and live scorer. Chronological split only — no shuffle."""

from python_smc_ml_robot._paths import ROOT  # noqa: F401

from smc_robot.scoring import SetupScorer
from smc_robot.scoring.pipeline import train_from_history
from smc_robot.scoring.train import chronological_split, train_model

__all__ = ["SetupScorer", "chronological_split", "train_from_history", "train_model"]
