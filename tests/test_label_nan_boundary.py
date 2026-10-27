"""tests/test_label_nan_boundary.py — regression test for a real bug
found during the 2026-08-24 scientific-validation audit's Task B (NaN
BOOLEAN SEMANTICS GUARD): quant_bot/features/build_h1.py's
build_labels_h1 was missing the NaN-preservation guard that its sibling
quant_bot/features/build.py's build_labels already has (with an
explicit comment about exactly this risk) -- the final horizon rows of
any close-price series have no future bar to compute a forward return
from (`close.shift(-horizon)` is NaN there), and a plain `(fwd >
threshold).astype(float)` comparison silently maps that NaN to 0.0 (a
real, wrong class label) instead of leaving it correctly missing/
excluded. Fixed in build_h1.py to match build.py's existing pattern.
No historical reported/adopted result was affected (verified via grep:
build_labels_h1's only callers, scripts/h1_dedicated_model.py and
scripts/h1_multi_asset_test.py, are never cited in
docs/research_plan_status.md).

Usage:
    python -m pytest tests/test_label_nan_boundary.py
    python tests/test_label_nan_boundary.py
"""
import os
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from quant_bot.features.build import build_labels
from quant_bot.features.build_h1 import build_labels_h1


class TestLabelNaNBoundary(unittest.TestCase):
    def _close_series(self, n=200):
        rng = np.random.default_rng(0)
        return pd.Series(100 + np.cumsum(rng.normal(0, 0.1, n)))

    def test_build_labels_final_horizon_rows_are_nan_not_zero(self):
        close = self._close_series()
        horizon = 10
        label = build_labels(close, horizon, cost_threshold_pct=0.0005, direction="long")
        tail = label.iloc[-horizon:]
        self.assertTrue(tail.isna().all(),
                         "build_labels: final horizon rows must be NaN (excluded), not silently 0.0")
        self.assertFalse(label.iloc[:-horizon].isna().any(),
                          "build_labels: rows with a valid forward bar must never be NaN")

    def test_build_labels_h1_final_horizon_rows_are_nan_not_zero(self):
        """This is the exact case that was broken before this audit's fix."""
        close = self._close_series()
        horizon = 5
        label = build_labels_h1(close, horizon, cost_threshold_pct=0.0005, direction="long")
        tail = label.iloc[-horizon:]
        self.assertTrue(tail.isna().all(),
                         "build_labels_h1: final horizon rows must be NaN (excluded), not silently 0.0 "
                         "(this was the bug found 2026-08-24 -- regression guard)")
        self.assertFalse(label.iloc[:-horizon].isna().any(),
                          "build_labels_h1: rows with a valid forward bar must never be NaN")

    def test_build_labels_and_build_labels_h1_agree_on_short_direction_too(self):
        close = self._close_series()
        horizon = 7
        for direction in ("long", "short"):
            label_1m = build_labels(close, horizon, cost_threshold_pct=0.0005, direction=direction)
            label_h1 = build_labels_h1(close, horizon, cost_threshold_pct=0.0005, direction=direction)
            self.assertTrue(label_1m.iloc[-horizon:].isna().all())
            self.assertTrue(label_h1.iloc[-horizon:].isna().all())


if __name__ == "__main__":
    unittest.main()
