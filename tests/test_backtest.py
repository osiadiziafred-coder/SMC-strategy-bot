from smc_robot.backtest import make_gold_trend, multi_tf_frames, run_backtest
from smc_robot.config import RobotConfig, load_config
from smc_robot.robot import strategy_summary
from smc_robot.signals import analyze_timeframe


def test_synthetic_frames_have_all_three_timeframes():
    frames = multi_tf_frames(make_gold_trend(n=180, seed=3))
    assert set(frames) == {"M5", "M15", "H1"}
    assert len(frames["H1"]) < len(frames["M15"]) < len(frames["M5"])


def test_analyze_timeframe_runs_on_synthetic_gold():
    df = make_gold_trend(n=200, seed=3)
    snap = analyze_timeframe(df, "M5", RobotConfig())
    assert snap.last_close > 0
    assert isinstance(snap.events, list)
    assert isinstance(snap.blocks, list)
    assert isinstance(snap.gaps, list)


def test_backtest_completes_and_respects_max_positions():
    result = run_backtest(RobotConfig(starting_balance=300.0), bars=220, seed=3)
    assert result.starting_balance == 300.0
    assert result.open_positions <= 3
    assert result.ending_balance > 0


def test_load_config_and_summary_mention_smc_parts():
    cfg = load_config("config.yaml")
    text = strategy_summary(cfg)
    for token in ("Order Block", "BOS", "MSS", "CHoCH", "FVG", "XAUUSDc", "1 : 2"):
        assert token in text
