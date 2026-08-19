from datetime import datetime, timezone

from smc_robot.backtest import make_ob_retest
from smc_robot.broker.paper import PaperBroker
from smc_robot.config import RobotConfig
from smc_robot.robot import SMCRobot, strategy_summary
from smc_robot.smc.models import TradeSetup


def _setup(tf: str, entry: float = 2400.0) -> TradeSetup:
    return TradeSetup(
        timeframe=tf,
        side="buy",
        entry=entry,
        sl=entry - 5,
        tp=entry + 10,
        score=80,
        reason="unit",
        event_kind="MSS",
        bar_index=10,
    )


def test_robot_picks_at_most_three_positions(monkeypatch):
    cfg = RobotConfig(starting_balance=900.0, max_positions=3)
    broker = PaperBroker(cfg, price=2400.0)
    robot = SMCRobot(broker, cfg)
    monkeypatch.setattr(
        "smc_robot.robot.scan_setups",
        lambda frames, config: [_setup("M5"), _setup("M15"), _setup("H1"), _setup("M5")],
    )
    report = robot.step(frames={"H1": None, "M15": None, "M5": None})  # type: ignore[arg-type]
    assert len(report.opened) == 3
    assert {p.timeframe for p in report.opened} == {"M5", "M15", "H1"}

    report2 = robot.step(frames={"H1": None, "M15": None, "M5": None})  # type: ignore[arg-type]
    assert report2.opened == []
    assert any("max 3" in msg for msg in report2.skipped)


def test_one_position_per_timeframe(monkeypatch):
    cfg = RobotConfig(starting_balance=600.0, one_position_per_timeframe=True)
    broker = PaperBroker(cfg, price=2400.0)
    robot = SMCRobot(broker, cfg)
    monkeypatch.setattr(
        "smc_robot.robot.scan_setups",
        lambda frames, config: [_setup("M5"), _setup("M5")],
    )
    report = robot.step(frames={"H1": None})  # type: ignore[arg-type]
    assert len(report.opened) == 1
    assert any("M5 already" in msg for msg in report.skipped)


def test_lot_grows_with_balance_on_open(monkeypatch):
    cfg = RobotConfig(starting_balance=900.0)
    broker = PaperBroker(cfg, price=2400.0)
    robot = SMCRobot(broker, cfg)
    monkeypatch.setattr("smc_robot.robot.scan_setups", lambda frames, config: [_setup("M15")])
    report = robot.step(frames={"H1": None})  # type: ignore[arg-type]
    assert report.opened[0].volume == 0.03


def test_trailing_adjusts_xl_up_when_trade_moves(monkeypatch):
    cfg = RobotConfig(starting_balance=300.0, spread=0.0, breakeven_buffer=0.0)
    broker = PaperBroker(cfg, price=2400.0)
    robot = SMCRobot(broker, cfg)
    monkeypatch.setattr("smc_robot.robot.scan_setups", lambda frames, config: [_setup("H1")])
    report = robot.step(frames={"H1": None})  # type: ignore[arg-type]
    pos = report.opened[0]
    original_sl = pos.sl
    # Drive price 1R in profit so XL (SL) is walked up.
    broker.set_price(pos.entry + pos.original_risk + 0.01)
    trail_report = robot.step(frames={"H1": None})  # type: ignore[arg-type]
    assert trail_report.trailed
    ticket, new_sl = trail_report.trailed[0]
    assert ticket == pos.ticket
    assert new_sl > original_sl


def test_multiple_trades_per_day_including_news():
    cfg = RobotConfig()
    assert cfg.allow_multiple_trades_per_day is True
    assert cfg.trade_news is True
    assert "news" in strategy_summary(cfg).lower()


def test_paper_broker_hits_tp_at_one_to_two():
    cfg = RobotConfig(starting_balance=300.0, spread=0.0)
    broker = PaperBroker(cfg, price=2400.0)
    pos = broker.open_trade("buy", 0.01, sl=2390.0, tp=2420.0, timeframe="M5")
    broker.set_price(2420.0, datetime.now(timezone.utc))
    closed = [p for p in broker.account().positions if p.closed]
    assert closed[0].ticket == pos.ticket
    assert closed[0].exit_reason == "tp"
    assert closed[0].profit > 0


def test_paper_robot_opens_three_positions_on_retest():
    cfg = RobotConfig(starting_balance=300.0, spread=0.0)
    df = make_ob_retest()
    frames = {"M5": df, "M15": df, "H1": df}
    broker = PaperBroker(cfg, frames=frames)
    report = SMCRobot(broker, cfg).step(frames)
    assert len(report.opened) == 3
    assert {p.timeframe for p in report.opened} == {"M5", "M15", "H1"}
    assert all(p.volume == 0.01 for p in report.opened)
    for pos in report.opened:
        assert abs((pos.tp - pos.entry) / (pos.entry - pos.sl) - 2.0) < 1e-6

