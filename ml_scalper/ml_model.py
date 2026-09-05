"""Dual-head machine learning wrapper for the scalper.

The packaged model learns three things, not the next candle:

1. **Direction** — a 3-class classifier: BUY / SELL / NO_TRADE
2. **Probability / confidence** — class probabilities from that model
3. **Expected outcome** — P(TP is hit before SL) at the configured 1:2 RR

LightGBM is preferred, then XGBoost, then scikit-learn RandomForest.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .features import CLASS_BUY, CLASS_NAMES, CLASS_NONE, CLASS_SELL


def _make_estimator(backends: tuple[str, ...], task: str, n_estimators: int = 300):
    multiclass = task == "multiclass"
    n_estimators = max(40, int(n_estimators))
    for backend in backends:
        if backend == "lightgbm":
            try:
                from lightgbm import LGBMClassifier

                kwargs = dict(
                    n_estimators=n_estimators,
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
                    class_weight="balanced",
                )
                if multiclass:
                    kwargs["objective"] = "multiclass"
                return LGBMClassifier(**kwargs), "lightgbm"
            except Exception:
                continue
        if backend == "xgboost":
            try:
                from xgboost import XGBClassifier

                kwargs = dict(
                    n_estimators=n_estimators,
                    learning_rate=0.05,
                    max_depth=5,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_lambda=1.0,
                    random_state=42,
                    n_jobs=-1,
                    tree_method="hist",
                )
                if multiclass:
                    kwargs["objective"] = "multi:softprob"
                    kwargs["eval_metric"] = "mlogloss"
                else:
                    kwargs["eval_metric"] = "logloss"
                return XGBClassifier(**kwargs), "xgboost"
            except Exception:
                continue
        if backend == "random_forest":
            from sklearn.ensemble import RandomForestClassifier

            return (
                RandomForestClassifier(
                    n_estimators=n_estimators,
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
class Head:
    feature_names: list[str]
    task: str
    backends: tuple[str, ...] = ("lightgbm", "xgboost", "random_forest")
    estimator: object = None
    backend: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.estimator is None:
            n_est = int(self.metadata.get("n_estimators", 300))
            self.estimator, self.backend = _make_estimator(tuple(self.backends), self.task, n_est)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "Head":
        self.estimator.fit(X[self.feature_names].to_numpy(), np.asarray(y))
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.estimator.predict_proba(X[self.feature_names].to_numpy())

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
        row = X_row[self.feature_names].iloc[0]
        contributions: dict[str, float] = {}
        if self.backend == "lightgbm":
            try:
                contrib = self.estimator.predict(
                    X_row[self.feature_names].to_numpy(), pred_contrib=True
                )
                raw = np.asarray(contrib)
                # Binary: (n, n_features+1). Multiclass: (n, n_features+1, n_classes)
                if raw.ndim == 3:
                    raw = raw[0, :, 1] if raw.shape[-1] > 1 else raw[0, :, 0]
                else:
                    raw = raw[0]
                for name, c in zip(self.feature_names, raw[:-1]):
                    contributions[name] = float(c)
            except Exception:
                contributions = {}
        if not contributions:
            imp = self.feature_importance()
            contributions = {name: imp.get(name, 0.0) * float(row[name]) for name in self.feature_names}
        ranked = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_k]
        return [(name, float(row[name]), float(contrib)) for name, contrib in ranked]


@dataclass
class TradeScore:
    p_buy: float
    p_sell: float
    p_none: float
    p_tp_buy: float
    p_tp_sell: float

    @property
    def direction(self) -> str:
        trio = {"BUY": self.p_buy, "SELL": self.p_sell, "NO_TRADE": self.p_none}
        return max(trio, key=trio.get)

    def as_dict(self) -> dict:
        return {
            "p_buy": self.p_buy,
            "p_sell": self.p_sell,
            "p_none": self.p_none,
            "p_tp_buy": self.p_tp_buy,
            "p_tp_sell": self.p_tp_sell,
        }


@dataclass
class ScalperModels:
    direction: Head
    outcome: Head
    metadata: dict = field(default_factory=dict)

    def predict(self, X_base: pd.DataFrame, X_buy: pd.DataFrame, X_sell: pd.DataFrame) -> TradeScore:
        dir_p = self.direction.predict_proba(X_base)[0]
        classes = list(getattr(self.direction.estimator, "classes_", [0, 1, 2]))
        mapped = {int(c): float(p) for c, p in zip(classes, dir_p)}
        p_none = mapped.get(CLASS_NONE, 0.0)
        p_buy = mapped.get(CLASS_BUY, 0.0)
        p_sell = mapped.get(CLASS_SELL, 0.0)
        # If a class was missing in training, renormalise.
        total = p_none + p_buy + p_sell
        if total <= 0:
            p_none, p_buy, p_sell = 1.0, 0.0, 0.0
        else:
            p_none, p_buy, p_sell = p_none / total, p_buy / total, p_sell / total

        def _pos(head: Head, X: pd.DataFrame) -> float:
            proba = head.predict_proba(X)[0]
            classes_b = list(getattr(head.estimator, "classes_", [0, 1]))
            if 1 in classes_b:
                return float(proba[classes_b.index(1)])
            return float(proba[-1])

        return TradeScore(
            p_buy=p_buy,
            p_sell=p_sell,
            p_none=p_none,
            p_tp_buy=_pos(self.outcome, X_buy),
            p_tp_sell=_pos(self.outcome, X_sell),
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "direction": {
                "estimator": self.direction.estimator,
                "feature_names": self.direction.feature_names,
                "backend": self.direction.backend,
                "task": self.direction.task,
            },
            "outcome": {
                "estimator": self.outcome.estimator,
                "feature_names": self.outcome.feature_names,
                "backend": self.outcome.backend,
                "task": self.outcome.task,
            },
            "metadata": {**self.metadata, "saved_at": time.time()},
        }
        joblib.dump(payload, path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "ScalperModels":
        payload = joblib.load(Path(path))
        d = payload["direction"]
        o = payload["outcome"]
        return cls(
            direction=Head(
                feature_names=d["feature_names"],
                task=d.get("task", "multiclass"),
                estimator=d["estimator"],
                backend=d.get("backend", ""),
            ),
            outcome=Head(
                feature_names=o["feature_names"],
                task=o.get("task", "binary"),
                estimator=o["estimator"],
                backend=o.get("backend", ""),
            ),
            metadata=payload.get("metadata", {}),
        )


def new_models(
    dir_features: list[str],
    out_features: list[str],
    backends: tuple[str, ...],
    n_estimators: int = 300,
) -> ScalperModels:
    return ScalperModels(
        direction=Head(
            feature_names=dir_features,
            task="multiclass",
            backends=backends,
            metadata={"n_estimators": n_estimators},
        ),
        outcome=Head(
            feature_names=out_features,
            task="binary",
            backends=backends,
            metadata={"n_estimators": n_estimators},
        ),
    )


__all__ = [
    "CLASS_BUY",
    "CLASS_NAMES",
    "CLASS_NONE",
    "CLASS_SELL",
    "Head",
    "ScalperModels",
    "TradeScore",
    "new_models",
]
