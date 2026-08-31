from datetime import datetime, timezone
from pathlib import Path

from smc_robot.backtest import run_backtest
from smc_robot.bridge import FileBridge, Mql5PaperExecutor
from smc_robot.config import NewsConfig, Settings
from smc_robot.data.setups import bullish_structure_candles, m15_buy_setup
from smc_robot.models import Direction, ScoreBreakdown, SetupGrade, Signal, TradePlan, Trend, SwingKind
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
    through = NewsConfig(trade_through_news=True, mode="avoid_high")
    assert news_block_reason(now, through, events) == ""
    allow = NewsConfig(trade_through_news=False, mode="allow")
    assert "news" in news_block_reason(now, allow, events)
    avoid = NewsConfig(
        trade_through_news=False, mode="avoid_high", minutes_before=30, minutes_after=30
    )
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


def _test_signal(sid: str) -> Signal:
    plan = TradePlan(
        direction=Direction.BUY,
        entry=2000.0,
        sl=1990.0,
        tp=2020.0,
        risk=10.0,
        lots=0.02,
        sl_source="test",
    )
    score = ScoreBreakdown(total=82, rule_score=80, ml_probability=0.74, grade=SetupGrade.A)
    return Signal(
        signal_id=sid,
        direction=Direction.BUY,
        plan=plan,
        score=score,
        h1_trend=Trend.BULLISH,
        m30_trend=Trend.BULLISH,
        m15_trend=Trend.BULLISH,
        reason="spec_test",
        grade=SetupGrade.A,
    )


def test_bridge_writes_command_file(tmp_path: Path):
    settings = Settings()
    settings.bridge.directory = str(tmp_path)
    bridge = FileBridge(settings)
    bridge.heartbeat()
    assert (tmp_path / "command.json").exists()
    assert "HEARTBEAT" in (tmp_path / "command.json").read_text(encoding="utf-8")


def test_stale_heartbeat_rejects_new_buy(tmp_path: Path):
    settings = Settings()
    settings.bridge.directory = str(tmp_path)
    bridge = FileBridge(settings)
    executor = Mql5PaperExecutor(settings)
    bridge.send_signal(_test_signal("no-hb"))
    result = executor.process_once()["last_result"]
    assert result["ok"] is False
    assert result["error"] == "python_disconnected"


def test_wait_for_result_after_heartbeat(tmp_path: Path):
    settings = Settings()
    settings.bridge.directory = str(tmp_path)
    bridge = FileBridge(settings)
    executor = Mql5PaperExecutor(settings, bid=1999.5, ask=2000.0)
    bridge.heartbeat()
    executor.process_once()
    sid = bridge.send_signal(_test_signal("fill-1"))
    executor.process_once()
    result = bridge.wait_for_result(sid, timeout=0.5)
    assert result["ok"] is True
    assert result["error"] == "filled"
    text = (tmp_path / "command.json").read_text(encoding="utf-8")
    assert "smc_score" in text
    assert "spec_test" in text
    assert "trail_enabled" in text
    status = bridge.read_status()
    assert "trail_on" in status


def test_modify_never_loosens_sl(tmp_path: Path):
    settings = Settings()
    settings.bridge.directory = str(tmp_path)
    bridge = FileBridge(settings)
    executor = Mql5PaperExecutor(settings, bid=1999.5, ask=2000.0)
    bridge.heartbeat()
    executor.process_once()
    sid = bridge.send_signal(_test_signal("fill-2"))
    filled = executor.process_once()["last_result"]
    ticket = int(filled["ticket"])
    bridge.send_modify(ticket, sl=1980.0, tp=2020.0, signal_id=sid)
    loosened = executor.process_once()["last_result"]
    assert loosened["ok"] is False
    assert loosened["error"] == "sl_would_loosen"


def test_default_lot_mode_is_balance_step():
    assert Settings().risk.sizing_mode == "balance_step"


def test_none_command_and_boolean_trail_flag(tmp_path: Path):
    settings = Settings()
    settings.bridge.directory = str(tmp_path)
    settings.risk.trail_enabled = True
    bridge = FileBridge(settings)
    none_id = bridge.send_none("weak_setup")
    assert none_id
    text = (tmp_path / "command.json").read_text(encoding="utf-8")
    assert '"action": "NONE"' in text
    executor = Mql5PaperExecutor(settings)
    result = executor.process_once()["last_result"]
    assert result["error"] == "heartbeat"
    sid = bridge.send_signal(_test_signal("bool-trail"))
    assert sid
    payload = (tmp_path / "command.json").read_text(encoding="utf-8")
    assert "true" in payload
    assert "trail_enabled" in payload


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
    assert "largest_win" in payload
    assert "max_consecutive_wins" in payload
