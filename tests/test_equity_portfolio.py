import unittest

import pandas as pd

from quant_bot.strategy_a_equity.portfolio import PortfolioLimits, simulate, validate_candidates


T0 = pd.Timestamp("2024-01-02 15:00", tz="UTC")


def candidates():
    return pd.DataFrame([
        {"symbol": "BBB", "fold": 1, "entry_time": T0, "exit_time": T0 + pd.Timedelta(minutes=2),
         "raw_return": 0.01, "exec_return": 0.0098, "stop_distance": 0.02, "entry_price": 100.0},
        {"symbol": "AAA", "fold": 1, "entry_time": T0, "exit_time": T0 + pd.Timedelta(minutes=1),
         "raw_return": -0.01, "exec_return": -0.0102, "stop_distance": 0.02, "entry_price": 100.0},
    ])


def price_at(symbol, timestamp):
    return 100.0


class EquityPortfolioTests(unittest.TestCase):
    def test_hand_calculated_shared_account(self):
        one = candidates().iloc[[1]]
        ledger, _, _ = simulate(one, PortfolioLimits(.01, .05, 2), price_at)
        self.assertAlmostEqual(ledger.iloc[0].notional, 50_000)
        self.assertAlmostEqual(ledger.iloc[0].pnl, -510)

    def test_collision_order_is_alphabetical(self):
        ledger, _, rejected = simulate(candidates(), PortfolioLimits(.01, .01, 2), price_at)
        self.assertEqual(ledger.iloc[0].symbol, "AAA")
        self.assertEqual(rejected.iloc[0].symbol, "BBB")
        self.assertEqual(rejected.iloc[0].reason, "OPEN_RISK_CAP")

    def test_same_symbol_overlap_rejected(self):
        frame = candidates().iloc[[1]].copy()
        later = frame.copy()
        later["entry_time"] += pd.Timedelta(seconds=30)
        later["exit_time"] += pd.Timedelta(minutes=2)
        _, _, rejected = simulate(pd.concat([frame, later]), PortfolioLimits(.005, .05, 2), price_at)
        self.assertEqual(rejected.iloc[0].reason, "SAME_SYMBOL_OPEN")

    def test_gross_cap(self):
        _, _, rejected = simulate(candidates().iloc[[1]], PortfolioLimits(.02, .10, .5), price_at)
        self.assertEqual(rejected.iloc[0].reason, "GROSS_EXPOSURE_CAP")

    def test_fee_once(self):
        ledger, _, _ = simulate(candidates().iloc[[0]], PortfolioLimits(.005, .05, 2), price_at)
        self.assertAlmostEqual(ledger.iloc[0].net_return, .0098)
        self.assertAlmostEqual(ledger.iloc[0].total_cost, ledger.iloc[0].notional * .0002)

    def test_no_future_capital(self):
        frame = candidates()
        frame.loc[frame.symbol == "BBB", "entry_time"] = T0 + pd.Timedelta(seconds=30)
        ledger, _, _ = simulate(frame, PortfolioLimits(.005, .05, 2), price_at)
        bbb = ledger[ledger.symbol == "BBB"].iloc[0]
        # Only AAA's already-paid entry half-cost is visible; its future loss
        # cannot finance or resize BBB.
        self.assertAlmostEqual(bbb.entry_equity, 99_997.5)

    def test_duplicate_and_cost_audit(self):
        with self.assertRaises(ValueError):
            validate_candidates(pd.concat([candidates(), candidates().iloc[[0]]]))
        bad = candidates()
        bad.loc[0, "exec_return"] = bad.loc[0, "raw_return"]
        with self.assertRaises(ValueError):
            validate_candidates(bad)

    def test_deterministic(self):
        first = simulate(candidates(), PortfolioLimits(.005, .05, 2), price_at)
        second = simulate(candidates(), PortfolioLimits(.005, .05, 2), price_at)
        for left, right in zip(first, second):
            pd.testing.assert_frame_equal(left, right)


if __name__ == "__main__":
    unittest.main()
