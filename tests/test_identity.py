from smc_robot.config import RobotConfig, load_config


def test_robot_is_named_fredfx_v1_smc():
    cfg = RobotConfig()
    assert cfg.robot_name == "FredFx v1 SMC"
    assert cfg.comment == "FredFx v1 SMC"
    assert cfg.symbol == "XAUUSDm"
    assert cfg.bias_tf == "H1"
    assert cfg.structure_tf == "M15"
    assert cfg.entry_tf == "M5"
    assert cfg.timeframes == ("H1", "M15", "M5")
    assert cfg.risk_reward == 2.0
    assert cfg.max_open_positions == 1
    assert cfg.require_liquidity_sweep is True
    assert cfg.require_m15_liquidity is True
    assert cfg.require_m15_pd_array is True
    assert cfg.require_m5_structure_after_sweep is True
    assert cfg.breakeven_at_r == 1.0
    assert cfg.trade_news is True


def test_load_config_yaml_defaults():
    cfg = load_config("config.yaml")
    assert cfg.robot_name == "FredFx v1 SMC"
    assert cfg.symbol == "XAUUSDm"
    assert cfg.max_open_positions == 1
    assert cfg.risk_reward == 2.0
