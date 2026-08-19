import pytest

from smc_robot.config import RobotConfig
from smc_robot.risk import lot_size, stops_for_entry, trail_stop


def test_lot_size_starts_at_min_and_adds_001_per_300():
    cfg = RobotConfig()
    assert lot_size(50, cfg) == 0.01
    assert lot_size(299, cfg) == 0.01
    assert lot_size(300, cfg) == 0.01
    assert lot_size(599, cfg) == 0.01
    assert lot_size(600, cfg) == 0.02
    assert lot_size(900, cfg) == 0.03
    assert lot_size(1500, cfg) == 0.05
    assert lot_size(0, cfg) == 0.0


def test_take_profit_is_one_to_two_risk_reward():
    sl, tp = stops_for_entry("buy", entry=2400.0, sl_price=2390.0, risk_reward=2.0)
    assert sl == 2390.0
    assert tp == 2420.0
    sl, tp = stops_for_entry("sell", entry=2400.0, sl_price=2410.0, risk_reward=2.0)
    assert sl == 2410.0
    assert tp == 2380.0


def test_trailing_xl_moves_up_on_longs_after_1r():
    cfg = RobotConfig(breakeven_buffer=0.05, trail_activate_r=1.0, trail_distance_r=1.0)
    entry, sl, risk = 2400.0, 2390.0, 10.0
    # Before 1R: SL stays put.
    new_sl, be = trail_stop("buy", entry, sl, 2405.0, risk, cfg)
    assert new_sl == sl
    assert be is False
    # At 1R: SL jumps to breakeven (up).
    new_sl, be = trail_stop("buy", entry, sl, 2410.0, risk, cfg)
    assert be is True
    assert new_sl == pytest.approx(2400.05)
    # Further profit: SL trails higher.
    new_sl, _ = trail_stop("buy", entry, new_sl, 2430.0, risk, cfg, already_breakeven=True)
    assert new_sl > 2400.05
    assert new_sl == pytest.approx(2420.0)


def test_trailing_xl_moves_down_on_shorts():
    cfg = RobotConfig(breakeven_buffer=0.05, trail_activate_r=1.0, trail_distance_r=1.0)
    entry, sl, risk = 2400.0, 2410.0, 10.0
    new_sl, be = trail_stop("sell", entry, sl, 2390.0, risk, cfg)
    assert be is True
    assert new_sl == pytest.approx(2399.95)
    new_sl, _ = trail_stop("sell", entry, new_sl, 2370.0, risk, cfg, already_breakeven=True)
    assert new_sl < 2399.95
    assert new_sl == pytest.approx(2380.0)


def test_trailing_never_widens_stop():
    cfg = RobotConfig()
    sl, _ = trail_stop("buy", 2400.0, 2395.0, 2398.0, 10.0, cfg)
    assert sl == 2395.0
