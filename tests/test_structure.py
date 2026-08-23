from smc_robot.smc.structure import detect_structure, last_bias
from smc_robot.smc.swings import detect_swings
from tests.helpers import mountain, ohlc


def test_fractal_swing_high_and_low():
    df = ohlc(mountain(10, 20, 12, up=5, down=5) + mountain(12, 18, 14, up=4, down=4))
    swings = detect_swings(df, left=2, right=2)
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]
    assert highs
    assert lows
    assert max(s.price for s in highs) >= 20


def test_bos_then_choch_and_optional_mss():
    rows = mountain(100, 112, 104, up=6, down=6)
    rows.extend(mountain(104, 118, 96, up=6, down=8))
    df = ohlc(rows)
    events = detect_structure(df, left=2, right=2)
    kinds = {e.kind for e in events}
    assert "BOS" in kinds
    assert "CHOCH" in kinds
    choch = [e for e in events if e.kind == "CHOCH"]
    assert choch
    assert last_bias(events) in {"bullish", "bearish"}
