from smc_robot.config import RobotConfig
from smc_robot.smc.strategy import SmcStrategy
from tests.helpers import mirror, ranging_chop, smc_buy_setup


def _strategy() -> SmcStrategy:
    return SmcStrategy(RobotConfig(sl_buffer=0.2))


def test_strategy_buys_when_all_smc_gates_line_up():
    h1 = smc_buy_setup(2300)
    m15 = smc_buy_setup(2320)
    m5 = smc_buy_setup(2340)
    evaluation = _strategy().diagnose(h1, m15, m5)
    signal = evaluation.signal
    assert signal is not None, evaluation.blocked_by
    assert signal.side == "buy"
    assert abs(signal.rr - 2.0) < 1e-9
    assert abs(signal.tp - signal.entry) == abs(signal.entry - signal.sl) * 2
    joined = " ".join(signal.reasons).lower()
    assert "h1" in joined
    assert "m15" in joined
    assert "liquidity sweep" in joined
    assert "fvg" in joined or "ob" in joined
    assert any(token in joined for token in ("bos", "choch", "mss"))


def test_strategy_sells_when_bias_is_bearish():
    h1 = mirror(smc_buy_setup(2300))
    m15 = mirror(smc_buy_setup(2320))
    m5 = mirror(smc_buy_setup(2340))
    signal = _strategy().evaluate(h1, m15, m5)
    assert signal is not None
    assert signal.side == "sell"
    assert abs(signal.rr - 2.0) < 1e-9


def test_isolated_h1_signal_is_not_a_trade():
    h1 = smc_buy_setup(2300)
    flat = ranging_chop(2320, bars=50)
    evaluation = _strategy().diagnose(h1, flat, flat)
    assert evaluation.signal is None
    assert evaluation.blocked_by is not None
    assert "H1" in " ".join(evaluation.stages)


def test_m15_without_pd_array_is_rejected():
    h1 = smc_buy_setup(2300)
    m15 = ranging_chop(2320, bars=50)
    m5 = smc_buy_setup(2340)
    evaluation = _strategy().diagnose(h1, m15, m5)
    assert evaluation.signal is None
    assert evaluation.blocked_by is not None


def test_m5_without_sweep_is_rejected():
    h1 = smc_buy_setup(2300)
    m15 = smc_buy_setup(2320)
    m5 = ranging_chop(2340, bars=50)
    evaluation = _strategy().diagnose(h1, m15, m5)
    assert evaluation.signal is None
    assert "sweep" in (evaluation.blocked_by or "").lower() or "tapping" in (evaluation.blocked_by or "").lower() or "structure" in (evaluation.blocked_by or "").lower() or "ob/fvg" in (evaluation.blocked_by or "").lower()


def test_stop_sits_behind_structure_not_a_fixed_distance():
    signal = _strategy().evaluate(smc_buy_setup(2300), smc_buy_setup(2320), smc_buy_setup(2340))
    assert signal is not None
    assert signal.risk > 0.2
    assert abs(signal.risk - 10.0) > 1.0
