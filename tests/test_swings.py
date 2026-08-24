from datetime import datetime, timezone

from smc_robot.data.synthetic import candles_from_ohlc
from smc_robot.smc.swings import detect_swings
from smc_robot.models import SwingKind


def test_swing_high_and_low_require_n_bars_each_side():
    # Unique peak at index 4, unique trough at index 10. n=2.
    highs = [1, 2, 3, 4, 9, 4, 3, 2, 3, 2, 0, 2, 3, 4, 5]
    rows = []
    for i, high in enumerate(highs):
        close = high - 0.2
        rows.append((close - 0.1, high, 0 if i == 10 else close - 0.5, close))
    # Fix trough bar
    rows[10] = (1.0, 1.4, 0.0, 0.8)
    candles = candles_from_ohlc(rows, start=datetime(2024, 1, 1, tzinfo=timezone.utc), minutes=15)
    swings = detect_swings(candles, n=2)
    highs_found = [s for s in swings if s.kind == SwingKind.HIGH]
    lows_found = [s for s in swings if s.kind == SwingKind.LOW]
    assert any(s.index == 4 and s.price == 9 for s in highs_found)
    assert any(s.index == 10 and s.price == 0.0 for s in lows_found)
    # Right-edge bars cannot be swings (unconfirmed)
    assert all(s.index <= len(candles) - 3 for s in swings)
