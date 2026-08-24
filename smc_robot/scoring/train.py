"""Train a GradientBoosting setup classifier from labelled feature rows."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from smc_robot.scoring import FEATURE_NAMES


def train_model(features: np.ndarray, labels: np.ndarray, path: str | Path):
    from sklearn.ensemble import GradientBoostingClassifier
    import joblib

    if features.size == 0 or len(np.unique(labels)) < 2:
        raise ValueError("Need both winning and losing labelled setups to train")
    model = GradientBoostingClassifier(
        n_estimators=80,
        max_depth=3,
        learning_rate=0.08,
        random_state=42,
    )
    model.fit(features, labels)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURE_NAMES}, target)
    return model


def load_sklearn_model(path: str | Path):
    import joblib

    payload = joblib.load(path)
    if isinstance(payload, dict) and "model" in payload:
        return payload["model"]
    return payload
