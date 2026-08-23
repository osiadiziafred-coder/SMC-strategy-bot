from pathlib import Path

from smc_robot.config import RobotConfig


def test_robot_is_named_fredfx_v1_smc():
    cfg = RobotConfig()
    assert cfg.robot_name == "FredFx v1 SMC"
    assert cfg.comment == "FredFx v1 SMC"
    assert cfg.symbol == "XAUUSDm"
    assert cfg.entry_tf == "M5"
    assert cfg.structure_tf == "M15"
    assert cfg.bias_tf == "H1"
    assert cfg.risk_reward == 2.0
    assert cfg.max_open_positions == 1
    assert cfg.require_liquidity_sweep is True
    assert cfg.breakeven_at_r == 1.0


def test_mq5_expert_is_complete():
    path = Path("MQL5/Experts/FredFx_v1_SMC.mq5")
    src = path.read_text(encoding="utf-8")
    assert "FredFx v1 SMC" in src
    assert "#include <Trade/Trade.mqh>" in src
    assert "int OnInit()" in src
    assert "void OnTick()" in src
    assert 'InpSymbol                 = "XAUUSDm"' in src
    assert "PERIOD_M5" in src
    assert "PERIOD_M15" in src
    assert "PERIOD_H1" in src
    assert "DetectSweeps" in src
    assert "DetectLiquidityZones" in src
    assert "DetectStructure" in src
    assert "DetectFvg" in src
    assert "DetectOrderBlocks" in src
    assert "ManageBreakeven" in src
    assert "NewsBlocked" in src
    assert "InpTradeNews" in src
    assert src.count("{") == src.count("}")
    assert "#property strict" not in src
