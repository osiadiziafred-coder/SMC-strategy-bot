"""Configurable economic-news awareness. No single behavior is hard-coded."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from smc_robot.config import NewsConfig
from smc_robot.models import NewsMode


def load_calendar(path: str | Path) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict] = []
    with target.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            raw = (row.get("time") or "").strip()
            if not raw:
                continue
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            rows.append(
                {
                    "time": stamp,
                    "impact": (row.get("impact") or "low").strip().lower(),
                    "currency": (row.get("currency") or "").strip().upper(),
                    "title": (row.get("title") or "").strip(),
                }
            )
    return rows


def news_block_reason(
    now: datetime,
    cfg: NewsConfig,
    events: list[dict] | None = None,
) -> str:
    mode = NewsMode(cfg.mode)
    if mode == NewsMode.ALLOW:
        return ""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    calendar = events if events is not None else load_calendar(cfg.calendar_path)
    if not calendar:
        return ""
    before = timedelta(minutes=cfg.minutes_before)
    after = timedelta(minutes=cfg.minutes_after)
    for event in calendar:
        if cfg.high_impact_only and event["impact"] != "high":
            continue
        when: datetime = event["time"]
        if mode == NewsMode.AVOID_HIGH:
            if abs((now - when).total_seconds()) <= max(before, after).total_seconds():
                return f"news_high_impact_{event['title'] or when.isoformat()}"
        elif mode == NewsMode.WINDOW:
            if when - before <= now <= when + after:
                return f"news_window_{event['title'] or when.isoformat()}"
        elif mode == NewsMode.AFTER_ONLY:
            if now < when + after:
                return f"news_wait_until_after_{when.isoformat()}"
    return ""
