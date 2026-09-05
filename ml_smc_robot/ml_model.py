"""Machine-learning model wrapper for the SMC brain.

This is a *real* supervised classifier - never a hard-coded score. It prefers
gradient-boosted trees (LightGBM, then XGBoost) and falls back to a scikit-learn
:class:`RandomForestClassifier` when neither is available, exactly as the spec
allows. All three expose feature importances for explainability.

The wrapper persists the fitted estimator together with its feature list and
training metadata so the live brain can load and use an identical model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def _make_estimator(backends: tuple[str, ...]):
    """Return (estimator, backend_name) for the first importable backend."""

    for backend in backends:
        if backend == "lightgbm":
            try:
                from lightgbm import LGBMClassifier

                return (
                    LGBMClassifier(
                        n_estimators=400,
                        learning_rate=0.05,
                        num_leaves=31,
                        max_depth=-1,
                        subsample=0.8,
                        subsample_freq=1,
                        colsample_bytree=0.8,
                        reg_lambda=1.0,
                        random_state=42,
                        n_jobs=-1,
                        verbosity=-1,
                    ),
                    "lightgbm",
                )
            except Exception:
                continue
        if backend == "xgboost":
            try:
                from xgboost import XGBClassifier

                return (
                    XGBClassifier(
                        n_estimators=400,
                        learning_rate=0.05,
                        max_depth=5,
                        subsample=0.8,
                        colsample_bytree=0.8,
                        reg_lambda=1.0,
                        random_state=42,
                        n_jobs=-1,
                        eval_metric="logloss",
                        tree_method="hist",
                    ),
                    "xgboost",
                )
            except Exception:
                continue
        if backend == "random_forest":
            from sklearn.ensemble import RandomForestClassifier

            return (
                RandomForestClassifier(
                    n_estimators=400,
                    max_depth=None,
                    min_samples_leaf=20,
                    max_features="sqrt",
                    random_state=42,
                    n_jobs=-1,
                    class_weight="balanced_subsample",
                ),
                "random_forest",
            )
    raise RuntimeError("No supported ML backend available")


@dataclass
class MLModel:
    feature_names: list[str]
    backends: tuple[str, ...] = ("lightgbm", "xgboost", "random_forest")
    estimator: object = None
    backend: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.estimator is None:
            self.estimator, self.backend = _make_estimator(tuple(self.backends))

    # -- training / inference ---------------------------------------------
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "MLModel":
        self.estimator.fit(X[self.feature_names].to_numpy(), np.asarray(y))
        return self

    def predict_success_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Probability of the positive class (setup success)."""

        proba = self.estimator.predict_proba(X[self.feature_names].to_numpy())
        classes = list(getattr(self.estimator, "classes_", [0, 1]))
        pos_idx = classes.index(1) if 1 in classes else proba.shape[1] - 1
        return proba[:, pos_idx]

    # -- explainability ----------------------------------------------------
    def feature_importance(self) -> dict[str, float]:
        importances = getattr(self.estimator, "feature_importances_", None)
        if importances is None:
            return {}
        total = float(np.sum(importances)) or 1.0
        return {
            name: float(imp) / total
            for name, imp in sorted(
                zip(self.feature_names, importances), key=lambda kv: kv[1], reverse=True
            )
        }

    def explain(self, X_row: pd.DataFrame, top_k: int = 6) -> list[tuple[str, float, float]]:
        """Return the top contributing features for a single prediction as
        (feature, value, contribution). Uses LightGBM SHAP contributions when
        available, otherwise importance-weighted feature values."""

        row = X_row[self.feature_names].iloc[0]
        contributions: dict[str, float] = {}

        if self.backend == "lightgbm":
            try:
                contrib = self.estimator.predict(
                    X_row[self.feature_names].to_numpy(), pred_contrib=True
                )[0]
                # Last column is the base value/bias.
                for name, c in zip(self.feature_names, contrib[:-1]):
                    contributions[name] = float(c)
            except Exception:
                contributions = {}

        if not contributions:
            imp = self.feature_importance()
            contributions = {name: imp.get(name, 0.0) * float(row[name]) for name in self.feature_names}

        ranked = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_k]
        return [(name, float(row[name]), float(contrib)) for name, contrib in ranked]

    # -- persistence -------------------------------------------------------
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "estimator": self.estimator,
            "feature_names": self.feature_names,
            "backend": self.backend,
            "metadata": {**self.metadata, "saved_at": time.time()},
        }
        joblib.dump(payload, path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "MLModel":
        payload = joblib.load(Path(path))
        return cls(
            feature_names=payload["feature_names"],
            estimator=payload["estimator"],
            backend=payload.get("backend", ""),
            metadata=payload.get("metadata", {}),
        )
