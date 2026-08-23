from datetime import datetime, timezone

from smc_robot.config import NewsEvent, RobotConfig
from smc_robot.news import NewsFilter


def test_news_filter_allows_trading_by_default():
    now = datetime(2026, 8, 23, 12, 30, tzinfo=timezone.utc)
    cfg = RobotConfig(
        trade_news=True,
        news_events=(NewsEvent(time=now, title="US CPI", impact="high"),),
    )
    assert NewsFilter(cfg).is_blocked(now) is False


def test_news_filter_blocks_inside_blackout_when_enabled():
    now = datetime(2026, 8, 23, 12, 30, tzinfo=timezone.utc)
    cfg = RobotConfig(
        trade_news=False,
        news_blackout_minutes=30,
        news_events=(NewsEvent(time=now, title="US CPI", impact="high"),),
    )
    filt = NewsFilter(cfg)
    assert filt.is_blocked(now) is True
    assert filt.blocking_event(now).title == "US CPI"
    later = datetime(2026, 8, 23, 14, 0, tzinfo=timezone.utc)
    assert filt.is_blocked(later) is False


def test_medium_impact_is_ignored_by_default():
    now = datetime(2026, 8, 23, 12, 30, tzinfo=timezone.utc)
    cfg = RobotConfig(
        trade_news=False,
        news_events=(NewsEvent(time=now, title="speeches", impact="medium"),),
    )
    assert NewsFilter(cfg).is_blocked(now) is False
