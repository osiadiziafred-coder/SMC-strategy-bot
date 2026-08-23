from smc_robot.smc.liquidity import detect_liquidity_sweeps, detect_liquidity_zones
from smc_robot.smc.swings import detect_swings
from tests.helpers import mountain, ohlc, smc_buy_setup


def test_detects_bullish_sell_side_sweep():
    df = ohlc(
        [
            (12.0, 12.4, 11.6, 12.1),
            (12.1, 12.3, 11.5, 11.8),
            (11.8, 11.9, 11.2, 11.4),
            (11.4, 11.6, 10.8, 11.0),
            (11.0, 11.1, 8.0, 9.5),
            (9.5, 10.2, 9.3, 10.0),
            (10.0, 10.8, 9.8, 10.5),
            (10.5, 11.2, 10.3, 11.0),
            (11.0, 11.4, 7.4, 8.6),
        ]
    )
    swings = detect_swings(df, left=2, right=2)
    lows = [s for s in swings if s.kind == "low"]
    assert any(abs(s.price - 8.0) < 1e-9 for s in lows)
    sweeps = detect_liquidity_sweeps(df, left=2, right=2)
    bullish = [s for s in sweeps if s.direction == "bullish"]
    assert bullish
    assert bullish[0].swept_price == 8.0
    assert bullish[0].wick == 7.4
    assert bullish[0].kind == "sell_side"


def test_detects_bearish_buy_side_sweep():
    df = ohlc(
        [
            (10.0, 10.4, 9.6, 10.1),
            (10.1, 10.6, 9.9, 10.4),
            (10.4, 11.2, 10.2, 10.9),
            (10.9, 12.0, 10.8, 11.6),
            (11.6, 14.0, 11.4, 12.5),
            (12.5, 12.8, 12.0, 12.2),
            (12.2, 12.4, 11.6, 11.8),
            (11.8, 12.0, 11.2, 11.4),
            (11.4, 14.6, 11.0, 13.2),
        ]
    )
    sweeps = detect_liquidity_sweeps(df, left=2, right=2)
    bearish = [s for s in sweeps if s.direction == "bearish"]
    assert bearish
    assert bearish[0].swept_price == 14.0
    assert bearish[0].kind == "buy_side"


def test_smc_buy_setup_contains_a_sweep():
    df = smc_buy_setup()
    sweeps = detect_liquidity_sweeps(df)
    assert any(s.direction == "bullish" for s in sweeps)


def test_equal_lows_become_a_sell_side_liquidity_zone():
    rows = mountain(20, 28, 10, up=5, down=6)
    rows.extend(mountain(10, 18, 10.3, up=5, down=6))
    rows.extend(mountain(10.3, 16, 13, up=4, down=3))
    df = ohlc(rows)
    zones = detect_liquidity_zones(df, equal_tolerance=0.5)
    equals = [z for z in zones if z.kind == "equal" and z.direction == "bullish"]
    assert equals
    assert equals[0].side == "sell_side"


def test_swing_highs_are_buy_side_liquidity():
    df = smc_buy_setup()
    zones = detect_liquidity_zones(df)
    highs = [z for z in zones if z.direction == "bearish"]
    lows = [z for z in zones if z.direction == "bullish"]
    assert highs
    assert lows
