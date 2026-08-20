from smc_robot.config import RobotConfig
from smc_robot.smc.strategy import SmcStrategy
from tests.helpers import mirror, smc_buy_setup


def test_strategy_buys_on_aligned_smc_confluence():
    h1 = smc_buy_setup(2300)
    m15 = smc_buy_setup(2320)
    m5 = smc_buy_setup(2340)
    signal = SmcStrategy(RobotConfig(min_confluence=4, sl_buffer=0.2)).evaluate(h1, m15, m5)
    assert signal is not None
    assert signal.side == "buy"
    assert abs(signal.rr - 2.0) < 1e-9
    assert abs(signal.tp - signal.entry) == abs(signal.entry - signal.sl) * 2
    assert signal.confluence >= 4
    assert any("liquidity sweep" in r for r in signal.reasons)
    assert any("FVG" in r or "order block" in r for r in signal.reasons)


def test_strategy_sells_when_bias_is_bearish():
    h1 = mirror(smc_buy_setup(2300))
    m15 = mirror(smc_buy_setup(2320))
    m5 = mirror(smc_buy_setup(2340))
    signal = SmcStrategy(RobotConfig(min_confluence=4, sl_buffer=0.2)).evaluate(h1, m15, m5)
    assert signal is not None
    assert signal.side == "sell"
    assert abs(signal.rr - 2.0) < 1e-9
