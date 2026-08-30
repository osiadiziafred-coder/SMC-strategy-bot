from smc_bot.data import SyntheticConfig, generate_synthetic
from smc_bot.indicators import Direction
from smc_bot.strategy import StrategyConfig, build_setups


def test_build_setups_produces_valid_setups():
    df = generate_synthetic(SyntheticConfig(n=1000, seed=5))
    setups = build_setups(df, StrategyConfig(risk_reward=2.0))
    assert setups, "expected setups on synthetic data"

    for s in setups:
        assert s.risk > 0
        assert s.expires_at > s.active_from
        # Reward-to-risk should match configuration (2.0) within rounding.
        assert abs(s.reward / s.risk - 2.0) < 0.05
        if s.direction == Direction.BULLISH:
            assert s.stop_loss < s.entry < s.take_profit
        else:
            assert s.take_profit < s.entry < s.stop_loss


def test_only_choch_filters_setups():
    df = generate_synthetic(SyntheticConfig(n=1000, seed=5))
    all_setups = build_setups(df, StrategyConfig(only_choch=False))
    choch_setups = build_setups(df, StrategyConfig(only_choch=True))
    assert len(choch_setups) <= len(all_setups)


def test_risk_reward_scales_target():
    df = generate_synthetic(SyntheticConfig(n=1000, seed=5))
    rr2 = build_setups(df, StrategyConfig(risk_reward=2.0))
    rr4 = build_setups(df, StrategyConfig(risk_reward=4.0))
    assert rr2 and rr4
    assert abs(rr4[0].reward / rr4[0].risk - 4.0) < 0.05
