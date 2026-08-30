from datetime import datetime, timezone, timedelta

from smc_robot.broker.paper import PaperBroker
from smc_robot.config import Settings
from smc_robot.manager import PositionManager
from smc_robot.models import Direction, Position
from smc_robot.risk.protection import ExecutionGuard, Quote
from smc_robot.risk.sizing import SymbolSpec


def test_breakeven_at_plus_one_r():
    broker = PaperBroker(balance=1000.0, bid=2000.0, ask=2000.2)
    settings = Settings()
    manager = PositionManager(broker, settings)
    position = broker.market_order(
        symbol="XAUUSDm",
        direction=Direction.BUY,
        lots=0.10,
        sl=1990.0,
        tp=2020.0,
        deviation_points=40,
        magic=settings.risk.magic,
        comment="test",
    )
    risk = position.initial_risk
    assert risk == position.entry - 1990.0
    broker.set_quote(position.entry + risk - 1.0, position.entry + risk - 0.8)
    manager.manage("XAUUSDm", broker.quote("XAUUSDm"))
    assert broker.positions[0].sl == 1990.0

    broker.set_quote(position.entry + risk, position.entry + risk + 0.2)
    manager.manage("XAUUSDm", broker.quote("XAUUSDm"))
    assert broker.positions[0].sl == position.entry
    assert broker.positions[0].tp == 2020.0


def test_trail_disabled_does_not_move_stop():
    broker = PaperBroker(balance=1000.0, bid=2000.0, ask=2000.2)
    settings = Settings()
    settings.risk.trail_enabled = False
    manager = PositionManager(broker, settings)
    position = broker.market_order(
        symbol="XAUUSDm",
        direction=Direction.BUY,
        lots=0.10,
        sl=1990.0,
        tp=2020.0,
        deviation_points=40,
        magic=settings.risk.magic,
        comment="test",
    )
    broker.set_quote(position.entry + 1.6 * position.initial_risk, position.entry + 1.6 * position.initial_risk + 0.2)
    manager.manage("XAUUSDm", broker.quote("XAUUSDm"), structure_sl=position.entry + 4.0)
    assert broker.positions[0].sl == position.entry
    assert broker.positions[0].trailing_applied is False


def test_trail_never_loosens_stop():
    broker = PaperBroker(balance=1000.0, bid=2000.0, ask=2000.2)
    settings = Settings()
    manager = PositionManager(broker, settings)
    position = broker.market_order(
        symbol="XAUUSDm",
        direction=Direction.BUY,
        lots=0.10,
        sl=1990.0,
        tp=2020.0,
        deviation_points=40,
        magic=settings.risk.magic,
        comment="test",
    )
    broker.set_quote(position.entry + 1.6 * position.initial_risk, position.entry + 1.6 * position.initial_risk + 0.2)
    manager.manage("XAUUSDm", broker.quote("XAUUSDm"), structure_sl=position.entry + 4.0)
    locked = broker.positions[0].sl
    assert locked > position.entry
    manager.manage("XAUUSDm", broker.quote("XAUUSDm"), structure_sl=position.entry - 8.0)
    assert broker.positions[0].sl >= locked


def test_only_one_open_position_allowed():
    broker = PaperBroker()
    settings = Settings()
    manager = PositionManager(broker, settings)
    broker.market_order("XAUUSDm", Direction.BUY, 0.01, 1990, 2020, 40, settings.risk.magic, "a")
    assert manager.can_enter("XAUUSDm") is False


def test_spread_and_stale_quote_are_blocked_news_is_not():
    settings = Settings()
    guard = ExecutionGuard(settings)
    spec = SymbolSpec(name="XAUUSDm")
    now = datetime.now(timezone.utc)
    for _ in range(10):
        guard.observe(20.0)
    ok, _ = guard.check(Quote(bid=2000, ask=2000.2, time=now, spread_points=20), spec)
    assert ok
    blocked, reason = guard.check(Quote(bid=2000, ask=2001.5, time=now, spread_points=150), spec)
    assert not blocked
    assert "spread" in reason
    stale, reason = guard.check(
        Quote(bid=2000, ask=2000.2, time=now - timedelta(seconds=10), spread_points=20),
        spec,
    )
    assert not stale
    assert "stale" in reason
