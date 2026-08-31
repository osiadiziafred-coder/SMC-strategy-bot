from smc_robot.config import Settings
from smc_robot.scoring import rule_score


def test_rule_score_adds_confluence_and_penalizes_poor_tape():
    settings = Settings()
    features = {
        "h1_aligned": 1.0,
        "h1_conflict": 0.0,
        "m30_bos": 1.0,
        "m30_mss": 0.0,
        "m30_choch": 0.0,
        "m30_trend": 1.0,
        "sweep": 1.0,
        "sweep_equal": 0.0,
        "ob_interact": 1.0,
        "fvg_interact": 1.0,
        "m15_bos": 1.0,
        "m15_choch": 0.0,
        "m15_mss": 0.0,
        "poor_conditions": 0.0,
        "efficiency": 0.4,
        "atr_ratio": 1.0,
        "spread_ratio": 1.0,
        "h1_trend": 1.0,
        "m15_trend": 1.0,
        "bars_since_sweep": 2.0,
    }
    total, parts = rule_score(features, settings)
    assert parts["h1_aligned"] == 20
    assert parts["m30_confirmation"] == 15
    assert parts["liquidity_sweep"] == 15
    assert parts["order_block"] == 15
    assert parts["fvg"] == 10
    assert parts["bos"] == 5
    assert parts["good_conditions"] == 10
    assert total == 90

    features["poor_conditions"] = 1.0
    total_poor, parts_poor = rule_score(features, settings)
    assert parts_poor["poor_conditions"] == -20
    assert "good_conditions" not in parts_poor
    assert total_poor == 60
