from datetime import datetime, timezone

from smc_robot.broker.paper import PaperBroker
from smc_robot.config import Settings
from smc_robot.engine import SmcEngine
from smc_robot.models import Direction
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec
from smc_robot.robot import SmcRobot
from smc_robot.smc.analyze import analyze_timeframe
from tests.factories import bullish_structure_candles, m15_buy_setup


def test_h1_wave_is_bullish():
    candles = bullish_structure_candles(n=96, minutes=60)
    settings = Settings()
    analysis = analyze_timeframe(candles, settings)
    assert analysis.trend.value == "BULLISH"


def test_m15_buy_setup_has_sweep_and_zone():
    candles = m15_buy_setup()
    settings = Settings()
    analysis = analyze_timeframe(candles, settings)
    assert analysis.sweeps, "expected a sell-side liquidity sweep"
    assert analysis.fvgs or analysis.order_blocks, "expected FVG or order block"


def test_engine_takes_aligned_buy_setup():
    settings = Settings()
    h1 = bullish_structure_candles(n=96, minutes=60)
    m30 = bullish_structure_candles(n=96, minutes=30)
    m15 = m15_buy_setup()
    engine = SmcEngine(settings)
    last = m15[-1]
    quote = Quote(
        bid=last.close - 0.1,
        ask=last.close,
        time=datetime.now(timezone.utc),
        spread_points=20,
    )
    decision = engine.evaluate(h1, m30, m15, quote, SymbolSpec(name="XAUUSDm"), 1000.0, [20, 20, 21])
    assert decision.signal is not None, decision.reason
    assert decision.signal.direction == Direction.BUY
    assert decision.signal.plan.lots == 0.10
    assert decision.signal.plan.tp > decision.signal.plan.entry
    risk = decision.signal.plan.entry - decision.signal.plan.sl
    assert abs((decision.signal.plan.tp - decision.signal.plan.entry) / risk - 2.0) < 1e-6
    assert decision.signal.score.total >= settings.scoring.min_score


def test_engine_skips_without_sweep():
    settings = Settings()
    h1 = bullish_structure_candles(n=96, minutes=60)
    m30 = bullish_structure_candles(n=96, minutes=30)
    m15 = bullish_structure_candles(n=96, minutes=15)
    engine = SmcEngine(settings)
    last = m15[-1]
    quote = Quote(bid=last.close, ask=last.close + 0.2, time=datetime.now(timezone.utc), spread_points=20)
    decision = engine.evaluate(h1, m30, m15, quote, SymbolSpec(name="XAUUSDm"), 1000.0, [20])
    assert decision.signal is None


def test_robot_step_sends_order_and_refuses_second_position():
    settings = Settings()
    settings.robot.analyze_on_closed_bar_only = False
    h1 = bullish_structure_candles(n=96, minutes=60)
    m30 = bullish_structure_candles(n=96, minutes=30)
    m15 = m15_buy_setup()
    last = m15[-1]
    broker = PaperBroker(
        balance=1000.0,
        candles_by_tf={"H1": h1, "M30": m30, "M15": m15},
        bid=last.close - 0.1,
        ask=last.close,
        quote_time=datetime.now(timezone.utc),
    )
    robot = SmcRobot(broker, settings, dry_run=False)
    result = robot.step()
    assert result == "order_sent", result
    assert len(broker.positions) == 1
    result2 = robot.step()
    assert result2 == "manage_open_position"
    assert len(broker.positions) == 1
