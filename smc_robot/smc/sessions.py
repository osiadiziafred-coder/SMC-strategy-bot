"""Session tagging in UTC. Filtering is optional and config-driven."""

from __future__ import annotations

from datetime import datetime, timezone

from smc_robot.config import SessionConfig
from smc_robot.models import SessionName


def classify_session(stamp: datetime, cfg: SessionConfig | None = None) -> SessionName:
    cfg = cfg or SessionConfig()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    hour = stamp.astimezone(timezone.utc).hour
    london = _in_hours(hour, cfg.london)
    ny = _in_hours(hour, cfg.new_york)
    asian = _in_hours(hour, cfg.asian)
    if london and ny:
        return SessionName.OVERLAP
    if london:
        return SessionName.LONDON
    if ny:
        return SessionName.NEW_YORK
    if asian:
        return SessionName.ASIAN
    return SessionName.OFF


def session_allowed(stamp: datetime, cfg: SessionConfig) -> tuple[bool, str]:
    name = classify_session(stamp, cfg)
    if not cfg.enabled:
        return True, name.value
    if name.value not in cfg.allowed and name != SessionName.OVERLAP:
        return False, f"session_blocked_{name.value}"
    if name == SessionName.OVERLAP and "LONDON_NY_OVERLAP" not in cfg.allowed:
        if "LONDON" not in cfg.allowed and "NEW_YORK" not in cfg.allowed:
            return False, f"session_blocked_{name.value}"
    return True, name.value


def _in_hours(hour: int, window: tuple[int, int]) -> bool:
    start, end = window
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end
