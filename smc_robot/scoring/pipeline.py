"""Train from historical MT5 data when available, otherwise time-ordered generated bars."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from smc_robot.config import Settings, load_config
from smc_robot.data.history import training_frames
from smc_robot.scoring import FEATURE_NAMES
from smc_robot.scoring.dataset import build_labeled_dataset
from smc_robot.scoring.train import chronological_split, pick_threshold, train_model


def _try_mt5_frames(settings: Settings, bars: int):
    try:
        from smc_robot.broker.mt5 import MT5Broker
    except Exception:
        return None
    login = os.getenv("MT5_LOGIN")
    broker = MT5Broker(
        login=int(login) if login else None,
        password=os.getenv("MT5_PASSWORD"),
        server=os.getenv("MT5_SERVER"),
        path=os.getenv("MT5_PATH") or None,
    )
    try:
        broker.connect()
        symbol = settings.symbol
        h1 = broker.candles(symbol, "H1", max(80, bars // 4))
        m30 = broker.candles(symbol, "M30", max(120, bars // 2))
        m15 = broker.candles(symbol, "M15", bars)
        return h1, m30, m15, "mt5"
    except Exception:
        return None
    finally:
        try:
            broker.shutdown()
        except Exception:
            pass


def load_history(settings: Settings, bars: int = 720, seed: int = 11):
    live = _try_mt5_frames(settings, bars)
    if live is not None:
        return live
    h1, m30, m15 = training_frames(n=bars, seed=seed)
    return h1, m30, m15, "generated_ohlcv"


def train_from_history(
    out_path: str = "models/smc_scorer.joblib",
    settings: Settings | None = None,
    bars: int = 720,
    seed: int = 11,
    allow_fallback: bool = True,
) -> dict:
    settings = settings or Settings()
    h1, m30, m15, source = load_history(settings, bars=bars, seed=seed)
    features, labels, meta = build_labeled_dataset(
        h1, m30, m15, settings=settings, start_index=80, step=2
    )
    if allow_fallback and (len(labels) < 20 or len(set(labels.tolist())) < 2):
        h1_b, m30_b, m15_b = training_frames(n=max(bars, 900), seed=seed + 3)
        features, labels, meta = build_labeled_dataset(
            h1_b, m30_b, m15_b, settings=settings, start_index=70, step=1
        )
        source = f"{source}+generated_fallback"
    history_files = _write_history_files(features, labels, meta, source)
    model = train_model(features, labels, out_path)
    x_tr, y_tr, x_va, y_va, x_te, y_te = chronological_split(features, labels)
    _ = x_tr, y_tr
    threshold = pick_threshold(model, x_va, y_va) if len(y_va) else settings.scoring.ml_min_probability
    test_acc = float((model.predict(x_te) == y_te).mean()) if len(y_te) else 0.0
    return {
        "model": out_path,
        "pkl": str(Path(out_path).with_name("smc_model.pkl")),
        "history_files": history_files,
        "source": source,
        "rows": int(len(labels)),
        "positives": int(labels.sum()),
        "negatives": int((labels == 0).sum()),
        "features": FEATURE_NAMES,
        "validation_threshold": threshold,
        "held_out_accuracy": test_acc,
        "shuffle": False,
        "note": "Trained on time-ordered SMC features. Live trading loads this file; it does not refit.",
    }


def _write_history_files(features, labels, meta, source: str) -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    roots = [
        repo_root / "data" / "historical_data",
        repo_root / "python_smc_ml_robot" / "data" / "historical_data",
    ]
    lines = []
    for row, _feat, lab in zip(meta, features, labels):
        rec = dict(row)
        rec["label"] = int(lab)
        rec["source"] = source
        lines.append(json.dumps(rec, default=str))
    written: list[str] = []
    body = "\n".join(lines) + ("\n" if lines else "")
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        dest = root / "setups.jsonl"
        dest.write_text(body, encoding="utf-8")
        written.append(str(dest))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train SMC ML model from historical bars")
    parser.add_argument("--out", default="models/smc_scorer.joblib")
    parser.add_argument("--config", default=None)
    parser.add_argument("--bars", type=int, default=720)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args(argv)
    settings = load_config(args.config)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    report = train_from_history(args.out, settings=settings, bars=args.bars, seed=args.seed)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
