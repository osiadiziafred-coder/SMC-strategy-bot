from smc_robot.config import Position, RobotConfig
from smc_robot.risk import lot_size, r_multiple, take_profit, trailing_stop


def test_lot_size_adds_0_01_per_100():
    cfg = RobotConfig()
    assert lot_size(100, cfg) == 0.01
    assert lot_size(200, cfg) == 0.02
    assert lot_size(999, cfg) == 0.09
    assert lot_size(1000, cfg) == 0.10
    assert lot_size(50, cfg) == 0.01  # any starting amount still gets min lot
    assert lot_size(0, cfg) == 0.0


def test_take_profit_is_one_to_two():
    assert take_profit(2000, 1990, "buy", 2.0) == 2020
    assert take_profit(2000, 2010, "sell", 2.0) == 1980


def test_trailing_stop_moves_buy_sl_up():
    pos = Position(
        ticket=1,
        side="buy",
        volume=0.01,
        entry=2000.0,
        sl=1990.0,
        tp=2020.0,
        initial_sl=1990.0,
        opened_at=0,
    )
    cfg = RobotConfig()
    assert trailing_stop(pos, 1995.0, cfg) == 1990.0
    be = trailing_stop(pos, 2010.0, cfg)
    assert be == 2000.0
    pos.sl = be
    trailed = trailing_stop(pos, 2015.0, cfg)
    assert trailed == 2005.0
    assert trailed > pos.sl
    assert r_multiple(pos, 2010.0) == 1.0
