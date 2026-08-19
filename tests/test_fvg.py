from smc_robot.smc.fvg import detect_fvgs, price_in_fvg, unmitigated
from tests.helpers import ohlc


def test_bullish_fvg_three_candle_gap():
    # high[0] < low[2]  → bullish FVG on the middle candle.
    df = ohlc(
        [10, 12, 14, 13.5],
        highs=[10.4, 12.8, 14.4, 13.8],
        lows=[9.6, 11.5, 13.6, 13.2],
    )
    gaps = detect_fvgs(df, min_size=0.1, mark_mitigation=False)
    bull = [g for g in gaps if g.direction == "bullish"]
    assert bull
    gap = bull[0]
    assert gap.bottom == 10.4
    assert gap.top == 13.6
    assert price_in_fvg(12.0, gap)


def test_bearish_fvg_three_candle_gap():
    df = ohlc(
        [14, 12, 10, 10.2],
        highs=[14.4, 12.5, 10.3, 10.5],
        lows=[13.6, 11.2, 9.6, 9.9],
    )
    gaps = detect_fvgs(df, min_size=0.1, mark_mitigation=False)
    bear = [g for g in gaps if g.direction == "bearish"]
    assert bear
    assert bear[0].top == 13.6
    assert bear[0].bottom == 10.3


def test_fvg_mitigation_and_unmitigated_filter():
    df = ohlc(
        [10, 12, 14, 11, 10.2],
        highs=[10.4, 12.8, 14.4, 11.5, 10.6],
        lows=[9.6, 11.5, 13.6, 10.3, 9.8],
    )
    gaps = detect_fvgs(df, min_size=0.1, mark_mitigation=True)
    bull = [g for g in gaps if g.direction == "bullish"]
    assert bull[0].mitigated is True
    assert unmitigated(bull) == []
