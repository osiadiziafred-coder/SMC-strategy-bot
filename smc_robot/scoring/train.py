"""Offline ML training. Never retrain from a live trade stream."""

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
        n_estimators=120,
        max_depth=3,
        learning_rate=0.06,
        random_state=42,
    )
    model.fit(features, labels)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": FEATURE_NAMES,
            "trained_offline": True,
        },
        target,
    )
    return model


def load_sklearn_model(path: str | Path):
    import joblib

    payload = joblib.load(path)
    if isinstance(payload, dict) and "model" in payload:
        return payload["model"]
    return payload


def chronological_split(
    features: np.ndarray,
    labels: np.ndarray,
    train_frac: float = 0.60,
    valid_frac: float = 0.20,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(labels)
    train_end = max(2, int(n * train_frac))
    valid_end = max(train_end + 1, int(n * (train_frac + valid_frac)))
    return (
        features[:train_end],
        labels[:train_end],
        features[train_end:valid_end],
        labels[train_end:valid_end],
        features[valid_end:],
        labels[valid_end:],
    )


def pick_threshold(model, features: np.ndarray, labels: np.ndarray, grid=None) -> float:
    if features.size == 0 or len(np.unique(labels)) < 2:
        return 0.60
    grid = grid or [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]
    proba = model.predict_proba(features)[:, 1]
    best_t, best_score = 0.60, -1.0
    for threshold in grid:
        chosen = proba >= threshold
        if chosen.sum() < 3:
            continue
        wins = labels[chosen].sum()
        win_rate = wins / chosen.sum()
        coverage = chosen.mean()
        score = win_rate * 0.7 + coverage * 0.3
        if score > best_score:
            best_score = score
            best_t = threshold
    return float(best_t)
