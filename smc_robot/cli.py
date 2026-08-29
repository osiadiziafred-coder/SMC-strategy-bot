from __future__ import annotations

import argparse
import json
import os
import sys

from smc_robot.broker.mt5 import MT5Broker
from smc_robot.broker.paper import PaperBroker
from smc_robot.config import load_config
from smc_robot.robot import SmcRobot, configure_logging
from smc_robot.smc.concepts import render_concepts


def _mt5_broker() -> MT5Broker:
    login = os.getenv("MT5_LOGIN")
    return MT5Broker(
        login=int(login) if login else None,
        password=os.getenv("MT5_PASSWORD"),
        server=os.getenv("MT5_SERVER"),
        path=os.getenv("MT5_PATH") or None,
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"explain", "train", "backtest", "walk-forward", "verify"}:
        command = argv.pop(0)
        if command == "explain":
            print(render_concepts())
            return 0
        if command == "verify":
            from smc_robot.verify import run_verification

            report = run_verification()
            print(json.dumps(report, indent=2, default=str))
            return 0 if report["passed"] else 1
        if command == "train":
            return _cmd_train(argv)
        if command == "backtest":
            return _cmd_backtest(argv, walk=False)
        return _cmd_backtest(argv, walk=True)

    parser = argparse.ArgumentParser(description="Python ML SMC robot for XAUUSDm")
    parser.add_argument("--config", default=None, help="Optional YAML config override")
    parser.add_argument(
        "--mode",
        choices=("live", "dry", "paper", "bridge"),
        default=os.getenv("SMC_MODE", "dry"),
        help="live=MT5 Python API, dry=data only, paper=memory, bridge=MQL5 files",
    )
    args = parser.parse_args(argv)

    settings = load_config(args.config)
    configure_logging(settings.robot.log_dir)

    if args.mode == "paper":
        broker = PaperBroker()
        dry_run = False
        use_bridge = False
    elif args.mode == "bridge":
        broker = _mt5_broker()
        dry_run = False
        use_bridge = True
    elif args.mode == "dry":
        broker = _mt5_broker()
        dry_run = True
        use_bridge = False
    else:
        broker = _mt5_broker()
        dry_run = False
        use_bridge = False

    SmcRobot(broker, settings, dry_run=dry_run, use_bridge=use_bridge).run_forever()
    return 0


def _cmd_train(argv: list[str]) -> int:
    from pathlib import Path

    import numpy as np

    from smc_robot.scoring import FEATURE_NAMES
    from smc_robot.scoring.train import chronological_split, pick_threshold, train_model

    parser = argparse.ArgumentParser(description="Offline ML train (no live retrain)")
    parser.add_argument("--out", default="models/smc_scorer.joblib")
    parser.add_argument("--rows", type=int, default=240)
    args = parser.parse_args(argv)
    rng = np.random.default_rng(7)
    n = args.rows
    X = rng.normal(size=(n, len(FEATURE_NAMES)))
    # Label: aligned HTF + sweep + MSS-like columns tend to win.
    y = ((X[:, 3] + X[:, 11] + X[:, 10] + X[:, 21] * 0.3) > 0.15).astype(int)
    y[0], y[1] = 0, 1
    x_tr, y_tr, x_va, y_va, x_te, y_te = chronological_split(X, y)
    model = train_model(x_tr, y_tr, args.out)
    threshold = pick_threshold(model, x_va, y_va) if len(y_va) else 0.60
    test_acc = float((model.predict(x_te) == y_te).mean()) if len(y_te) else 0.0
    print(
        json.dumps(
            {
                "model": args.out,
                "features": FEATURE_NAMES,
                "validation_threshold": threshold,
                "held_out_accuracy": test_acc,
                "note": "Retrain only through this offline command. Live trades do not auto-fit.",
            },
            indent=2,
        )
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    return 0


def _cmd_backtest(argv: list[str], walk: bool) -> int:
    from smc_robot.backtest import demo_series, run_backtest, walk_forward

    parser = argparse.ArgumentParser(description="Replay SMC setups (synthetic if no data)")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    settings = load_config(args.config)
    h1, m30, m15 = demo_series()
    if walk:
        print(json.dumps(walk_forward(h1, m30, m15, settings), indent=2, default=str))
        return 0
    report = run_backtest(h1, m30, m15, settings)
    print(json.dumps(report.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
