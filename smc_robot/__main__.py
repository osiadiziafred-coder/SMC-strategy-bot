from __future__ import annotations

import argparse
import logging
import time

from smc_robot.broker.paper import PaperBroker
from smc_robot.config import load_config
from smc_robot.robot import SmcRobot
from smc_robot.summary import render_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FredFx v1 SMC — XAUUSDm Smart Money Concepts robot")
    parser.add_argument("command", nargs="?", default="run", choices=("run", "summary", "diagnose"))
    parser.add_argument("--mode", choices=("demo", "paper", "live"), default="demo")
    parser.add_argument("--balance", type=float, default=1000.0, help="Starting balance for demo/paper")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--config", help="Optional YAML config path")
    parser.add_argument("--csv", help="M5 OHLC CSV for paper mode (columns: time,open,high,low,close)")
    parser.add_argument("--once", action="store_true", help="Evaluate one bar and exit")
    parser.add_argument("--trade-news", dest="trade_news", action="store_true", default=None)
    parser.add_argument("--pause-news", dest="trade_news", action="store_false", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    config = load_config(args.config, symbol=args.symbol, trade_news=args.trade_news)

    if args.command == "summary":
        print(render_summary(config))
        return 0

    if args.mode == "live":
        from smc_robot.broker.mt5 import Mt5Broker

        broker = Mt5Broker()
        robot = SmcRobot(broker, config)
        robot.start()
        try:
            if args.once or args.command == "diagnose":
                robot.on_bar()
                _print_diagnosis(robot)
                return 0
            while True:
                robot.on_bar()
                time.sleep(config.poll_seconds)
        finally:
            robot.stop()

    if args.mode == "paper" and args.csv:
        import pandas as pd

        m5 = pd.read_csv(args.csv)
        broker = PaperBroker(m5, starting_balance=args.balance, index=max(80, len(m5) // 3))
    else:
        m5 = PaperBroker.synthetic_gold(bars=720)
        broker = PaperBroker(m5, starting_balance=args.balance, index=260)

    robot = SmcRobot(broker, config)
    robot.start()
    if args.command == "diagnose":
        robot.on_bar()
        _print_diagnosis(robot)
        return 0

    taken = robot.run_until_end()
    print(f"Robot: {config.robot_name}")
    print(f"Symbol: {config.symbol}")
    print(f"Timeframes: {' → '.join(config.timeframes)}")
    print(f"Risk:reward: 1:{config.risk_reward:.0f}")
    print(f"Lot rule: 0.01 per $100 (start any amount, min {config.min_lot})")
    print(f"Max open positions: {config.max_open_positions}")
    print(f"News filter: {'off (trades through news)' if config.trade_news else 'on'}")
    print(f"SL management: move to breakeven at +{config.breakeven_at_r:.0f}R")
    print(f"Signals taken: {len(taken)}")
    print(f"Closed trades: {len(broker.closed)}")
    print(f"Ending balance: {broker.balance():.2f}")
    for signal in taken:
        print(
            f"  {signal.side.upper()} entry={signal.entry:.2f} sl={signal.sl:.2f} "
            f"tp={signal.tp:.2f} rr={signal.rr:.2f} confluence={signal.confluence} "
            f"{' | '.join(signal.reasons)}"
        )
    return 0


def _print_diagnosis(robot: SmcRobot) -> None:
    evaluation = robot.last_evaluation
    print(f"Robot: {robot.config.robot_name}")
    print(f"Symbol: {robot.config.symbol}")
    if evaluation is None:
        print("No scan ran (flat check / cooldown / news / already in a trade).")
        return
    for stage in evaluation.stages:
        print(f"  pass: {stage}")
    if evaluation.signal is not None:
        signal = evaluation.signal
        print(
            f"SETUP ACCEPTED  {signal.side.upper()} entry={signal.entry:.2f} "
            f"sl={signal.sl:.2f} tp={signal.tp:.2f} rr={signal.rr:.2f}"
        )
        return
    print(f"SETUP REJECTED  {evaluation.blocked_by}")


if __name__ == "__main__":
    raise SystemExit(main())
