from __future__ import annotations

import argparse
import logging
import time

from smc_robot.broker.paper import PaperBroker
from smc_robot.config import RobotConfig
from smc_robot.robot import SmcRobot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XAUUSDM Smart Money Concepts robot")
    parser.add_argument("--mode", choices=("demo", "paper", "live"), default="demo")
    parser.add_argument("--balance", type=float, default=1000.0, help="Starting balance for demo/paper")
    parser.add_argument("--symbol", default="XAUUSDM")
    parser.add_argument("--csv", help="M5 OHLC CSV for paper mode (columns: time,open,high,low,close)")
    parser.add_argument("--once", action="store_true", help="Evaluate one bar and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    config = RobotConfig(symbol=args.symbol)

    if args.mode == "live":
        from smc_robot.broker.mt5 import Mt5Broker

        broker = Mt5Broker()
        robot = SmcRobot(broker, config)
        robot.start()
        try:
            if args.once:
                robot.on_bar()
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
    taken = robot.run_until_end()
    print(f"Symbol: {config.symbol}")
    print(f"Timeframes: {', '.join(config.timeframes)}")
    print(f"Risk:reward: 1:{config.risk_reward:.0f}")
    print(f"Lot rule: 0.01 per $100 (start any amount, min {config.min_lot})")
    print(f"Max open positions: {config.max_open_positions}")
    print(f"News filter: {'off (trades through news)' if config.trade_news else 'on'}")
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


if __name__ == "__main__":
    raise SystemExit(main())
