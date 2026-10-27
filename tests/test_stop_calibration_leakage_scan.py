"""tests/test_stop_calibration_leakage_scan.py — regression test for
the 2026-08-24 scientific-validation audit's Task A (STOP CALIBRATION
LEAKAGE GUARD). Two things are locked in here:

1. The SCANNER ITSELF (scripts/audit/scan_stop_calibration_leakage.py)
   is correct -- during this audit, manual review found TWO real gaps
   in the scanner's own first draft: (a) `\\b`-delimited regex never
   matches inside snake_case identifiers like "val_trades" (no boundary
   between 'val' and '_', both are \\w characters), and (b) method-style
   calls (`series.quantile(p)`) were checked against the wrong AST node
   (the quantile-level argument, e.g. 0.90, instead of the actual data
   population, `series`). Both were fixed. This test pins down BOTH
   fixes with synthetic bad/good examples so a future edit to the
   scanner can't silently reintroduce either blind spot.
2. The LIVE CODEBASE currently has exactly 3 known candidates, both
   manually verified as benign (diagnostic print statements labeled
   "on VALIDATION", not feeding any stop/trail/leverage calibration) --
   if a NEW candidate appears, this test fails, forcing the same manual
   review this audit already did for the current 3.

Usage:
    python -m pytest tests/test_stop_calibration_leakage_scan.py
    python tests/test_stop_calibration_leakage_scan.py
"""
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "audit"))
sys.path.insert(0, REPO_ROOT)

import scan_stop_calibration_leakage as scanner  # noqa: E402


class TestScannerCorrectness(unittest.TestCase):
    """Pin down the two real gaps found (and fixed) during manual review."""

    def _scan_snippet(self, code: str) -> list:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            path = f.name
        try:
            return scanner.scan_file(path)
        finally:
            os.unlink(path)

    def test_snake_case_val_prefix_detected(self):
        """Gap (a): r'\\bval\\b' never matched 'val_trades' -- must be caught now."""
        findings = self._scan_snippet(
            'val_trades = build_trades(val_df)\n'
            'stop_distance = float(__import__("numpy").percentile('
            '[abs(t["mae"]) for t in val_trades], 90))\n'
        )
        self.assertGreater(len(findings), 0, "snake_case 'val_trades' should be flagged as a candidate")

    def test_snake_case_train_prefix_not_flagged(self):
        findings = self._scan_snippet(
            'train_trades = build_trades(train_df)\n'
            'stop_distance = float(__import__("numpy").percentile('
            '[abs(t["mae"]) for t in train_trades], 90))\n'
        )
        self.assertEqual(findings, [], "TRAIN-derived calibration must not be flagged")

    def test_method_style_quantile_checks_the_population_not_the_level(self):
        """Gap (b): series.quantile(p) was checked against `p` (a float, e.g. 0.90), not the
        actual population (the series itself) -- must check the RIGHT node now."""
        findings = self._scan_snippet("threshold = val_series.quantile(0.90)\n")
        self.assertGreater(len(findings), 0,
                            "method-style val_series.quantile(...) should be flagged (population, not level)")

    def test_method_style_quantile_train_not_flagged(self):
        findings = self._scan_snippet("threshold = train_series.quantile(0.90)\n")
        self.assertEqual(findings, [], "TRAIN-derived method-style quantile must not be flagged")


class TestLiveCodebaseKnownState(unittest.TestCase):
    """If this fails, a NEW candidate has appeared in scripts/ or quant_bot/ -- manually review
    it the same way this audit reviewed the 3 known ones (see docs/SCIENTIFIC_VALIDATION_AUDIT.md
    Task A) before deciding whether to update this test's expected set."""

    KNOWN_BENIGN = {
        ("scripts\\btc_dedicated_model.py", 105),  # diagnostic print "Probability distribution on VALIDATION"
        ("scripts\\multi_horizon_ensemble.py", 80),  # diagnostic print "Ensemble proba on VALIDATION"
    }

    def test_no_new_candidates_beyond_the_known_benign_set(self):
        all_findings = []
        for d in scanner.SCAN_DIRS:
            import glob
            for path in glob.glob(os.path.join(d, "**", "*.py"), recursive=True):
                all_findings.extend(scanner.scan_file(path))

        observed = {(os.path.relpath(f["file"], REPO_ROOT), f["line"]) for f in all_findings}
        new_candidates = observed - self.KNOWN_BENIGN
        self.assertEqual(new_candidates, set(),
                          f"New stop-calibration-leakage candidate(s) found, not yet manually reviewed: "
                          f"{new_candidates}. Review each per docs/SCIENTIFIC_VALIDATION_AUDIT.md's Task A "
                          f"protocol before adding to KNOWN_BENIGN (only if confirmed benign) or fixing "
                          f"(if a real leak).")


if __name__ == "__main__":
    unittest.main()
