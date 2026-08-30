from ml_smc_robot.config import Config
from ml_smc_robot.risk_manager import RiskManager
from ml_smc_robot.smc_detector import Bias, SMCState


def _symbol_info():
    return {"point": 0.01, "digits": 2, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01}


def test_lot_sizing_rule():
    rm = RiskManager(Config())
    si = _symbol_info()
    assert rm.lot_size(100, si) == 0.01
    assert rm.lot_size(200, si) == 0.02
    assert rm.lot_size(500, si) == 0.05
    assert rm.lot_size(1000, si) == 0.10


def test_lot_normalization_clamps_to_min():
    rm = RiskManager(Config())
    si = _symbol_info()
    assert rm.lot_size(10, si) == 0.01  # below min rounds up to broker minimum


def test_buy_sl_tp_respects_1to2_and_ordering():
    rm = RiskManager(Config())
    si = _symbol_info()
    state = SMCState(bias=Bias.BULLISH, atr=3.0, swing_low=2295.0, price=2300.0)
    sl, tp, risk = rm.compute_sl_tp("BUY", 2300.0, state, si)
    assert sl < 2300.0 < tp
    reward = tp - 2300.0
    assert abs(reward / risk - 2.0) < 0.01
    assert rm.validate_rr("BUY", 2300.0, sl, tp)


def test_sell_sl_tp_respects_1to2_and_ordering():
    rm = RiskManager(Config())
    si = _symbol_info()
    state = SMCState(bias=Bias.BEARISH, atr=3.0, swing_high=2305.0, price=2300.0)
    sl, tp, risk = rm.compute_sl_tp("SELL", 2300.0, state, si)
    assert tp < 2300.0 < sl
    reward = 2300.0 - tp
    assert abs(reward / risk - 2.0) < 0.01
    assert rm.validate_rr("SELL", 2300.0, sl, tp)


def test_gates():
    rm = RiskManager(Config(max_spread_points=60, max_open_positions=1))
    assert rm.check_spread(30) is True
    assert rm.check_spread(90) is False
    assert rm.can_open(0) is True
    assert rm.can_open(1) is False
