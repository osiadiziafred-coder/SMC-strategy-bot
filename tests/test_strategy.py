from smc_robot.config import RobotConfig
from smc_robot.smc.strategy import SmcStrategy
from tests.helpers import impulse_up


def _mirror(df):
    out = df.copy()
    mid = 4000.0
    out["open"] = mid - df["open"]
    out["close"] = mid - df["close"]
    out["high"] = mid - df["low"]
    out["low"] = mid - df["high"]
    return out


def test_strategy_buys_on_aligned_smc_confluence():
    h1 = impulse_up(2300, 4)
    m15 = impulse_up(2320, 4)
    m5 = impulse_up(2340, 4)
    signal = SmcStrategy(RobotConfig(min_confluence=3, sl_buffer=0.2)).evaluate(h1, m15, m5)
    assert signal is not None
    assert signal.side == "buy"
    assert abs(signal.rr - 2.0) < 1e-9
    assert abs(signal.tp - signal.entry) == abs(signal.entry - signal.sl) * 2
    assert signal.confluence >= 3
    assert any("FVG" in r or "order block" in r for r in signal.reasons)


def test_strategy_sells_when_bias_is_bearish():
    h1 = _mirror(impulse_up(2300, 4))
    m15 = _mirror(impulse_up(2320, 4))
    m5 = _mirror(impulse_up(2340, 4))
    signal = SmcStrategy(RobotConfig(min_confluence=3, sl_buffer=0.2)).evaluate(h1, m15, m5)
    assert signal is not None
    assert signal.side == "sell"
    assert abs(signal.rr - 2.0) < 1e-9
