from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from smc_robot.config import NewsEvent, RobotConfig, _parse_news_events


class NewsFilter:
    """Optional high-impact news pause.

    Default config keeps trading through news (`trade_news=True`) because
    XAUUSDm can still print valid SMC setups around releases. Set
    `trade_news=False` to block new entries inside the blackout window.
    Open positions are never force-closed by this filter.
    """

    def __init__(self, config: RobotConfig | None = None) -> None:
        self.config = config or RobotConfig()
        self.events: list[NewsEvent] = list(self.config.news_events)
        if self.config.news_calendar_path:
            self.events.extend(self._load_calendar(Path(self.config.news_calendar_path)))

    def is_blocked(self, now: datetime | None = None) -> bool:
        if self.config.trade_news:
            return False
        when = now or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        window = self.config.news_blackout_minutes * 60
        for event in self.events:
            if event.impact not in self.config.news_block_impacts:
                continue
            event_time = event.time
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            if abs((when - event_time).total_seconds()) <= window:
                return True
        return False

    def blocking_event(self, now: datetime | None = None) -> NewsEvent | None:
        if self.config.trade_news:
            return None
        when = now or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        window = self.config.news_blackout_minutes * 60
        for event in self.events:
            if event.impact not in self.config.news_block_impacts:
                continue
            event_time = event.time
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            if abs((when - event_time).total_seconds()) <= window:
                return event
        return None

    @staticmethod
    def _load_calendar(path: Path) -> list[NewsEvent]:
        if not path.exists():
            return []
        import csv

        rows = []
        with path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(
                    {
                        "time": row.get("time") or row.get("datetime"),
                        "title": row.get("title") or row.get("event") or "",
                        "impact": (row.get("impact") or "high").lower(),
                    }
                )
        return list(_parse_news_events(rows))
