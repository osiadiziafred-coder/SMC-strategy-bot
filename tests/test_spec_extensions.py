from datetime import datetime, timezone
from pathlib import Path

from smc_robot.backtest import run_backtest
from smc_robot.bridge import FileBridge
from smc_robot.config import NewsConfig, Settings
from smc_robot.data.setups import bullish_structure_candles, m15_buy_setup
from smc_robot.models import Direction, SwingKind
from smc_robot.risk.daily import DailyGuard
from smc_robot.smc.concepts import render_concepts
from smc_robot.smc.liquidity import LiquidityPool, detect_sweeps
from smc_robot.smc.news import news_block_reason
from smc_robot.data.synthetic import candles_from_ohlc


def test_equal_liquidity_sweep_is_flagged():
    pool = LiquidityPool(kind=SwingKind.LOW, price=100.0, index=2, equal=True, members=3)
    rows = [
        (101.0, 102.0, 100.5, 101.2),
        (101.2, 101.8, 100.8, 101.0),
        (101.0, 101.5, 100.2, 101.1),
        (100.7, 101.8, 99.4, 101.2),
    ]
    candles = candles_from_ohlc(rows, datetime(2024, 1, 1, tzinfo=timezone.utc), 15)
    sweeps = detect_sweeps(candles, [pool])
    assert sweeps
    assert sweeps[0].equal_liquidity is True
    assert sweeps[0].members == 3
    assert sweeps[0].rejection_ratio > 0


def test_news_modes_do_not_hardcode_one_behavior():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    events = [{"time": now, "impact": "high", "currency": "USD", "title": "CPI"}]
    allow = NewsConfig(mode="allow")
    assert news_block_reason(now, allow, events) == ""
    avoid = NewsConfig(mode="avoid_high", minutes_before=30, minutes_after=30)
    assert "news" in news_block_reason(now, avoid, events)


def test_daily_guard_stops_after_loss_limit():
    settings = Settings()
    settings.daily_risk.max_daily_loss_percent = 2.0
    guard = DailyGuard(settings)
    now = datetime.now(timezone.utc)
    guard.roll(now, 1000.0)
    guard.record_close(-25.0, 10)
    ok, reason = guard.allow(975.0)
    assert ok is False
    assert reason == "max_daily_loss"


def test_bridge_writes_command_file(tmp_path: Path):
    settings = Settings()
    settings.bridge.directory = str(tmp_path)
    bridge = FileBridge(settings)
    bridge.heartbeat()
    assert (tmp_path / "command.json").exists()
    assert "HEARTBEAT" in (tmp_path / "command.json").read_text(encoding="utf-8")


def test_concepts_cover_requested_terms():
    text = render_concepts()
    for word in ("LIQUIDITY SWEEP", "EQUAL-LIQUIDITY", "ORDER BLOCK", "FAIR VALUE GAP", "BOS", "CHOCH", "MSS"):
        assert word in text


def test_backtest_runs_on_synthetic_series():
    h1 = bullish_structure_candles(n=120, minutes=60)
    m30 = bullish_structure_candles(n=120, minutes=30)
    m15 = m15_buy_setup()
    report = run_backtest(h1, m30, m15, start_index=90)
    assert report.total >= 0
    payload = report.as_dict()
    assert "win_rate" in payload
    assert "expectancy" in payload
