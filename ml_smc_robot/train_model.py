"""Historical training pipeline for the SMC ML model.

Steps (matching the spec):

1. Read historical data from MT5 (or an offline provider for testing).
2. Generate SMC features.
3. Create triple-barrier training labels (BUY and SELL).
4. Train a real ML model (LightGBM / XGBoost / RandomForest).
5. Validate with **time-ordered** splits (no shuffling) - a chronological
   holdout plus ``TimeSeriesSplit`` cross-validation - to avoid look-ahead bias
   and leakage.
6. Save the trained model (+ feature list, metrics, importances) to disk.

Run offline (no terminal required)::

    python -m ml_smc_robot.train_model --source synthetic --bars 15000

Run against a live MT5 terminal on Windows::

    python -m ml_smc_robot.train_model --source mt5 --bars 30000
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from .config import Config
from .features import FEATURE_COLUMNS, build_training_dataset
from .ml_model import MLModel
from .mt5_connector import make_connector


def _safe_auc(y_true, y_score) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def load_history(cfg: Config, connector) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    connector.connect()
    h1 = connector.get_rates(cfg.bias_timeframe, cfg.train_bars)
    m30 = connector.get_rates(cfg.confirm_timeframe, cfg.train_bars)
    m15 = connector.get_rates(cfg.entry_timeframe, cfg.train_bars)
    return h1, m30, m15


def time_ordered_split(X: pd.DataFrame, y: pd.Series, test_frac: float) -> tuple:
    n = len(X)
    split = int(n * (1.0 - test_frac))
    return (
        X.iloc[:split],
        X.iloc[split:],
        y.iloc[:split],
        y.iloc[split:],
    )


def cross_validate(X: pd.DataFrame, y: pd.Series, cfg: Config, n_splits: int) -> dict:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    aucs, accs = [], []
    for train_idx, val_idx in tscv.split(X):
        if len(np.unique(y.iloc[train_idx])) < 2:
            continue
        model = MLModel(feature_names=FEATURE_COLUMNS, backends=cfg.model_backends)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        proba = model.predict_success_proba(X.iloc[val_idx])
        aucs.append(_safe_auc(y.iloc[val_idx], proba))
        accs.append(accuracy_score(y.iloc[val_idx], (proba >= 0.5).astype(int)))
    return {
        "cv_auc_mean": float(np.nanmean(aucs)) if aucs else float("nan"),
        "cv_auc_std": float(np.nanstd(aucs)) if aucs else float("nan"),
        "cv_accuracy_mean": float(np.mean(accs)) if accs else float("nan"),
        "cv_folds": len(aucs),
    }


def train(cfg: Config, test_frac: float = 0.2, n_splits: int = 4, seed: int = 7) -> dict:
    connector = make_connector(cfg, seed=seed) if cfg.data_source == "synthetic" else make_connector(cfg)
    h1, m30, m15 = load_history(cfg, connector)
    print(f"Loaded bars -> H1={len(h1)} M30={len(m30)} M15={len(m15)}")

    X, y, ts = build_training_dataset(h1, m30, m15, cfg)
    print(f"Built dataset -> samples={len(X)} features={X.shape[1]} positive_rate={y.mean():.3f}")

    if len(X) < 500 or y.nunique() < 2:
        raise RuntimeError("Insufficient/one-class training data; increase --bars.")

    # 1) Chronological cross-validation (no shuffle).
    cv = cross_validate(X, y, cfg, n_splits)

    # 2) Chronological holdout evaluation.
    X_tr, X_te, y_tr, y_te = time_ordered_split(X, y, test_frac)
    model = MLModel(feature_names=FEATURE_COLUMNS, backends=cfg.model_backends)
    model.fit(X_tr, y_tr)
    proba_te = model.predict_success_proba(X_te)
    pred_te = (proba_te >= 0.5).astype(int)
    holdout = {
        "holdout_auc": _safe_auc(y_te, proba_te),
        "holdout_accuracy": float(accuracy_score(y_te, pred_te)),
        "holdout_precision": float(precision_score(y_te, pred_te, zero_division=0)),
        "holdout_recall": float(recall_score(y_te, pred_te, zero_division=0)),
        "holdout_samples": int(len(y_te)),
        "holdout_positive_rate": float(y_te.mean()),
    }

    # 3) Refit on ALL chronological data for the deployed model.
    final = MLModel(feature_names=FEATURE_COLUMNS, backends=cfg.model_backends)
    final.fit(X, y)
    importances = final.feature_importance()

    metadata = {
        "symbol": cfg.symbol,
        "backend": final.backend,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_samples": int(len(X)),
        "n_features": int(X.shape[1]),
        "positive_rate": float(y.mean()),
        "data_source": cfg.data_source,
        "feature_importance": importances,
        "metrics": {**cv, **holdout},
        "label": {
            "horizon": cfg.label_horizon,
            "atr_sl_mult": cfg.atr_sl_mult,
            "risk_reward": cfg.risk_reward,
        },
    }
    final.metadata = metadata

    path = final.save(cfg.model_path)
    with open(str(path) + ".meta.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    print("\n" + "=" * 60)
    print("TRAINING REPORT")
    print("=" * 60)
    print(f"Backend            : {final.backend}")
    print(f"Samples            : {metadata['n_samples']} (pos rate {metadata['positive_rate']:.3f})")
    print(f"CV AUC (time-split): {cv['cv_auc_mean']:.3f} +/- {cv['cv_auc_std']:.3f} over {cv['cv_folds']} folds")
    print(f"CV accuracy        : {cv['cv_accuracy_mean']:.3f}")
    print(f"Holdout AUC        : {holdout['holdout_auc']:.3f}")
    print(f"Holdout accuracy   : {holdout['holdout_accuracy']:.3f}")
    print(f"Holdout precision  : {holdout['holdout_precision']:.3f}")
    print(f"Holdout recall     : {holdout['holdout_recall']:.3f}")
    print("Top features       :")
    for name, imp in list(importances.items())[:8]:
        print(f"   {name:<22} {imp:.3f}")
    print(f"Model saved to     : {path}")
    print("=" * 60)
    return metadata


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="train_model", description="Train the SMC ML model.")
    p.add_argument("--source", choices=["mt5", "synthetic", "csv"], default="synthetic")
    p.add_argument("--bars", type=int, default=None, help="Bars per timeframe to load.")
    p.add_argument("--test-frac", type=float, default=0.2, help="Chronological holdout fraction.")
    p.add_argument("--splits", type=int, default=4, help="TimeSeriesSplit folds.")
    p.add_argument("--seed", type=int, default=7, help="Synthetic data seed.")
    p.add_argument("--model-out", type=str, default=None, help="Override model output path.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.from_env(data_source=args.source)
    if args.bars:
        cfg.train_bars = args.bars
    if args.model_out:
        from pathlib import Path

        cfg.model_dir = Path(args.model_out).parent
        cfg.model_filename = Path(args.model_out).name
    cfg.ensure_dirs()
    train(cfg, test_frac=args.test_frac, n_splits=args.splits, seed=args.seed)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
