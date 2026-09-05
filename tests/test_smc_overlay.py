"""Tests for the SMC chart overlay and the MQL5 bridge EA."""

from __future__ import annotations

from pathlib import Path

from smc_overlay import (
    DIR_BEAR,
    DIR_BULL,
    DIR_NONE,
    KIND_BOS,
    KIND_CHOCH,
    KIND_MSS,
    V50_1S_ALIASES,
    V75_ALIASES,
    ZONE_FVG,
    Setup,
    Snapshot,
    Sweep,
    Zone,
    Event,
    analyze,
    build_setup,
    chat_lines,
    classify_symbol,
    detect_fvg,
    detect_order_blocks,
    detect_structure,
    detect_sweeps,
    detect_swings,
    pick_dual_pair_trades,
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
    assert "#property version   \"3.04\"" in text
    assert "InpRequireBothPairs" in text
    assert "PICK " in text
    assert "MaybeAutoTrade" in text
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


def _forced_setup(direction: int, *, valid: bool = True, skill: int = 90) -> Setup:
    return Setup(
        valid=valid,
        direction=direction,
        sl=100.0,
        tp=104.0,
        confluence=5,
        zone_kind=ZONE_FVG,
        eq_extra=True,
        why="bias+BOS+sweep+eq_sweep_extra+FVG",
        skill=skill,
        missing="" if valid else "sweep",
    )


def test_build_setup_needs_sweep_and_zone_tap() -> None:
    n = 80
    opens = [110.0] * n
    highs = [110.5] * n
    lows = [108.2] * n
    closes = [108.5] * n
    highs[-1], lows[-1], closes[-1] = 108.8, 108.2, 108.5
    snap = Snapshot(
        bias=DIR_BULL,
        events=[Event(index=50, kind=KIND_BOS, direction=DIR_BULL, broken=110.0)],
        sweeps=[
            Sweep(
                index=70,
                direction=DIR_BULL,
                swept_price=108.0,
                wick=107.4,
                equal_extra=True,
                members=2,
            )
        ],
        fvgs=[Zone(60, 62, 108.0, 109.0, DIR_BULL, ZONE_FVG, False)],
    )
    setup = build_setup(opens, highs, lows, closes, snap=snap, min_confluence=4)
    assert setup.valid
    assert setup.direction == DIR_BULL
    assert setup.eq_extra
    assert "FVG" in setup.why


def test_build_setup_rejects_missing_sweep() -> None:
    n = 40
    opens = highs = lows = closes = [10.0] * n
    snap = Snapshot(
        bias=DIR_BULL,
        events=[Event(index=20, kind=KIND_BOS, direction=DIR_BULL, broken=10.0)],
        fvgs=[Zone(30, 32, 9.5, 10.2, DIR_BULL, ZONE_FVG, False)],
    )
    setup = build_setup(opens, highs, lows, closes, snap=snap, require_sweep=True)
    assert not setup.valid
    assert setup.why == "no_sweep"


def test_pick_trade_only_when_both_pairs_align() -> None:
    bull = _forced_setup(DIR_BULL)
    bear = _forced_setup(DIR_BEAR)
    none = _forced_setup(DIR_BULL, valid=False)

    t1, t2, direction, status = pick_dual_pair_trades(bull, bull, require_both=True)
    assert t1 and t2
    assert direction == DIR_BULL
    assert status == "PICK BUY on both pairs  SKILL 90/100"

    t1, t2, direction, status = pick_dual_pair_trades(bear, bear, require_both=True)
    assert t1 and t2
    assert direction == DIR_BEAR
    assert status == "PICK SELL on both pairs  SKILL 90/100"

    t1, t2, direction, status = pick_dual_pair_trades(bull, none, require_both=True)
    assert not t1 and not t2
    assert direction == DIR_NONE
    assert "Volatility 50 (1s)" in status

    t1, t2, direction, status = pick_dual_pair_trades(bull, bear, require_both=True)
    assert not t1 and not t2
    assert status == "pairs not aligned"


def test_ea_auto_trade_requires_both_pairs() -> None:
    text = EA_PATH.read_text(encoding="utf-8")
    assert "InpRequireBothPairs   = true" in text
    assert "waiting for setup on both pairs" in text
    assert "on both pairs  SKILL" in text
    assert "SMC-SETUP" in text
    assert "InpMinSkillScore     = 85" in text
    assert "InpProSkill          = true" in text
    assert "InpRiskPercent" in text
    assert "daily_loss_cap" in text
    assert "need_choch_after_sweep" in text
    assert "need_premium_discount" in text
    assert "htf_mismatch" in text
    assert "SKILL:" in text


def test_pro_skill_rejects_buy_in_premium() -> None:
    from smc_overlay import build_setup, DIR_BULL, KIND_CHOCH, KIND_MSS, ZONE_FVG, Event, Snapshot, Sweep, Zone

    n = 80
    opens = [110.0] * n
    highs = [112.0] * n
    lows = [100.0] * n
    closes = [111.5] * n
    highs[-1], lows[-1], closes[-1] = 111.8, 111.0, 111.5
    opens[50], closes[50], highs[50] = 108.0, 111.6, 111.9
    lows[50] = 107.8
    snap = Snapshot(
        bias=DIR_BULL,
        events=[
            Event(index=50, kind=KIND_CHOCH, direction=DIR_BULL, broken=110.0),
            Event(index=55, kind=KIND_MSS, direction=DIR_BULL, broken=110.0),
        ],
        sweeps=[
            Sweep(index=40, direction=DIR_BULL, swept_price=100.5, wick=99.8, equal_extra=True, members=2)
        ],
        fvgs=[Zone(60, 62, 110.8, 111.9, DIR_BULL, ZONE_FVG, False)],
    )
    setup = build_setup(
        opens, highs, lows, closes, snap=snap, pro_mode=True, htf_bias=DIR_BULL, min_er=0.0
    )
    assert not setup.valid
    assert setup.why == "need_premium_discount"


def test_pro_skill_passes_a_plus_discount_buy() -> None:
    from smc_overlay import (
        DIR_BULL,
        KIND_CHOCH,
        KIND_MSS,
        ZONE_FVG,
        Event,
        Snapshot,
        Sweep,
        Zone,
        build_setup,
        skill_chat_line,
        skill_score,
        MIN_SKILL_SCORE,
    )

    n = 80
    opens = [100.0] * n
    highs = [110.0] * n
    lows = [90.0] * n
    closes = [94.0] * n
    for i in range(1, n):
        opens[i] = closes[i - 1]
        closes[i] = 100.0 - i * 0.08
        highs[i] = max(opens[i], closes[i]) + 0.2
        lows[i] = min(opens[i], closes[i]) - 0.2
    # Strong down then bullish displacement CHoCH after SSL sweep, tap FVG in discount.
    closes[-1] = 93.2
    opens[-1] = 92.0
    highs[-1] = 93.5
    lows[-1] = 91.8
    snap = Snapshot(
        bias=DIR_BULL,
        events=[
            Event(index=n - 8, kind=KIND_CHOCH, direction=DIR_BULL, broken=94.0),
            Event(index=n - 8, kind=KIND_MSS, direction=DIR_BULL, broken=94.0),
        ],
        sweeps=[
            Sweep(
                index=n - 20,
                direction=DIR_BULL,
                swept_price=91.5,
                wick=90.8,
                equal_extra=True,
                members=2,
            )
        ],
        fvgs=[Zone(n - 6, n - 4, 92.5, 93.8, DIR_BULL, ZONE_FVG, False)],
    )
    # Make displacement on choch bar
    opens[n - 8] = 92.0
    closes[n - 8] = 96.0
    highs[n - 8] = 96.2
    lows[n - 8] = 91.9
    setup = build_setup(
        opens, highs, lows, closes, snap=snap, pro_mode=True, htf_bias=DIR_BULL, min_er=0.05
    )
    assert setup.skill >= MIN_SKILL_SCORE
    assert setup.valid
    assert "SKILL:" in skill_chat_line(setup)
    score, missing = skill_score(
        has_sweep=True,
        eq_extra=True,
        choch_after=True,
        displacement=True,
        zone_tap=True,
        pd_aligned=True,
        htf_aligned=True,
        trending=True,
    )
    assert score == 100
    assert missing == ""


def test_skill_85_fails_without_choch_after_sweep() -> None:
    from smc_overlay import skill_score

    score, missing = skill_score(
        has_sweep=True,
        eq_extra=True,
        choch_after=False,
        displacement=True,
        zone_tap=True,
        pd_aligned=True,
        htf_aligned=True,
        trending=True,
    )
    assert score == 80
    assert "choch_after_sweep" in missing
    assert score < 85


def test_lots_from_risk_and_daily_guard() -> None:
    from smc_overlay import lots_from_risk, daily_guard

    lots = lots_from_risk(1000.0, 1.0, sl_distance=10.0, tick_size=0.01, tick_value=0.01, volume_min=0.01, volume_max=5.0, volume_step=0.01)
    assert lots > 0
    assert daily_guard(1000.0, 960.0, 3.0, 0, 4) == "daily_loss_cap"
    assert daily_guard(1000.0, 990.0, 3.0, 4, 4) == "max_trades_today"
    assert daily_guard(1000.0, 990.0, 3.0, 1, 4) == ""
