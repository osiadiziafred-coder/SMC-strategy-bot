from smc_robot.smc.order_blocks import detect_order_blocks, price_in_ob
from smc_robot.smc.structure import detect_structure
from tests.helpers import ohlc


def test_bullish_order_block_is_last_down_candle_before_break():
    # A down candle, then a strong rally that breaks structure.
    closes = [
        100, 101, 99, 98, 97, 99, 102, 105, 108, 111,
        109, 107, 110, 114, 118, 122,
    ]
    opens = [
        99.5, 100.2, 100.8, 99.1, 98.2, 97.2, 99.4, 102.2, 105.2, 108.2,
        110.5, 108.8, 107.4, 110.3, 114.2, 118.2,
    ]
    df = ohlc(closes, opens=opens, wick=0.35)
    events = detect_structure(df, swing_length=2, displacement_body_atr=0.6)
    blocks = detect_order_blocks(df, events=events, lookback=12)
    bull = [b for b in blocks if b.direction == "bullish"]
    assert bull
    block = bull[0]
    candle = df.iloc[block.index]
    assert candle["close"] < candle["open"]
    assert price_in_ob((block.top + block.bottom) / 2, block)
