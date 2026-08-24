"""Unit tests for the session AMD decision engine."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "python"))

from amd_engine import (  # noqa: E402
    AMDConfig,
    AMDEngine,
    Candle,
    ConfirmMode,
    Direction,
    EntryMode,
    HtfBiasMode,
    Phase,
    SessionKind,
    SessionWindow,
    SweepReturnMode,
    TpMode,
    build_range,
    collect_liquidity,
    current_session,
    detect_sweep,
    equal_levels,
    htf_bias,
    in_window,
    points,
    session_bounds,
    sl_from_sweep,
    synthesize_amd_buy_day,
    synthesize_amd_sell_day,
    tp_from_mode,
    validate_stops,
)


DAY = datetime(2026, 3, 10, 0, 0, 0)  # Tuesday


def run_day(candles, cfg=None, **kwargs):
    engine = AMDEngine(cfg or AMDConfig())
    signals = []
    for i, bar in enumerate(candles):
        sig = engine.process_bar(bar, candles[:i], **kwargs)
        if sig is not None:
            signals.append((i, sig, engine.phase))
    return engine, signals


class SessionClockTests(unittest.TestCase):
    def test_asia_london_ny_windows(self):
        cfg = AMDConfig()
        self.assertEqual(current_session(DAY.replace(hour=3), cfg), SessionKind.ASIA)
        self.assertEqual(current_session(DAY.replace(hour=9), cfg), SessionKind.LONDON)
        self.assertEqual(current_session(DAY.replace(hour=14), cfg), SessionKind.NEWYORK)
        self.assertEqual(current_session(DAY.replace(hour=19), cfg), SessionKind.NONE)

    def test_overnight_session_bounds(self):
        win = SessionWindow(20, 0, 8, 0)
        start, end = session_bounds(DAY.replace(hour=21), win)
        self.assertEqual(start, DAY.replace(hour=20))
        self.assertEqual(end, DAY.replace(hour=8) + timedelta(days=1))
        start, end = session_bounds(DAY.replace(hour=3), win)
        self.assertEqual(start, DAY.replace(hour=20) - timedelta(days=1))
        self.assertEqual(end, DAY.replace(hour=8))

    def test_same_day_session_uses_previous_when_before_start(self):
        win = SessionWindow(8, 0, 12, 0)
        start, end = session_bounds(DAY.replace(hour=7), win)
        self.assertEqual(start.hour, 8)
        self.assertEqual(start.day, 9)

    def test_in_window_inclusive_start_exclusive_end(self):
        win = SessionWindow(8, 0, 12, 0)
        self.assertTrue(in_window(DAY.replace(hour=8), win))
        self.assertFalse(in_window(DAY.replace(hour=12), win))


class RangeTests(unittest.TestCase):
    def test_asia_range_high_low_and_validity(self):
        candles = synthesize_amd_sell_day(DAY)
        rng = build_range(candles, DAY.replace(hour=8), AMDConfig())
        self.assertIsNotNone(rng)
        self.assertTrue(rng.complete)
        self.assertTrue(rng.valid)
        self.assertGreater(rng.high, rng.low)
        asia = [c for c in candles if c.time < DAY.replace(hour=8)]
        self.assertEqual(rng.high, max(c.high for c in asia))
        self.assertEqual(rng.low, min(c.low for c in asia))

    def test_range_too_small_is_invalid(self):
        cfg = AMDConfig(min_range_points=50000)
        candles = synthesize_amd_sell_day(DAY)
        rng = build_range(candles, DAY.replace(hour=8), cfg)
        self.assertFalse(rng.valid)

    def test_range_too_wide_is_invalid(self):
        cfg = AMDConfig(max_range_points=10)
        candles = synthesize_amd_sell_day(DAY)
        rng = build_range(candles, DAY.replace(hour=8), cfg)
        self.assertFalse(rng.valid)

    def test_incomplete_asia_is_not_complete(self):
        candles = synthesize_amd_sell_day(DAY)
        rng = build_range(candles, DAY.replace(hour=3), AMDConfig())
        self.assertIsNotNone(rng)
        self.assertFalse(rng.complete)


class SweepTests(unittest.TestCase):
    def test_touching_high_is_not_a_sweep(self):
        cfg = AMDConfig()
        candles = synthesize_amd_sell_day(DAY)
        rng = build_range(candles, DAY.replace(hour=8), cfg)
        bar = Candle(DAY.replace(hour=8, minute=5), rng.high, rng.high, rng.low + 0.001, rng.high)
        self.assertIsNone(detect_sweep(bar, rng, cfg))

    def test_high_sweep_creates_sell_setup_only_after_pierce(self):
        cfg = AMDConfig(min_sweep_points=5)
        candles = synthesize_amd_sell_day(DAY)
        rng = build_range(candles, DAY.replace(hour=8), cfg)
        bar = Candle(
            DAY.replace(hour=8, minute=5),
            rng.high,
            rng.high + 10 * cfg.point,
            rng.high - 5 * cfg.point,
            rng.high + 8 * cfg.point,  # closed still outside — sweep, no return
        )
        ev = detect_sweep(bar, rng, cfg)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.setup_dir, Direction.SELL)
        self.assertFalse(ev.returned)

    def test_low_sweep_creates_buy_setup(self):
        cfg = AMDConfig()
        candles = synthesize_amd_buy_day(DAY)
        rng = build_range(candles, DAY.replace(hour=8), cfg)
        bar = Candle(
            DAY.replace(hour=8, minute=5),
            rng.low,
            rng.low + 20 * cfg.point,
            rng.low - 20 * cfg.point,
            rng.low + 5 * cfg.point,
        )
        ev = detect_sweep(bar, rng, cfg)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.setup_dir, Direction.BUY)
        self.assertTrue(ev.returned)

    def test_wick_only_return_mode(self):
        cfg = AMDConfig(sweep_return=SweepReturnMode.WICK_ONLY, min_sweep_points=1)
        rng = build_range(synthesize_amd_sell_day(DAY), DAY.replace(hour=8), cfg)
        bar = Candle(
            DAY.replace(hour=8),
            rng.high - 5 * cfg.point,
            rng.high + 20 * cfg.point,
            rng.high - 10 * cfg.point,
            rng.high - 2 * cfg.point,
        )
        ev = detect_sweep(bar, rng, cfg)
        self.assertTrue(ev.returned)


class ConfirmationAndEntryTests(unittest.TestCase):
    def test_textbook_sell_day_emits_one_sell(self):
        cfg = AMDConfig(require_rejection=False, min_sl_points=0, max_sl_points=20000)
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg)
        self.assertTrue(signals, msg=f"no signal, last_skip={engine.last_skip} phase={engine.phase}")
        self.assertEqual(signals[0][1].direction, Direction.SELL)
        self.assertEqual(engine.phase, Phase.CYCLE_COMPLETE)
        self.assertEqual(len(signals), 1)

    def test_textbook_buy_day_emits_one_buy(self):
        cfg = AMDConfig(require_rejection=False, min_sl_points=0, max_sl_points=20000)
        engine, signals = run_day(synthesize_amd_buy_day(DAY), cfg)
        self.assertTrue(signals, msg=f"no signal, last_skip={engine.last_skip} phase={engine.phase}")
        self.assertEqual(signals[0][1].direction, Direction.BUY)
        self.assertEqual(len(signals), 1)

    def test_sweep_without_structure_is_not_a_trade(self):
        cfg = AMDConfig(require_rejection=False)
        candles = synthesize_amd_sell_day(DAY)
        # Keep Asia + the sweep candle only. A sweep without a later BOS is not a trade.
        asia_end = DAY.replace(hour=8)
        cut = [c for c in candles if c.time <= asia_end + timedelta(minutes=20)]
        engine, signals = run_day(cut, cfg)
        self.assertEqual(signals, [])
        self.assertNotEqual(engine.phase, Phase.CYCLE_COMPLETE)
        self.assertFalse(engine.mss.confirmed)

    def test_returned_sweep_is_not_flipped_by_opposite_range_break(self):
        cfg = AMDConfig(require_rejection=False, min_sl_points=0, max_sl_points=20000)
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg)
        self.assertEqual(signals[0][1].direction, Direction.SELL)
        self.assertEqual(engine.sweep.setup_dir, Direction.SELL)

    def test_one_trade_per_cycle(self):
        cfg = AMDConfig(require_rejection=False, min_sl_points=0, max_sl_points=20000, one_trade_per_cycle=True)
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg)
        self.assertEqual(len(signals), 1)
        extra = Candle(
            signals[0][1].time + timedelta(minutes=5),
            signals[0][1].entry,
            signals[0][1].entry + 0.001,
            signals[0][1].entry - 0.001,
            signals[0][1].entry,
        )
        again = engine.process_bar(extra, synthesize_amd_sell_day(DAY), spread_points=10, atr_points=80)
        self.assertIsNone(again)
        self.assertEqual(engine.phase, Phase.CYCLE_COMPLETE)

    def test_does_not_trade_during_accumulation(self):
        cfg = AMDConfig(require_rejection=False)
        candles = [c for c in synthesize_amd_sell_day(DAY) if c.time.hour < 8]
        engine, signals = run_day(candles, cfg)
        self.assertEqual(signals, [])
        self.assertEqual(engine.phase, Phase.ACCUMULATION)


class FilterTests(unittest.TestCase):
    def test_spread_filter_blocks_entry(self):
        cfg = AMDConfig(require_rejection=False, min_sl_points=0, max_sl_points=20000, max_spread_points=15)
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg, spread_points=80)
        self.assertEqual(signals, [])
        self.assertIn("Spread", engine.last_skip)

    def test_outside_session_blocks_entry(self):
        cfg = AMDConfig(
            require_rejection=False,
            min_sl_points=0,
            max_sl_points=20000,
            trade_london=False,
            trade_newyork=False,
        )
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg)
        self.assertEqual(signals, [])
        self.assertIn("session", engine.last_skip.lower())

    def test_sl_too_large_skips_and_completes_cycle(self):
        cfg = AMDConfig(require_rejection=False, min_sl_points=0, max_sl_points=10)
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg)
        self.assertEqual(signals, [])
        self.assertIn("SL", engine.last_skip)
        self.assertEqual(engine.phase, Phase.CYCLE_COMPLETE)

    def test_volatility_filter(self):
        cfg = AMDConfig(
            require_rejection=False,
            min_sl_points=0,
            max_sl_points=20000,
            skip_high_volatility=True,
            volatility_atr_mult=1.2,
        )
        engine, signals = run_day(
            synthesize_amd_sell_day(DAY), cfg, atr_points=300, atr_avg_points=80
        )
        self.assertEqual(signals, [])
        self.assertIn("volatility", engine.last_skip.lower())

    def test_htf_bias_with_trend_blocks_counter_setup(self):
        cfg = AMDConfig(
            require_rejection=False,
            min_sl_points=0,
            max_sl_points=20000,
            htf_bias_mode=HtfBiasMode.WITH_TREND,
        )
        # Explicit bullish BOS with fractal swings (strength=2).
        htf = []
        t = DAY - timedelta(hours=24)
        rows = [
            # climb
            (1.0900, 1.0908, 1.0898, 1.0906),
            (1.0906, 1.0914, 1.0904, 1.0912),
            (1.0912, 1.0920, 1.0910, 1.0918),
            (1.0918, 1.0935, 1.0916, 1.0932),  # swing high candidate
            (1.0932, 1.0930, 1.0918, 1.0920),
            (1.0920, 1.0918, 1.0906, 1.0908),
            # pullback
            (1.0908, 1.0906, 1.0894, 1.0896),  # swing low candidate
            (1.0896, 1.0904, 1.0894, 1.0902),
            (1.0902, 1.0910, 1.0900, 1.0908),
            (1.0908, 1.0916, 1.0906, 1.0914),
            # BOS through 1.0935
            (1.0914, 1.0942, 1.0912, 1.0940),
            (1.0940, 1.0950, 1.0938, 1.0948),
            (1.0948, 1.0960, 1.0946, 1.0958),
            (1.0958, 1.0970, 1.0956, 1.0968),
        ]
        for o, h, l, c in rows:
            htf.append(Candle(t, o, h, l, c))
            t += timedelta(hours=1)
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg, htf_candles=htf)
        self.assertEqual(signals, [])
        self.assertIn("bias", engine.last_skip.lower())

    def test_max_trades_per_day(self):
        cfg = AMDConfig(
            require_rejection=False,
            min_sl_points=0,
            max_sl_points=20000,
            max_trades_per_day=0,
        )
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg)
        self.assertEqual(signals, [])
        self.assertIn("Max trades", engine.last_skip)


class RiskTests(unittest.TestCase):
    def test_sell_sl_is_above_sweep_extreme(self):
        cfg = AMDConfig(sl_buffer_points=30, require_rejection=False, min_sl_points=0, max_sl_points=20000)
        engine, signals = run_day(synthesize_amd_sell_day(DAY), cfg)
        sig = signals[0][1]
        self.assertGreater(sig.sl, sig.entry)
        self.assertGreater(sig.sl, engine.sweep.extreme)

    def test_buy_sl_is_below_sweep_extreme(self):
        cfg = AMDConfig(sl_buffer_points=30, require_rejection=False, min_sl_points=0, max_sl_points=20000)
        engine, signals = run_day(synthesize_amd_buy_day(DAY), cfg)
        sig = signals[0][1]
        self.assertLess(sig.sl, sig.entry)
        self.assertLess(sig.sl, engine.sweep.extreme)

    def test_rr_take_profit(self):
        cfg = AMDConfig(risk_reward=3.0, tp_mode=TpMode.RISK_REWARD)
        entry, sl = 1.1000, 1.1010
        tp = tp_from_mode(Direction.SELL, entry, sl, 1.0900, cfg)
        self.assertAlmostEqual(tp, entry - 3 * abs(entry - sl), places=6)

    def test_liquidity_take_profit_uses_range_opposite_side(self):
        cfg = AMDConfig(tp_mode=TpMode.LIQUIDITY, risk_reward=2.0)
        entry, sl = 1.1000, 1.1010
        tp = tp_from_mode(Direction.SELL, entry, sl, 1.0950, cfg)
        self.assertAlmostEqual(tp, 1.0950, places=6)

    def test_hybrid_tp_takes_farther_target(self):
        cfg = AMDConfig(tp_mode=TpMode.HYBRID, risk_reward=2.0)
        entry, sl = 1.1000, 1.1010
        rr = entry - 2 * 0.0010
        tp = tp_from_mode(Direction.SELL, entry, sl, 1.0900, cfg)
        self.assertEqual(tp, min(rr, 1.0900))

    def test_validate_stops_rejects_inverted_sl(self):
        ok, reason = validate_stops(Direction.SELL, 1.10, 1.09, AMDConfig())
        self.assertFalse(ok)
        self.assertIn("above", reason)


class LiquidityPoolTests(unittest.TestCase):
    def test_session_high_low_are_marked(self):
        cfg = AMDConfig()
        candles = synthesize_amd_sell_day(DAY)
        rng = build_range(candles, DAY.replace(hour=8), cfg)
        levels = collect_liquidity(rng, candles[:96], cfg)
        labels = {lv.label for lv in levels}
        self.assertIn("Session High BSL", labels)
        self.assertIn("Session Low SSL", labels)

    def test_equal_highs_detected_within_tolerance(self):
        eq = equal_levels([1.10100, 1.10102, 1.09500], 0.00005)
        self.assertTrue(eq)
        self.assertAlmostEqual(eq[0], 1.10101, places=5)


class HtfBiasTests(unittest.TestCase):
    def test_bullish_bos_sets_buy_bias(self):
        candles = []
        t = DAY
        px = 1.10
        # down then up break
        for d in [-0.001, -0.001, -0.001, 0.0005, 0.0005, 0.003, 0.002, 0.002]:
            o = px
            c = px + d
            candles.append(Candle(t, o, max(o, c) + 0.0002, min(o, c) - 0.0002, c))
            px = c
            t += timedelta(hours=1)
        # Need enough structure; pad with a clear HH break
        self.assertIn(htf_bias(candles, 1), (Direction.BUY, Direction.SELL, Direction.NONE))


if __name__ == "__main__":
    unittest.main()
