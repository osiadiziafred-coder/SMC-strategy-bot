from datetime import datetime, timezone

from smc_robot.config import Settings
from smc_robot.models import Direction, LiquiditySweep, Zone, ZoneKind
from smc_robot.risk.sizing import SymbolSpec, lots_from_balance
from smc_robot.risk.trade_plan import build_trade_plan


def test_lot_size_every_100_dollars_is_one_step():
    spec = SymbolSpec(name="XAUUSDm")
    assert lots_from_balance(100, spec) == 0.01
    assert lots_from_balance(200, spec) == 0.02
    assert lots_from_balance(300, spec) == 0.03
    assert lots_from_balance(500, spec) == 0.05
    assert lots_from_balance(1000, spec) == 0.10
    assert lots_from_balance(199, spec) == 0.01
    assert lots_from_balance(50, spec) == 0.0


def test_lot_size_respects_broker_step_and_max():
    spec = SymbolSpec(name="XAUUSDm", volume_min=0.01, volume_max=0.08, volume_step=0.01)
    assert lots_from_balance(10_000, spec) == 0.08


def test_sl_from_setup_and_tp_is_one_to_two():
    sweep = LiquiditySweep(
        direction=Direction.BUY,
        index=10,
        time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        swept_price=1990.0,
        wick=1988.0,
        close=1992.0,
    )
    ob = Zone(
        kind=ZoneKind.ORDER_BLOCK,
        direction=Direction.BUY,
        index=11,
        time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        low=1989.0,
        high=1994.0,
    )
    settings = Settings()
    settings.risk.sl_buffer_atr_mult = 0.0
    spec = SymbolSpec(name="XAUUSDm")
    plan = build_trade_plan(
        Direction.BUY,
        entry=2000.0,
        sweep=sweep,
        order_block=ob,
        fvg=None,
        atr_value=5.0,
        balance=1000.0,
        spec=spec,
        settings=settings,
    )
    assert plan is not None
    assert plan.sl == 1988.0
    assert plan.sl_source == "sweep_low"
    assert abs(plan.tp - (2000.0 + 2 * (2000.0 - 1988.0))) < 1e-9
    assert plan.lots == 0.10


def test_sell_plan_is_one_to_two_from_sweep_high():
    sweep = LiquiditySweep(
        direction=Direction.SELL,
        index=10,
        time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        swept_price=2010.0,
        wick=2012.0,
        close=2008.0,
    )
    settings = Settings()
    settings.risk.sl_buffer_atr_mult = 0.0
    plan = build_trade_plan(
        Direction.SELL,
        entry=2000.0,
        sweep=sweep,
        order_block=None,
        fvg=None,
        atr_value=5.0,
        balance=500.0,
        spec=SymbolSpec(name="XAUUSDm"),
        settings=settings,
    )
    assert plan is not None
    assert plan.sl == 2012.0
    assert plan.tp == 1976.0
    assert plan.lots == 0.05
