import pandas as pd
import pytest

from smc_robot.broker.paper import PaperBroker
from smc_robot.config import NewsEvent, RobotConfig
from smc_robot.robot import SmcRobot
from smc_robot.smc.strategy import SmcStrategy
from tests.helpers import smc_buy_setup


def test_robot_holds_only_one_position():
    m5 = smc_buy_setup(2340, min_bars=280)
    broker = PaperBroker(m5, starting_balance=500.0, index=len(m5) - 1)
    robot = SmcRobot(broker, RobotConfig(sl_buffer=0.2, lookback_bars=400))
    robot.start()
    robot.on_bar()
    assert len(broker.open_positions(robot.config.magic)) <= 1
    if broker.open_positions():
        with pytest.raises(RuntimeError, match="already has an open position"):
            broker.open_trade("XAUUSDm", "buy", 0.01, 1, 3, "x", robot.config.magic)


def test_paper_run_executes_and_respects_lot_rule():
    m5 = smc_buy_setup(2340, min_bars=280)
    broker = PaperBroker(m5, starting_balance=1000.0, index=len(m5) - 6)
    robot = SmcRobot(broker, RobotConfig(sl_buffer=0.2))
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
    first = smc_buy_setup(2340, min_bars=280)
    second = smc_buy_setup(2500, min_bars=280)
    second = second.copy()
    second["time"] = second["time"] + 10_000
    m5 = pd.concat([first, second], ignore_index=True)
    broker = PaperBroker(m5, starting_balance=1000.0, index=len(m5) - 8)
    robot = SmcRobot(broker, RobotConfig(sl_buffer=0.2, cooldown_bars=0))
    robot.start()
    robot.run_until_end()
    assert len(broker.open_positions()) <= 1


def test_moves_sl_to_breakeven_at_one_r():
    m5 = smc_buy_setup(2340, min_bars=40)
    broker = PaperBroker(m5, starting_balance=1000.0, index=len(m5) - 1)
    broker._m5.loc[broker._index, ["open", "high", "low", "close"]] = [2000.0, 2000.2, 1999.8, 2000.0]
    robot = SmcRobot(broker, RobotConfig())
    robot.start()
    position = broker.open_trade("XAUUSDm", "buy", 0.10, 1990.0, 2040.0, "be-test", robot.config.magic)
    robot.initial_stops[position.ticket] = position.sl
    broker._m5.loc[broker._index, "close"] = 2010.0
    broker._m5.loc[broker._index, "high"] = 2010.0
    robot._manage_open_trade()
    updated = broker.open_positions()
    assert updated
    assert updated[0].sl == pytest.approx(updated[0].entry)


def test_news_pause_blocks_new_entries():
    from datetime import datetime, timezone

    m5 = smc_buy_setup(2340, min_bars=80)
    m5 = m5.copy()
    start = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    m5["time"] = [start + pd.Timedelta(minutes=5 * i) for i in range(len(m5))]
    broker = PaperBroker(m5, starting_balance=1000.0, index=len(m5) - 1)
    cfg = RobotConfig(
        sl_buffer=0.2,
        trade_news=False,
        news_blackout_minutes=180,
        news_events=(NewsEvent(time=start, title="NFP", impact="high"),),
    )
    robot = SmcRobot(broker, cfg)
    robot.start()
    assert robot.on_bar() is None
    assert broker.open_positions() == []


def test_demo_cli_runs(capsys):
    from smc_robot.__main__ import main

    assert main(["--mode", "demo", "--balance", "1000"]) == 0
    out = capsys.readouterr().out
    assert "FredFx v1 SMC" in out
    assert "XAUUSDm" in out
    assert "1:2" in out


def test_summary_cli(capsys):
    from smc_robot.__main__ import main

    assert main(["summary"]) == 0
    out = capsys.readouterr().out
    assert "FredFx v1 SMC" in out
    assert "liquidity sweep" in out.lower()
    assert "breakeven" in out.lower()
    assert "0.01" in out
    assert "H1" in out and "M15" in out and "M5" in out


def test_diagnose_cli(capsys):
    from smc_robot.__main__ import main

    assert main(["diagnose", "--mode", "demo"]) == 0
    out = capsys.readouterr().out
    assert "FredFx v1 SMC" in out
    assert "SETUP" in out


def test_strategy_on_synthetic_gold_does_not_crash():
    m5 = PaperBroker.synthetic_gold(400)
    broker = PaperBroker(m5, starting_balance=200.0, index=250)
    signal = SmcStrategy().evaluate(
        broker.candles("XAUUSDm", "H1", 400),
        broker.candles("XAUUSDm", "M15", 400),
        broker.candles("XAUUSDm", "M5", 400),
    )
    assert signal is None or abs(signal.rr - 2.0) < 1e-9
