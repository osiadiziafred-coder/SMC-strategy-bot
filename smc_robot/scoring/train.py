"""Offline ML training. Never retrain from a live trade stream."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from smc_robot.scoring import FEATURE_NAMES


def _candidates():
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    return {
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.06, random_state=42
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=160, max_depth=5, min_samples_leaf=4, random_state=42
        ),
        "logistic": LogisticRegression(max_iter=400, random_state=42),
    }


def _valid_score(model, features: np.ndarray, labels: np.ndarray) -> float:
    if len(features) == 0 or len(np.unique(labels)) < 2:
        return float((model.predict(features) == labels).mean()) if len(labels) else 0.0
    proba = model.predict_proba(features)[:, 1]
    order = np.argsort(proba)
    # Mann–Whitney style rank AUC without extra sklearn metrics dependency edge cases
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(len(order))
    pos = labels == 1
    n_pos = pos.sum()
    n_neg = (~pos).sum()
    if n_pos == 0 or n_neg == 0:
        return float((model.predict(features) == labels).mean())
    return float((ranks[pos].sum() - n_pos * (n_pos - 1) / 2.0) / (n_pos * n_neg))


def select_model(x_train, y_train, x_valid, y_valid):
    best_name = "gradient_boosting"
    best_model = None
    best_score = -1.0
    scores = {}
    for name, model in _candidates().items():
        model.fit(x_train, y_train)
        score = _valid_score(model, x_valid, y_valid) if len(y_valid) else 0.0
        scores[name] = score
        if score > best_score:
            best_score = score
            best_name = name
            best_model = model
    if best_model is None:
        best_model = _candidates()["gradient_boosting"]
        best_model.fit(x_train, y_train)
    return best_name, best_model, scores


def train_model(features: np.ndarray, labels: np.ndarray, path: str | Path):
    import joblib

    if features.size == 0 or len(np.unique(labels)) < 2:
        raise ValueError("Need both winning and losing labelled setups to train")
    x_tr, y_tr, x_va, y_va, _, _ = chronological_split(features, labels)
    if len(y_va) < 4:
        x_tr, y_tr, x_va, y_va = features, labels, features, labels
    name, model, scores = select_model(x_tr, y_tr, x_va, y_va)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": FEATURE_NAMES,
            "trained_offline": True,
            "selected_model": name,
            "validation_scores": scores,
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
