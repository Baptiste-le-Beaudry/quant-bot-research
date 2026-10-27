"""tests/test_fold_boundaries_train_before_test.py — dynamic regression
test for the 2026-08-24 scientific-validation audit's Task A: asserts
TRAIN_END <= TEST_START (no fold's TRAIN window extends into or past
its own TEST window) for every fold-construction function actually used
across Strategy A/B's walk-forward scripts, and that TEST windows within
each function's own fold sequence never overlap each other (a
prerequisite for the project's standard "%folds PF>1" statistic being a
genuinely non-overlapping-sample measure -- see
docs/SCIENTIFIC_VALIDATION_AUDIT.md Section 4's independence audit).

Usage:
    python -m pytest tests/test_fold_boundaries_train_before_test.py
    python tests/test_fold_boundaries_train_before_test.py
"""
import os
import sys
import unittest

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

DATA_START = pd.Timestamp("2019-11-27", tz="UTC")
SAFE_END = pd.Timestamp("2025-03-28", tz="UTC")


def _assert_folds_well_ordered(testcase, folds, label):
    testcase.assertGreater(len(folds), 0, f"{label}: produced zero folds -- test may be misconfigured")
    prev_test_end = None
    for i, fold in enumerate(folds):
        # Support both (data_start, train_end, test_end) [3-tuple] and any other fixed-length
        # fold tuple shape used across the project's scripts -- take the LAST two elements as
        # (train_end, test_end), matching every build_folds implementation surveyed in this audit.
        train_end, test_end = fold[-2], fold[-1]
        testcase.assertLess(train_end, test_end,
                             f"{label} fold {i}: TRAIN_END ({train_end}) must be strictly before "
                             f"TEST_END ({test_end})")
        testcase.assertLessEqual(test_end, SAFE_END,
                                  f"{label} fold {i}: TEST_END ({test_end}) exceeds SAFE_END/HOLDOUT "
                                  f"boundary ({SAFE_END}) -- would touch HOLDOUT")
        if prev_test_end is not None:
            # Non-overlap of TEST windows across consecutive folds: this fold's TRAIN_END
            # (== the start of its own TEST window) must be >= the previous fold's TEST_END.
            testcase.assertGreaterEqual(train_end, prev_test_end,
                                         f"{label} fold {i}: this fold's TEST window starts "
                                         f"({train_end}) before the previous fold's TEST window "
                                         f"ended ({prev_test_end}) -- TEST windows overlap, breaking "
                                         f"the project's standard non-overlapping-sample assumption "
                                         f"for '%folds PF>1'-style statistics")
        prev_test_end = test_end


class TestFoldBoundaries(unittest.TestCase):
    def test_walk_forward_engine_build_folds(self):
        from scripts.walk_forward_engine import build_folds
        folds = build_folds(DATA_START, SAFE_END)
        _assert_folds_well_ordered(self, folds, "walk_forward_engine.build_folds")

    def test_multi_crypto_transfer_walkforward_build_folds(self):
        from scripts.multi_crypto_transfer_walkforward import build_folds
        folds = build_folds(DATA_START, SAFE_END)
        _assert_folds_well_ordered(self, folds, "multi_crypto_transfer_walkforward.build_folds")

    def test_multi_crypto_walkforward_build_folds_standard_params(self):
        from scripts.multi_crypto_walkforward import build_folds
        folds = build_folds(DATA_START, SAFE_END, 24, 3, 3)
        _assert_folds_well_ordered(self, folds, "multi_crypto_walkforward.build_folds (standard 24/3/3)")

    def test_multi_crypto_walkforward_build_folds_adapted_params(self):
        """Shorter-history symbols use adapted (non-24/3/3) fold params (decide_fold_params) --
        verify the SAME invariants hold there too, not just the standard case."""
        from scripts.multi_crypto_walkforward import build_folds, decide_fold_params
        short_safe_end = DATA_START + pd.DateOffset(months=20)  # forces the adapted branch
        initial, test_m, step_m, adapted = decide_fold_params(DATA_START, short_safe_end)
        self.assertTrue(adapted, "test setup expected the adapted-fold-params branch to trigger")
        folds = build_folds(DATA_START, short_safe_end, initial, test_m, step_m)
        _assert_folds_well_ordered(self, folds, "multi_crypto_walkforward.build_folds (adapted, short history)")


if __name__ == "__main__":
    unittest.main()
