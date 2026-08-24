from datetime import datetime, timezone

from smc_robot.models import Direction, EventType
from smc_robot.smc.structure import detect_structure_events
from tests.factories import structure_from_swings


def test_mss_fires_on_close_above_external_high_in_downtrend():
    candles = structure_from_swings(
        [
            (8, "H", 2050.0),
            (22, "L", 2026.0),
            (36, "H", 2042.0),
            (50, "L", 2014.0),
            (64, "H", 2034.0),
            (78, "L", 2002.0),
        ],
        n_bars=96,
        minutes=15,
    )
    events, trend, _, external = detect_structure_events(candles, internal_n=2, external_n=5)
    assert trend.value == "BEARISH"
    last = candles[-1]
    level = max(s.price for s in external if s.kind.value == "HIGH")
    candles[-1] = last.model_copy(
        update={"open": last.close, "close": level + 1.0, "high": level + 1.4, "low": min(last.low, last.close)}
    )
    events, _, _, _ = detect_structure_events(candles, internal_n=2, external_n=5)
    mss = [e for e in events if e.event_type == EventType.MSS and e.direction == Direction.BUY]
    assert mss, "expected bullish MSS after closing through the external high"
    assert mss[-1].index == len(candles) - 1
