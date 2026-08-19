from smc_robot.smc.structure import current_bias, detect_structure
from tests.helpers import ohlc


def _impulse_up() -> list[float]:
    # Slow dip (swing low), rally through prior high (BOS), then dump through
    # the last swing low (CHoCH / MSS).
    return [
        100, 99, 97, 99, 101, 103, 105, 108, 106, 104,
        107, 110, 113, 116, 114, 112, 109, 105, 100, 96,
        94, 92, 90, 88, 86,
    ]


def test_bullish_bos_then_bearish_choch_or_mss():
    df = ohlc(_impulse_up(), wick=0.4)
    events = detect_structure(df, swing_length=2, close_break=True, displacement_body_atr=0.8)
    kinds = [e.kind for e in events]
    directions = [e.direction for e in events]
    assert "BOS" in kinds
    assert any(k in {"CHOCH", "MSS"} for k in kinds)
    assert "bullish" in directions
    assert "bearish" in directions


def test_mss_is_choch_with_displacement():
    df = ohlc(_impulse_up(), wick=0.4)
    events = detect_structure(df, swing_length=2, close_break=True, displacement_body_atr=0.5)
    reversals = [e for e in events if e.kind in {"CHOCH", "MSS"}]
    assert reversals
    for event in reversals:
        if event.displacement:
            assert event.kind == "MSS"
        else:
            assert event.kind == "CHOCH"


def test_bias_follows_last_event():
    df = ohlc(_impulse_up(), wick=0.4)
    events = detect_structure(df, swing_length=2)
    assert current_bias(events) == events[-1].direction
    assert current_bias([]) is None
