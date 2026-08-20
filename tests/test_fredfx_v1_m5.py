from pathlib import Path

from smc_robot.config import RobotConfig


def test_robot_is_named_fredfx_v1_m5():
    cfg = RobotConfig()
    assert cfg.robot_name == "FredFx V1 m5"
    assert cfg.comment == "FredFx V1 m5"
    assert cfg.symbol == "XAUUSDm"
    assert cfg.entry_tf == "M5"
    assert cfg.risk_reward == 2.0
    assert cfg.require_liquidity_sweep is True
    assert cfg.breakeven_at_r == 1.0


def test_mq5_expert_is_complete():
    path = Path("MQL5/Experts/FredFx_V1_m5.mq5")
    src = path.read_text(encoding="utf-8")
    assert "FredFx V1 m5" in src
    assert "#include <Trade/Trade.mqh>" in src
    assert "int OnInit()" in src
    assert "void OnTick()" in src
    assert 'InpSymbol          = "XAUUSDm"' in src
    assert "PERIOD_M5" in src
    assert "PERIOD_M15" in src
    assert "PERIOD_H1" in src
    assert "DetectSweeps" in src
    assert "ManageBreakeven" in src
    assert src.count("{") == src.count("}")
    assert "#property strict" not in src
