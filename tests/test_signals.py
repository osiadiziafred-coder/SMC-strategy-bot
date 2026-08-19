from smc_robot.backtest import make_ob_retest
from smc_robot.config import RobotConfig
from smc_robot.smc.models import OrderBlock, TradeSetup
from smc_robot.signals import scan_setups
from tests.helpers import ohlc


def test_scan_setups_requires_h1():
    cfg = RobotConfig()
    try:
        scan_setups({"M5": ohlc([1, 2, 3])}, cfg)
    except KeyError as exc:
        assert "H1" in str(exc)
    else:
        raise AssertionError("expected KeyError for missing H1")


def test_trade_setup_rr_is_two():
    setup = TradeSetup(
        timeframe="M5",
        side="buy",
        entry=2400.0,
        sl=2390.0,
        tp=2420.0,
        score=80,
        reason="test",
        event_kind="MSS",
        ob=OrderBlock(0, "bullish", 2395, 2390, "MSS"),
        fvg=None,
    )
    assert setup.rr == 2.0


def test_config_defaults_match_brief():
    cfg = RobotConfig()
    assert cfg.symbol == "XAUUSDM"
    assert cfg.timeframes == ("M5", "M15", "H1")
    assert cfg.risk_reward == 2.0
    assert cfg.max_positions == 3
    assert cfg.trade_news is True
    assert cfg.allow_multiple_trades_per_day is True


def test_scan_finds_three_buy_setups_on_fvg_retest():
    df = make_ob_retest().drop(columns=["time"])
    setups = scan_setups({"M5": df, "M15": df, "H1": df}, RobotConfig())
    assert len(setups) == 3
    assert {s.timeframe for s in setups} == {"M5", "M15", "H1"}
    assert all(s.side == "buy" for s in setups)
    assert all(abs(s.rr - 2.0) < 1e-6 for s in setups)
    assert all(s.ob is not None or s.fvg is not None for s in setups)

