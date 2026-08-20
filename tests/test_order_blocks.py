from smc_robot.smc.order_blocks import detect_order_blocks
from smc_robot.smc.structure import detect_structure
from tests.helpers import smc_buy_setup


def test_bullish_order_block_is_last_down_candle_before_bos():
    df = smc_buy_setup()
    events = detect_structure(df, left=2, right=2)
    assert events
    obs = detect_order_blocks(df, events, lookback=12)
    bullish = [z for z in obs if z.direction == "bullish"]
    assert bullish
    assert bullish[0].kind == "OB"
    assert bullish[0].low <= bullish[0].high
    bearish_candles = df[df["close"] < df["open"]]
    assert not bearish_candles.empty
