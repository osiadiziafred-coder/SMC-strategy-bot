import pandas as pd
import pytest

from smc_robot.broker.paper import PaperBroker
from smc_robot.config import RobotConfig
from smc_robot.robot import SmcRobot
from smc_robot.smc.strategy import SmcStrategy
from tests.helpers import impulse_up


def test_robot_holds_only_one_position():
    m5 = impulse_up(2340, 5, min_bars=280)
    broker = PaperBroker(m5, starting_balance=500.0, index=len(m5) - 1)
    robot = SmcRobot(broker, RobotConfig(min_confluence=3, sl_buffer=0.2, lookback_bars=200))
    robot.start()
    robot.on_bar()
    assert len(broker.open_positions(robot.config.magic)) <= 1
    if broker.open_positions():
        with pytest.raises(RuntimeError, match="already has an open position"):
            broker.open_trade("XAUUSDm", "buy", 0.01, 1, 3, "x", robot.config.magic)


def test_paper_run_executes_and_respects_lot_rule():
    m5 = impulse_up(2340, 5, min_bars=280)
    broker = PaperBroker(m5, starting_balance=1000.0, index=len(m5) - 6)
    robot = SmcRobot(broker, RobotConfig(min_confluence=3, sl_buffer=0.2))
    robot.start()
    taken = robot.run_until_end()
    assert taken
    assert all(abs(s.rr - 2.0) < 1e-9 for s in taken)
    fills = broker.closed + broker.open_positions()
    assert fills
    assert fills[0].volume == 0.10
    assert robot.config.max_open_positions == 1
    assert robot.config.trade_news is True
    assert robot.config.max_trades_per_day is None


def test_multiple_trades_allowed_after_flat():
    first = impulse_up(2340, 5, min_bars=280)
    second = impulse_up(2500, 5, min_bars=280)
    second = second.copy()
    second["time"] = second["time"] + 10_000
    m5 = pd.concat([first, second], ignore_index=True)
    broker = PaperBroker(m5, starting_balance=1000.0, index=len(m5) - 8)
    robot = SmcRobot(broker, RobotConfig(min_confluence=3, sl_buffer=0.2))
    robot.start()
    robot.run_until_end()
    assert len(broker.open_positions()) <= 1


def test_demo_cli_runs(capsys):
    from smc_robot.__main__ import main

    assert main(["--mode", "demo", "--balance", "1000"]) == 0
    out = capsys.readouterr().out
    assert "FredFx V1 m5" in out
    assert "XAUUSDm" in out
    assert "1:2" in out


def test_strategy_on_synthetic_gold_does_not_crash():
    m5 = PaperBroker.synthetic_gold(400)
    broker = PaperBroker(m5, starting_balance=200.0, index=250)
    signal = SmcStrategy().evaluate(
        broker.candles("XAUUSDm", "H1", 400),
        broker.candles("XAUUSDm", "M15", 400),
        broker.candles("XAUUSDm", "M5", 400),
    )
    assert signal is None or abs(signal.rr - 2.0) < 1e-9
