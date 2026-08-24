from datetime import datetime, timezone

from smc_robot.data.synthetic import candles_from_ohlc
from smc_robot.models import Direction, EventType
from smc_robot.smc.fvg import detect_fvgs, unfilled_fvgs
from smc_robot.smc.structure import detect_structure_events
from smc_robot.smc.liquidity import LiquidityPool, detect_sweeps
from smc_robot.models import SwingKind


def test_bullish_and_bearish_fvg_three_candle_rule():
    rows = [
        (100.0, 101.0, 99.5, 100.4),
        (100.5, 106.0, 100.4, 105.5),
        (105.6, 107.0, 103.5, 106.2),  # bullish FVG: 103.5 > 101.0
        (106.0, 106.5, 105.8, 106.1),
        (106.2, 106.4, 100.8, 101.2),  # fills the gap
    ]
    candles = candles_from_ohlc(rows, datetime(2024, 1, 1, tzinfo=timezone.utc), 15)
    gaps = detect_fvgs(candles, min_atr_mult=0.0, atr_period=14)
    bullish = [g for g in gaps if g.direction == Direction.BUY]
    assert bullish
    assert bullish[0].low == 101.0
    assert bullish[0].high == 103.5
    live = unfilled_fvgs(candles, gaps)
    assert bullish[0].index not in {g.index for g in live}

    bear_rows = [
        (110.0, 110.5, 109.0, 109.2),
        (109.1, 109.3, 104.0, 104.4),
        (104.3, 105.0, 103.8, 104.0),  # bearish FVG: 105.0 < 109.0
    ]
    bear = candles_from_ohlc(bear_rows, datetime(2024, 1, 1, tzinfo=timezone.utc), 15)
    bear_gaps = detect_fvgs(bear, min_atr_mult=0.0, atr_period=14)
    assert any(g.direction == Direction.SELL and g.high == 109.0 and g.low == 105.0 for g in bear_gaps)


def test_liquidity_sweep_requires_wick_through_and_close_back():
    pool = LiquidityPool(kind=SwingKind.LOW, price=100.0, index=2, equal=False, members=1)
    rows = [
        (101.0, 102.0, 100.5, 101.2),
        (101.2, 101.8, 100.8, 101.0),
        (101.0, 101.5, 100.2, 101.1),  # pool index, not a sweep of itself
        (101.0, 101.4, 99.2, 99.7),    # wick below 100, close still below → not a sweep
        (100.7, 101.8, 99.4, 101.2),   # wick below 100, close back above → sweep
    ]
    candles = candles_from_ohlc(rows, datetime(2024, 1, 1, tzinfo=timezone.utc), 15)
    sweeps = detect_sweeps(candles, [pool])
    assert len(sweeps) == 1
    assert sweeps[0].index == 4
    assert sweeps[0].direction == Direction.BUY
    assert sweeps[0].wick == 99.4


def test_bos_is_close_beyond_internal_swing_in_trend_direction():
    from tests.factories import bullish_structure_candles

    candles = bullish_structure_candles(n=96, minutes=15)
    last = candles[-1]
    top = max(c.high for c in candles[:-1]) + 1.5
    candles[-1] = last.model_copy(
        update={"open": last.close, "high": top + 0.2, "close": top, "low": min(last.low, last.close - 0.1)}
    )
    events, trend, _, _ = detect_structure_events(candles, internal_n=2, external_n=5)
    assert trend == trend.BULLISH or trend.value == "BULLISH"
    bos_or_mss = [e for e in events if e.event_type in (EventType.BOS, EventType.MSS, EventType.CHOCH)]
    assert bos_or_mss, "expected at least one structure break on a trending series"
    assert any(e.direction == Direction.BUY for e in bos_or_mss)
