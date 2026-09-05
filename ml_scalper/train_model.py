"""Train per-instrument scalper models with time-ordered validation.

The pipeline:

1. Load M15 / M5 / M1 history (MT5, synthetic, or CSV).
2. Build causal technical features (no SMC).
3. Label:
   * 3-class direction (BUY / SELL / NO_TRADE) from regime+setup+triple-barrier
   * binary expected-outcome (TP before SL at 1:2 RR)
4. Fit LightGBM (or fallback) with **no shuffling**.
5. Sweep confidence thresholds on the chronological holdout — 75% is a starting
   point, not an assumed edge.
6. Save ``{slug}_scalper.joblib`` plus a metrics JSON sidecar.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from .config import CANONICAL_SYMBOLS, Config
from .features import BASE_FEATURES, FEATURE_COLUMNS, build_training_dataset
from .ml_model import ScalperModels, new_models
from .mt5_connector import make_connector


def _safe_auc(y_true, y_score) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def load_history(cfg: Config, connector) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    connector.connect()
    m15 = connector.get_rates(cfg.regime_timeframe, max(cfg.train_bars // 3 + 200, 800))
    m5 = connector.get_rates(cfg.setup_timeframe, cfg.train_bars)
    m1 = connector.get_rates(cfg.entry_timeframe, min(cfg.train_bars * 5, 50_000))
    return m15, m5, m1


def time_ordered_split(X: pd.DataFrame, y: pd.Series, test_frac: float):
    n = len(X)
    split = int(n * (1.0 - test_frac))
    split = min(max(split, 1), n - 1) if n > 1 else n
    return X.iloc[:split], X.iloc[split:], y.iloc[:split], y.iloc[split:]


def _pos_proba(model, X: pd.DataFrame) -> np.ndarray:
    proba = model.predict_proba(X)
    classes = list(getattr(model.estimator, "classes_", [0, 1]))
    if 1 in classes:
        return proba[:, classes.index(1)]
    return proba[:, -1]


def optimize_thresholds(y_true: np.ndarray, p_tp: np.ndarray, p_dir: np.ndarray | None = None) -> dict:
    """Sweep confidence on holdout. Do not assume 0.75 is profitable.

    Objective: 1:2 expectancy ``2p - (1-p)`` among selected trades, subject to a
    minimum number of selections so a tiny cherry-picked slice cannot win.
    """

    y_true = np.asarray(y_true)
    p_tp = np.asarray(p_tp)
    n = len(y_true)
    min_trades = max(25, int(0.03 * n))
    best = {
        "ml_min_confidence": 0.70,
        "min_outcome_prob": 0.55,
        "holdout_selected": 0,
        "holdout_precision": float("nan"),
        "holdout_expectancy_R": float("nan"),
        "note": "no threshold met the minimum-trade constraint; defaults kept",
    }
    dir_ok = np.ones(n, dtype=bool) if p_dir is None else np.asarray(p_dir)
    for t_out in np.round(np.arange(0.50, 0.86, 0.05), 2):
        for t_dir in np.round(np.arange(0.50, 0.86, 0.05), 2):
            selected = (p_tp >= t_out) & (dir_ok >= t_dir if p_dir is not None else True)
            k = int(selected.sum())
            if k < min_trades:
                continue
            prec = float(y_true[selected].mean())
            exp_r = prec * 2.0 - (1.0 - prec)
            if not np.isfinite(best["holdout_expectancy_R"]) or exp_r > best["holdout_expectancy_R"]:
                best = {
                    "ml_min_confidence": float(t_dir),
                    "min_outcome_prob": float(t_out),
                    "holdout_selected": k,
                    "holdout_precision": prec,
                    "holdout_expectancy_R": float(exp_r),
                    "min_trades_constraint": min_trades,
                    "note": "selected by chronological holdout sweep (1:2 expectancy)",
                }
    return best


def train(cfg: Config, test_frac: float = 0.2, n_splits: int = 4, seed: int = 7) -> dict:
    connector = make_connector(cfg, seed=seed) if cfg.data_source == "synthetic" else make_connector(cfg)
    m15, m5, m1 = load_history(cfg, connector)
    print(f"[{cfg.symbol}] Loaded bars -> M15={len(m15)} M5={len(m5)} M1={len(m1)}")

    data = build_training_dataset(m15, m5, m1, cfg)
    X_dir, y_dir = data["X_dir"], data["y_dir"]
    X_out, y_out = data["X_out"], data["y_out"]
    print(
        f"[{cfg.symbol}] Direction samples={len(X_dir)}  classes={y_dir.value_counts().to_dict()}  "
        f"Outcome samples={len(X_out)}  pos_rate={float(y_out.mean()):.3f}"
    )
    if len(X_out) < 400 or y_out.nunique() < 2:
        raise RuntimeError("Insufficient outcome-model training data; increase --bars.")
    if len(X_dir) < 400 or y_dir.nunique() < 2:
        raise RuntimeError("Insufficient direction-model training data; increase --bars.")

    # Chronological holdout for both heads.
    Xd_tr, Xd_te, yd_tr, yd_te = time_ordered_split(X_dir, y_dir, test_frac)
    Xo_tr, Xo_te, yo_tr, yo_te = time_ordered_split(X_out, y_out, test_frac)

    models = new_models(BASE_FEATURES, FEATURE_COLUMNS, cfg.model_backends, cfg.n_estimators)
    models.direction.fit(Xd_tr, yd_tr)
    models.outcome.fit(Xo_tr, yo_tr)

    p_tp_te = _pos_proba(models.outcome, Xo_te)
    pred_te = (p_tp_te >= 0.5).astype(int)
    holdout = {
        "outcome_holdout_auc": _safe_auc(yo_te, p_tp_te),
        "outcome_holdout_accuracy": float(accuracy_score(yo_te, pred_te)),
        "outcome_holdout_precision": float(precision_score(yo_te, pred_te, zero_division=0)),
        "outcome_holdout_recall": float(recall_score(yo_te, pred_te, zero_division=0)),
        "outcome_holdout_samples": int(len(yo_te)),
        "outcome_holdout_positive_rate": float(yo_te.mean()),
        "direction_holdout_accuracy": float(accuracy_score(yd_te, models.direction.estimator.predict(Xd_te[BASE_FEATURES].to_numpy()))),
        "direction_holdout_samples": int(len(yd_te)),
    }
    try:
        holdout["direction_holdout_logloss"] = float(
            log_loss(yd_te, models.direction.predict_proba(Xd_te))
        )
    except ValueError:
        holdout["direction_holdout_logloss"] = float("nan")

    # Time-series CV on the outcome head (the tradable probability).
    tscv = TimeSeriesSplit(n_splits=n_splits)
    aucs = []
    for tr_idx, va_idx in tscv.split(X_out):
        if len(np.unique(y_out.iloc[tr_idx])) < 2:
            continue
        fold = new_models(BASE_FEATURES, FEATURE_COLUMNS, cfg.model_backends, cfg.n_estimators)
        fold.outcome.fit(X_out.iloc[tr_idx], y_out.iloc[tr_idx])
        aucs.append(_safe_auc(y_out.iloc[va_idx], _pos_proba(fold.outcome, X_out.iloc[va_idx])))
    cv = {
        "cv_auc_mean": float(np.nanmean(aucs)) if aucs else float("nan"),
        "cv_auc_std": float(np.nanstd(aucs)) if aucs else float("nan"),
        "cv_folds": len(aucs),
    }

    # Direction-class probability of the *hypothesized* side on outcome holdout
    # is not 1:1 aligned (different row construction). Sweep outcome probability
    # alone, then store a joint default that the brain ANDs with direction P.
    sweep = optimize_thresholds(yo_te.to_numpy(), p_tp_te)

    # Refit on all chronological data for deployment.
    final = new_models(BASE_FEATURES, FEATURE_COLUMNS, cfg.model_backends, cfg.n_estimators)
    final.direction.fit(X_dir, y_dir)
    final.outcome.fit(X_out, y_out)

    metadata = {
        "symbol": cfg.symbol,
        "direction_backend": final.direction.backend,
        "outcome_backend": final.outcome.backend,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_dir_samples": int(len(X_dir)),
        "n_out_samples": int(len(X_out)),
        "n_features_dir": int(X_dir.shape[1]),
        "n_features_out": int(X_out.shape[1]),
        "dir_class_counts": {str(k): int(v) for k, v in y_dir.value_counts().to_dict().items()},
        "outcome_positive_rate": float(y_out.mean()),
        "data_source": cfg.data_source,
        "direction_importance": final.direction.feature_importance(),
        "outcome_importance": final.outcome.feature_importance(),
        "metrics": {**cv, **holdout},
        "threshold_search": sweep,
        "label": {
            "horizon": cfg.label_horizon,
            "atr_sl_mult": cfg.atr_sl_mult,
            "risk_reward": cfg.risk_reward,
        },
        "recommended_ml_min_confidence": sweep.get("ml_min_confidence", cfg.ml_min_confidence),
        "recommended_min_outcome_prob": sweep.get("min_outcome_prob", cfg.min_outcome_prob),
    }
    final.metadata = metadata
    path = final.save(cfg.model_path)
    with open(str(path) + ".meta.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    print("\n" + "=" * 64)
    print(f"TRAINING REPORT  |  {cfg.symbol}")
    print("=" * 64)
    print(f"Backends           : dir={final.direction.backend}  outcome={final.outcome.backend}")
    print(f"Direction samples  : {metadata['n_dir_samples']}  {metadata['dir_class_counts']}")
    print(f"Outcome samples    : {metadata['n_out_samples']}  pos={metadata['outcome_positive_rate']:.3f}")
    print(f"CV AUC (outcome)   : {cv['cv_auc_mean']:.3f} +/- {cv['cv_auc_std']:.3f} over {cv['cv_folds']} folds")
    print(f"Holdout AUC        : {holdout['outcome_holdout_auc']:.3f}")
    print(f"Holdout accuracy   : {holdout['outcome_holdout_accuracy']:.3f}")
    print(f"Holdout precision  : {holdout['outcome_holdout_precision']:.3f}")
    print(f"Dir holdout acc    : {holdout['direction_holdout_accuracy']:.3f}")
    print(
        f"Recommended gates  : P(dir)≥{sweep['ml_min_confidence']:.2f}  "
        f"P(TP)≥{sweep['min_outcome_prob']:.2f}  "
        f"(holdout expectancy {sweep.get('holdout_expectancy_R', float('nan'))})"
    )
    print("Top outcome features:")
    for name, imp in list(metadata["outcome_importance"].items())[:8]:
        print(f"   {name:<22} {imp:.3f}")
    print(f"Model saved to     : {path}")
    print("=" * 64)
    return metadata


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ml_scalper.train_model", description="Train per-instrument ML scalper models.")
    p.add_argument("--source", choices=["mt5", "synthetic", "csv"], default="synthetic")
    p.add_argument("--symbol", default="Volatility 75 Index", help="Instrument or alias (V50, V75, XAUUSD, ...).")
    p.add_argument("--all-symbols", action="store_true", help="Train a separate model for every instrument.")
    p.add_argument("--bars", type=int, default=None, help="M5 bars to load.")
    p.add_argument("--test-frac", type=float, default=0.2)
    p.add_argument("--splits", type=int, default=4)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--model-out", type=str, default=None)
    return p


def _train_one(args, symbol: str) -> dict:
    cfg = Config.from_env(data_source=args.source, symbol=symbol)
    if args.bars:
        cfg.train_bars = args.bars
    if args.model_out and not args.all_symbols:
        from pathlib import Path

        cfg.model_dir = Path(args.model_out).parent
        cfg.model_filename = Path(args.model_out).name
    cfg.ensure_dirs()
    return train(cfg, test_frac=args.test_frac, n_splits=args.splits, seed=args.seed)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols = list(CANONICAL_SYMBOLS) if args.all_symbols else [args.symbol]
    for symbol in symbols:
        _train_one(args, symbol)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
