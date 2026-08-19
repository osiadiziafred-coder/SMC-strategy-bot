import unittest

from smc_logic import (
    Candle,
    all_entry_checks,
    calculate_lot_size_from_balance,
    calculate_risk_reward,
    classify_hhhl,
    detect_liquidity_sweep,
    find_swing_highs,
    find_swing_lows,
    in_session,
    is_chasing,
    is_swing_high,
    normalize_volume,
    stop_distance_ok,
)


class LotSizeTests(unittest.TestCase):
    def test_spec_balance_tiers(self):
        cases = {
            50.00: 0.01,
            100.00: 0.01,
            149.00: 0.01,
            149.99: 0.01,
            150.00: 0.02,
            200.00: 0.02,
            249.00: 0.02,
            249.99: 0.02,
            250.00: 0.03,
            300.00: 0.03,
            500.00: 0.05,
            1000.00: 0.10,
        }
        for balance, expected in cases.items():
            got = calculate_lot_size_from_balance(balance)
            self.assertAlmostEqual(got, expected, places=2, msg=f"balance={balance}")

    def test_drawdown_reduces_lot(self):
        self.assertAlmostEqual(calculate_lot_size_from_balance(1000), 0.10, places=2)
        self.assertAlmostEqual(calculate_lot_size_from_balance(140), 0.01, places=2)

    def test_continues_progression(self):
        self.assertAlmostEqual(calculate_lot_size_from_balance(1050), 0.11, places=2)
        self.assertAlmostEqual(calculate_lot_size_from_balance(1950), 0.20, places=2)

    def test_respects_broker_volume_step(self):
        lots = calculate_lot_size_from_balance(150, minlot=0.1, maxlot=5.0, step=0.1)
        self.assertAlmostEqual(lots, 0.10, places=2)

    def test_normalize_volume_caps(self):
        self.assertAlmostEqual(normalize_volume(0.001, minlot=0.01), 0.01, places=2)
        self.assertAlmostEqual(normalize_volume(999, maxlot=5.0), 5.00, places=2)


class StructureTests(unittest.TestCase):
    def _series_from_highs_lows(self, highs, lows):
        rates = []
        for i, (h, l) in enumerate(zip(highs, lows)):
            mid = (h + l) / 2.0
            rates.append(Candle(time=i, open=mid, high=h, low=l, close=mid))
        return list(reversed(rates))

    def test_swing_high_ignores_forming_bar(self):
        highs = [10, 11, 12, 15, 12, 11, 10, 9]
        lows = [9, 10, 11, 12, 11, 10, 9, 8]
        rates = self._series_from_highs_lows(highs, lows)
        self.assertFalse(is_swing_high(rates, 0, 2))
        self.assertFalse(any(idx == 0 for idx in find_swing_highs(rates, 2)))

    def test_confirmed_swing_high(self):
        values = [1, 2, 3, 10, 3, 2, 1, 0]
        rates = []
        for i, v in enumerate(values):
            rates.append(Candle(i, v, v + 1 if i == 3 else v, v - 1, v))
        rates = list(reversed(rates))
        highs = find_swing_highs(rates, 2)
        self.assertTrue(len(highs) >= 1)

    def test_bullish_hh_hl_bias(self):
        self.assertEqual(classify_hhhl([110, 100], [90, 80]), "BULLISH")

    def test_bearish_lh_ll_bias(self):
        self.assertEqual(classify_hhhl([100, 110], [80, 90]), "BEARISH")

    def test_ranging_is_none(self):
        self.assertEqual(classify_hhhl([110, 100], [80, 90]), "NONE")

    def test_find_swings_uses_closed_bars_only(self):
        rates = []
        for i in range(20):
            high = 10 + (5 if i == 10 else 0)
            low = 8 - (5 if i == 14 else 0)
            rates.append(Candle(i, 9, high, low, 9))
        rates = list(reversed(rates))
        self.assertNotIn(0, find_swing_highs(rates, 2))
        self.assertNotIn(0, find_swing_lows(rates, 2))


class LiquidityAndRiskTests(unittest.TestCase):
    def test_bullish_sweep_requires_reclaim(self):
        rates = [
            Candle(0, 101, 102, 100.8, 101.2),
            Candle(1, 100.5, 101.2, 99.2, 100.8),
            Candle(2, 100.6, 101.0, 100.2, 100.4),
        ]
        extreme = detect_liquidity_sweep(rates, 100.0, 1, min_pierce=0.4)
        self.assertIsNotNone(extreme)
        self.assertLess(extreme, 100.0)

    def test_wick_without_meaningful_level_is_not_enough(self):
        rates = [
            Candle(0, 100, 100.1, 99.99, 100.05),
            Candle(1, 100, 100.1, 99.97, 100.02),
        ]
        self.assertIsNone(detect_liquidity_sweep(rates, 100.0, 1, min_pierce=0.4))

    def test_minimum_rr(self):
        self.assertGreaterEqual(calculate_risk_reward(100, 99, 102), 2.0)
        self.assertLess(calculate_risk_reward(100, 99, 101.5), 2.0)

    def test_reject_oversized_stop(self):
        self.assertTrue(stop_distance_ok(2000, 1990, 0.01, 5000))
        self.assertFalse(stop_distance_ok(2000, 1900, 0.01, 5000))

    def test_do_not_chase(self):
        self.assertTrue(is_chasing(1, 109, 100, 110))
        self.assertFalse(is_chasing(1, 100.2, 100, 110))

    def test_session_filter(self):
        self.assertTrue(in_session(10, 7, 21, True))
        self.assertFalse(in_session(22, 7, 21, True))
        self.assertTrue(in_session(22, 7, 21, False))
        self.assertTrue(in_session(23, 22, 6, True))

    def test_one_setup_one_trade_gate(self):
        used = set()
        setup_id = (1, 123, 2000.0)
        self.assertNotIn(setup_id, used)
        used.add(setup_id)
        self.assertIn(setup_id, used)

    def test_execution_requires_all_checks(self):
        kwargs = dict(
            symbol_is_xauusdm=True,
            trading_allowed=True,
            market_open=True,
            spread_ok=True,
            open_positions=0,
            max_positions=1,
            h1_setup=True,
            m5_confirm=True,
            sl_valid=True,
            tp_valid=True,
            rr=2.1,
            min_rr=2.0,
            daily_loss_hit=False,
            drawdown_hit=False,
            lot_valid=True,
        )
        self.assertTrue(all_entry_checks(**kwargs))
        kwargs["m5_confirm"] = False
        self.assertFalse(all_entry_checks(**kwargs))
        kwargs["m5_confirm"] = True
        kwargs["rr"] = 1.5
        self.assertFalse(all_entry_checks(**kwargs))
        kwargs["rr"] = 2.1
        kwargs["open_positions"] = 1
        self.assertFalse(all_entry_checks(**kwargs))


if __name__ == "__main__":
    unittest.main()
