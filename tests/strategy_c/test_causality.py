"""tests/strategy_c/test_causality.py — STRATEGY_ID = C, mandatory
causality/leakage tests (per the mandate's C7): deliberately inject a
FUTURE data point and confirm the feature computation does NOT change
at earlier timestamps as a result. This is the synthetic-injection
style test explicitly requested, not just a code-review claim of
causality.

Usage:
    python -m pytest tests/strategy_c/test_causality.py
    python tests/strategy_c/test_causality.py
"""
import os
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from quant_bot.strategy_c.features import (
    attach_prevailing_quote, classify_aggressor, quote_imbalance, spread_pct,
    trade_flow_imbalance, trade_intensity, short_term_volatility,
    distance_to_session_vwap, short_term_price_impact,
)


def _synthetic_quotes(n=200, freq="1s", start="2026-03-02 14:30:00", seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    mid = 400 + np.cumsum(rng.normal(0, 0.01, n))
    spread = 0.02
    df = pd.DataFrame({
        "bid_px_00": mid - spread / 2, "ask_px_00": mid + spread / 2,
        "bid_sz_00": rng.integers(100, 1000, n).astype(float),
        "ask_sz_00": rng.integers(100, 1000, n).astype(float),
    }, index=idx)
    return df


def _synthetic_trades(quotes: pd.DataFrame, n=100, seed=1):
    rng = np.random.default_rng(seed)
    idx = quotes.index[rng.choice(len(quotes), size=n, replace=False)].sort_values()
    mid = (quotes.loc[idx, "bid_px_00"] + quotes.loc[idx, "ask_px_00"]) / 2
    price = mid + rng.choice([-0.01, 0.01], size=n)
    size = rng.integers(10, 500, n).astype(float)
    return pd.DataFrame({"price": price.to_numpy(), "size": size}, index=idx)


class TestQuoteImbalanceCausality(unittest.TestCase):
    def test_future_quote_injection_does_not_change_earlier_values(self):
        quotes = _synthetic_quotes()
        qi_before = quote_imbalance(quotes)

        # Inject an EXTREME future quote far in the future -- must not affect any earlier value,
        # since quote_imbalance is a pure function of each row's own snapshot (no rolling window).
        future_row = quotes.iloc[[-1]].copy()
        future_row.index = future_row.index + pd.Timedelta(hours=1)
        future_row["bid_sz_00"] = 999999.0
        future_row["ask_sz_00"] = 1.0
        quotes_with_future = pd.concat([quotes, future_row]).sort_index()
        qi_after = quote_imbalance(quotes_with_future)

        pd.testing.assert_series_equal(qi_before, qi_after.iloc[:len(qi_before)], check_names=False, check_freq=False)


class TestTradeFlowImbalanceCausality(unittest.TestCase):
    def test_future_trade_injection_does_not_change_earlier_values(self):
        quotes = _synthetic_quotes()
        trades = _synthetic_trades(quotes)
        tq = attach_prevailing_quote(trades, quotes)
        tq["aggressor"] = classify_aggressor(tq)
        tfi_before = trade_flow_imbalance(tq)

        future_trade = trades.iloc[[-1]].copy()
        future_trade.index = future_trade.index + pd.Timedelta(hours=1)
        future_trade["price"] = 10000.0  # extreme, would obviously distort any leaked stat
        future_trade["size"] = 999999.0
        trades_with_future = pd.concat([trades, future_trade]).sort_index()
        tq2 = attach_prevailing_quote(trades_with_future, quotes)
        tq2["aggressor"] = classify_aggressor(tq2)
        tfi_after = trade_flow_imbalance(tq2)

        # Every timestamp that existed BEFORE the injected future trade must be numerically
        # unchanged -- a rolling(window) computation is causal (backward-looking) by construction,
        # but this test proves it empirically rather than just asserting it from reading the code.
        common_idx = tfi_before.index
        pd.testing.assert_series_equal(tfi_before, tfi_after.loc[common_idx], check_names=False, check_freq=False)

    def test_ambiguous_and_missing_trades_never_silently_become_buy_or_sell(self):
        quotes = _synthetic_quotes(n=5, freq="1s")
        # A trade with no quote coverage at all (timestamp before any quote exists).
        trades = pd.DataFrame({"price": [400.0], "size": [100.0]},
                               index=[quotes.index[0] - pd.Timedelta(seconds=10)])
        tq = attach_prevailing_quote(trades, quotes)
        aggressor = classify_aggressor(tq)
        self.assertEqual(aggressor.iloc[0], "MISSING",
                          "a trade with no prevailing quote must be MISSING, never defaulted to BUY/SELL")

        # A trade exactly at the midpoint (neither >= ask nor <= bid) must be AMBIGUOUS.
        mid_trade = pd.DataFrame({"price": [(quotes["bid_px_00"].iloc[0] + quotes["ask_px_00"].iloc[0]) / 2],
                                   "size": [100.0]}, index=[quotes.index[0]])
        tq2 = attach_prevailing_quote(mid_trade, quotes)
        aggressor2 = classify_aggressor(tq2)
        self.assertEqual(aggressor2.iloc[0], "AMBIGUOUS",
                          "a midpoint trade must be AMBIGUOUS, never defaulted to BUY based on 'above last price'")


class TestCrossedMarketExclusion(unittest.TestCase):
    def test_crossed_quote_is_missing_not_a_signed_value(self):
        quotes = _synthetic_quotes(n=5, freq="1s")
        quotes.iloc[2, quotes.columns.get_loc("bid_px_00")] = quotes.iloc[2]["ask_px_00"] + 0.05  # cross it
        qi = quote_imbalance(quotes)
        sp = spread_pct(quotes)
        self.assertTrue(pd.isna(qi.iloc[2]), "a crossed quote (bid > ask) must yield MISSING quote_imbalance, "
                                              "not a sign-flipped numeric value")
        self.assertTrue(pd.isna(sp.iloc[2]), "a crossed quote (bid > ask) must yield MISSING spread_pct, "
                                              "not a negative spread")
        # neighboring, non-crossed rows must be unaffected
        for i in (0, 1, 3, 4):
            self.assertFalse(pd.isna(qi.iloc[i]))
            self.assertFalse(pd.isna(sp.iloc[i]))


class TestSessionVWAPCausality(unittest.TestCase):
    def test_session_vwap_uses_only_past_trades_within_the_session(self):
        idx = pd.date_range("2026-03-02 14:30:00", periods=10, freq="1min", tz="UTC")  # 09:30 NY EST-adjacent
        trades = pd.DataFrame({"price": np.linspace(400, 401, 10), "size": np.full(10, 100.0)}, index=idx)
        dist_before = distance_to_session_vwap(trades)

        future_trade = trades.iloc[[-1]].copy()
        future_trade.index = future_trade.index + pd.Timedelta(minutes=1)
        future_trade["price"] = 999.0  # extreme -- would shift VWAP a lot if leaked backward
        trades2 = pd.concat([trades, future_trade])
        dist_after = distance_to_session_vwap(trades2)

        pd.testing.assert_series_equal(dist_before, dist_after.iloc[:len(dist_before)], check_names=False, check_freq=False)

    def test_session_vwap_resets_across_session_boundary(self):
        day1 = pd.date_range("2026-03-02 14:30:00", periods=3, freq="1min", tz="UTC")
        day2 = pd.date_range("2026-03-03 14:30:00", periods=3, freq="1min", tz="UTC")
        idx = day1.append(day2)
        trades = pd.DataFrame({"price": [100.0, 100.0, 100.0, 200.0, 200.0, 200.0],
                                "size": [10.0] * 6}, index=idx)
        dist = distance_to_session_vwap(trades)
        # Day 2's first trade should have ~0 distance from ITS OWN day's VWAP (200), not be
        # contaminated by day 1's much lower price level (100) -- proves the session reset works.
        self.assertAlmostEqual(dist.iloc[3], 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
