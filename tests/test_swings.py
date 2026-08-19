from smc_robot.smc.swings import detect_swings
from tests.helpers import ohlc


def test_detects_unique_swing_low_and_high():
    # length=2 window of 5 bars. Index 2 is the unique lowest, index 7 unique highest.
    closes = [10, 9, 7, 9, 10, 11, 12, 14, 12, 11, 10]
    lows = [9.7, 8.7, 6.4, 8.7, 9.7, 10.7, 11.7, 13.7, 11.7, 10.7, 9.7]
    highs = [10.3, 9.3, 7.3, 9.3, 10.3, 11.3, 12.3, 14.6, 12.3, 11.3, 10.3]
    df = ohlc(closes, highs=highs, lows=lows)
    swings = detect_swings(df, length=2)
    lows_found = [s for s in swings if s.kind == "low"]
    highs_found = [s for s in swings if s.kind == "high"]
    assert any(s.index == 2 and s.price == 6.4 for s in lows_found)
    assert any(s.index == 7 and s.price == 14.6 for s in highs_found)


def test_equal_highs_are_not_both_swings():
    highs = [5, 6, 8, 8, 6, 5, 4]
    lows = [4, 5, 7, 7, 5, 4, 3]
    closes = [4.5, 5.5, 7.5, 7.5, 5.5, 4.5, 3.5]
    df = ohlc(closes, highs=highs, lows=lows)
    highs_found = [s for s in detect_swings(df, length=2) if s.kind == "high"]
    assert len(highs_found) <= 1
