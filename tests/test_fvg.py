from smc_robot.smc.fvg import detect_fvg, price_in_zone, unmitigated
from tests.helpers import ohlc


def test_detects_bullish_fvg():
    df = ohlc(
        [
            (10.0, 11.0, 9.0, 10.5),
            (12.0, 20.0, 11.5, 19.0),
            (19.0, 22.0, 18.0, 21.0),
        ]
    )
    zones = detect_fvg(df)
    assert len(zones) == 1
    zone = zones[0]
    assert zone.direction == "bullish"
    assert zone.kind == "FVG"
    assert zone.low == 11.0
    assert zone.high == 18.0
    assert zone.mitigated is False


def test_detects_bearish_fvg():
    df = ohlc(
        [
            (20.0, 21.0, 19.0, 20.5),
            (18.0, 18.5, 10.0, 11.0),
            (11.0, 12.0, 9.0, 10.0),
        ]
    )
    zones = detect_fvg(df)
    assert len(zones) == 1
    assert zones[0].direction == "bearish"
    assert zones[0].high == 19.0
    assert zones[0].low == 12.0


def test_fvg_mitigation_and_tap():
    df = ohlc(
        [
            (10.0, 11.0, 9.0, 10.5),
            (12.0, 20.0, 11.5, 19.0),
            (19.0, 22.0, 18.0, 21.0),
            (17.0, 18.0, 16.5, 17.5),
        ]
    )
    zones = detect_fvg(df)
    assert zones[0].mitigated is False
    assert price_in_zone(16.5, 18.0, zones[0])
    assert unmitigated(zones, "bullish")

    closed_through = ohlc(
        [
            (10.0, 11.0, 9.0, 10.5),
            (12.0, 20.0, 11.5, 19.0),
            (19.0, 22.0, 18.0, 21.0),
            (10.0, 12.0, 9.0, 10.0),
        ]
    )
    assert detect_fvg(closed_through)[0].mitigated is True
    assert unmitigated(detect_fvg(closed_through)) == []
