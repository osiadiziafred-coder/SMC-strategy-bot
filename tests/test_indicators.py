import pandas as pd

from smc_bot.data import SyntheticConfig, generate_synthetic
from smc_bot.indicators import (
    Direction,
    detect_structure,
    find_fair_value_gaps,
    find_order_block,
    find_swing_points,
)


def _frame(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_find_swing_points_detects_obvious_peak():
    # A clear peak at index 3 and a clear trough at index 7.
    rows = [
        [1.0, 1.1, 0.9, 1.0],
        [1.0, 1.2, 0.95, 1.1],
        [1.1, 1.3, 1.0, 1.2],
        [1.2, 1.6, 1.1, 1.3],  # swing high (peak)
        [1.3, 1.4, 1.1, 1.2],
        [1.2, 1.3, 1.0, 1.1],
        [1.1, 1.2, 0.9, 1.0],
        [1.0, 1.05, 0.6, 0.7],  # swing low (trough)
        [0.7, 0.9, 0.65, 0.85],
        [0.85, 1.0, 0.8, 0.95],
        [0.95, 1.1, 0.9, 1.05],
    ]
    swings = find_swing_points(_frame(rows), lookback=3)
    kinds = {(s.index, s.kind) for s in swings}
    assert (3, "high") in kinds
    assert (7, "low") in kinds


def test_detect_structure_marks_bos_and_choch():
    df = generate_synthetic(SyntheticConfig(n=800, seed=11))
    events = detect_structure(df, lookback=3)
    assert events, "expected some structural breaks on synthetic data"
    kinds = {e.event for e in events}
    assert "BOS" in kinds or "CHoCH" in kinds
    # First event against no trend must be a CHoCH.
    assert events[0].event == "CHoCH"


def test_find_order_block_bullish_picks_last_down_candle():
    rows = [
        [1.0, 1.05, 0.98, 1.02],  # up
        [1.02, 1.06, 1.00, 1.01],  # down candle (close < open) -> bullish OB
        [1.01, 1.30, 1.00, 1.28],  # impulsive up move (the break)
    ]
    ob = find_order_block(_frame(rows), break_index=2, direction=Direction.BULLISH)
    assert ob is not None
    assert ob.index == 1
    assert ob.direction == Direction.BULLISH


def test_find_fair_value_gaps_detects_bullish_gap():
    rows = [
        [1.0, 1.05, 0.98, 1.02],
        [1.02, 1.20, 1.01, 1.18],
        [1.18, 1.25, 1.10, 1.22],  # low (1.10) > candle[0].high (1.05) -> bullish FVG
    ]
    gaps = find_fair_value_gaps(_frame(rows))
    assert any(g.direction == Direction.BULLISH and g.index == 2 for g in gaps)
