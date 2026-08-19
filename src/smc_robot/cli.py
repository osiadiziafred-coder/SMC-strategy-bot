from __future__ import annotations

import argparse
import logging
import sys

from smc_robot.backtest import run_backtest
from smc_robot.config import load_config
from smc_robot.robot import strategy_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="smc-robot",
        description="SMC multi-timeframe robot for XAUUSDM (M5 / M15 / H1).",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="summary",
        choices=("summary", "backtest", "paper", "live"),
        help="summary (default), backtest, paper, or live MT5",
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--bars", type=int, default=400)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = load_config(args.config)

    if args.command == "summary":
        print(strategy_summary(config))
        return 0

    if args.command == "backtest":
        result = run_backtest(config, bars=args.bars)
        print(strategy_summary(config))
        print()
        print("Backtest on synthetic XAUUSDM path")
        print(f"  start  : ${result.starting_balance:.2f}")
        print(f"  end    : ${result.ending_balance:.2f}")
        print(f"  profit : ${result.profit:.2f}")
        print(f"  closed : {result.trades}  (W {result.wins} / L {result.losses})")
        print(f"  open   : {result.open_positions}")
        print(f"  win%   : {result.win_rate:.0%}")
        return 0

    if args.command == "paper":
        from smc_robot.backtest import make_ob_retest
        from smc_robot.broker.paper import PaperBroker
        from smc_robot.robot import SMCRobot

        df = make_ob_retest()
        frames = {"M5": df, "M15": df, "H1": df}
        broker = PaperBroker(config, frames=frames)
        report = SMCRobot(broker, config).step(frames)
        print(strategy_summary(config))
        print()
        print(f"Paper scan opened {len(report.opened)} trade(s), trailed {len(report.trailed)}.")
        for pos in report.opened:
            print(
                f"  #{pos.ticket} {pos.side} {pos.timeframe} vol={pos.volume} "
                f"entry={pos.entry:.2f} sl={pos.sl:.2f} tp={pos.tp:.2f}"
            )
        for msg in report.skipped:
            print(f"  skip: {msg}")
        return 0

    if args.command == "live":
        from smc_robot.broker.mt5 import MT5Broker
        from smc_robot.robot import SMCRobot

        broker = MT5Broker(config)
        report = SMCRobot(broker, config).step()
        print(f"Live scan opened {len(report.opened)} / trailed {len(report.trailed)}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
