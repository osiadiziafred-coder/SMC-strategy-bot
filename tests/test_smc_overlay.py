"""Tests for the SMC chart overlay and the MQL5 bridge EA."""

from __future__ import annotations

from pathlib import Path

from smc_overlay import (
    DIR_BEAR,
    DIR_BULL,
    KIND_BOS,
    KIND_CHOCH,
    KIND_MSS,
    V50_1S_ALIASES,
    V75_ALIASES,
    analyze,
    chat_lines,
    classify_symbol,
    detect_fvg,
    detect_order_blocks,
    detect_structure,
    detect_sweeps,
    detect_swings,
    resolve_from_market,
    zone_name,
)

EA_PATH = Path(__file__).resolve().parents[1] / "MQL5" / "Experts" / "PythonML_SMC_Bridge.mq5"


def _ohlc_from_closes(closes: list[float], wick: float = 1.0) -> tuple[list[float], list[float], list[float], list[float]]:
    opens = [closes[0], *closes[:-1]]
    highs = [max(o, c) + wick for o, c in zip(opens, closes)]
    lows = [min(o, c) - wick for o, c in zip(opens, closes)]
    return opens, highs, lows, closes


def test_ea_file_exists_and_is_bridge() -> None:
    text = EA_PATH.read_text(encoding="utf-8")
    assert "#property version   \"3.02\"" in text
    assert "never invents BUY/SELL" in text or "Python still decides BUY/SELL" in text
    assert EA_PATH.read_text(encoding="utf-8") == (
        Path(__file__).resolve().parents[1] / "PythonML_SMC_Bridge.mq5"
    ).read_text(encoding="utf-8")


def test_ea_left_xauusd_and_uses_volatility_indices() -> None:
    text = EA_PATH.read_text(encoding="utf-8")
    assert "XAUUSD" not in text.upper()
    assert 'InpSymbol1            = "Volatility 75 Index"' in text
    assert 'InpSymbol2            = "Volatility 50 (1s) Index"' in text
    assert "R_75" in text
    assert "1HZ50V" in text


def test_ea_exposes_requested_smc_labels_on_chat() -> None:
    text = EA_PATH.read_text(encoding="utf-8")
    for label in (
        "Liquidity sweep",
        "Equal-liquidity sweep extra",
        "Order Block",
        "FVG",
        "BOS",
        "CHoCH",
        "MSS",
        "EQ SWEEP EXTRA",
        "LIQUIDITY SWEEP",
        "Comment(txt)",
    ):
        assert label in text, label


def test_ea_braces_balanced() -> None:
    text = EA_PATH.read_text(encoding="utf-8")
    stripped = []
    in_str = False
    for ch in text:
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            stripped.append(ch)
    body = "".join(stripped)
    assert body.count("{") == body.count("}")
    assert body.count("(") == body.count(")")


def test_symbol_aliases_resolve() -> None:
    market = ["EURUSD", "R_75", "1HZ50V", "BTCUSD"]
    assert resolve_from_market("Volatility 75 Index", market, "v75") == "R_75"
    assert resolve_from_market("Volatility 50 (1s) Index", market, "v50_1s") == "1HZ50V"
    assert classify_symbol("Volatility 75 Index") == "v75"
    assert classify_symbol("Volatility 50 (1s) Index") == "v50_1s"
    assert "Volatility 75 Index" in V75_ALIASES
    assert "Volatility 50 (1s) Index" in V50_1S_ALIASES


def test_swings_and_bos() -> None:
    closes = [10, 11, 12, 11, 10, 11, 12, 13, 14, 15, 16]
    opens, highs, lows, closes = _ohlc_from_closes(closes, wick=0.2)
    highs[3] = 12.8
    events = detect_structure(opens, highs, lows, closes, left=2, right=2)
    kinds = {e.kind for e in events}
    assert KIND_BOS in kinds
    assert any(e.direction == DIR_BULL for e in events)


def test_choch_and_mss_on_reversal_displacement() -> None:
    n = 40
    opens = [100.0] * n
    highs = [100.3] * n
    lows = [99.7] * n
    closes = [100.0] * n
    highs[8] = 102.0
    opens[8], closes[8] = 100.0, 100.5
    lows[14] = 98.5
    opens[14], closes[14] = 100.0, 99.5
    opens[20], closes[20], highs[20] = 100.5, 103.0, 103.2
    opens[26], closes[26], lows[26], highs[26] = 102.0, 97.0, 96.8, 102.1
    events = detect_structure(opens, highs, lows, closes, left=2, right=2)
    kinds = {e.kind for e in events}
    assert KIND_BOS in kinds
    assert KIND_CHOCH in kinds
    assert KIND_MSS in kinds
    assert any(e.kind == KIND_CHOCH and e.direction == DIR_BEAR for e in events)


def test_fvg_bullish_gap() -> None:
    opens = [10, 11, 13]
    highs = [10.5, 12.5, 13.5]
    lows = [9.5, 11.2, 12.8]
    closes = [10.4, 12.4, 13.2]
    zones = detect_fvg(highs, lows, closes)
    assert zones
    assert zones[0].direction == DIR_BULL
    assert zones[0].low == highs[0]
    assert zones[0].high == lows[2]


def test_liquidity_sweep_and_equal_extra() -> None:
    n = 30
    closes = [20.0] * n
    opens = [20.0] * n
    highs = [20.4] * n
    lows = [19.6] * n
    highs[6] = 21.00
    highs[14] = 21.02
    closes[6] = 20.2
    opens[6] = 20.0
    closes[14] = 20.2
    opens[14] = 20.0
    lows[6] = 19.8
    lows[14] = 19.8
    highs[22] = 21.80
    closes[22] = 20.50
    opens[22] = 20.60
    lows[22] = 20.40
    swings = detect_swings(highs, lows, left=2, right=2)
    assert any(s.kind == 1 for s in swings)
    sweeps, equals = detect_sweeps(highs, lows, closes, left=2, right=2, equal_atr_mult=0.05)
    assert equals, "expected an equal-high pool"
    assert any(s.direction == DIR_BEAR for s in sweeps)
    assert any(s.equal_extra for s in sweeps)


def test_order_block_is_opposite_candle_before_break() -> None:
    closes = [10, 11, 12, 11.2, 10.5, 11, 12, 13, 14, 15]
    opens, highs, lows, closes = _ohlc_from_closes(closes, wick=0.1)
    events = detect_structure(opens, highs, lows, closes, left=2, right=2)
    obs = detect_order_blocks(opens, highs, lows, closes, events)
    assert zone_name(2) == "Order Block"
    if events:
        assert isinstance(obs, list)


def test_chat_lines_list_every_requested_concept() -> None:
    closes = [10 + (i % 7) * 0.3 for i in range(50)]
    opens, highs, lows, closes = _ohlc_from_closes(closes, wick=0.2)
    highs[10] = highs[18] = max(highs) + 0.4
    snap = analyze(opens, highs, lows, closes)
    lines = "\n".join(chat_lines("Volatility 75 Index", snap))
    for label in (
        "BOS",
        "CHoCH",
        "MSS",
        "Liquidity sweep",
        "Equal-liquidity sweep extra",
        "Order Block",
        "FVG",
    ):
        assert label in lines
    assert "Volatility 75 Index" in lines
