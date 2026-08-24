from __future__ import annotations

import argparse
import os

from smc_robot.broker.mt5 import MT5Broker
from smc_robot.broker.paper import PaperBroker
from smc_robot.config import load_config
from smc_robot.robot import SmcRobot, configure_logging


def _mt5_broker() -> MT5Broker:
    login = os.getenv("MT5_LOGIN")
    return MT5Broker(
        login=int(login) if login else None,
        password=os.getenv("MT5_PASSWORD"),
        server=os.getenv("MT5_SERVER"),
        path=os.getenv("MT5_PATH") or None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Python AI SMC robot for XAUUSDm on MT5")
    parser.add_argument("--config", default=None, help="Optional YAML config override")
    parser.add_argument(
        "--mode",
        choices=("live", "dry", "paper"),
        default=os.getenv("SMC_MODE", "dry"),
        help="live=MT5 orders, dry=MT5 data without orders, paper=in-memory broker",
    )
    args = parser.parse_args(argv)

    settings = load_config(args.config)
    configure_logging(settings.robot.log_dir)

    if args.mode == "paper":
        broker = PaperBroker()
        dry_run = False
    elif args.mode == "dry":
        broker = _mt5_broker()
        dry_run = True
    else:
        broker = _mt5_broker()
        dry_run = False

    SmcRobot(broker, settings, dry_run=dry_run).run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
