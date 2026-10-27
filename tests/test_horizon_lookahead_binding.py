"""tests/test_horizon_lookahead_binding.py — regression test for a bug
CLASS found during the 2026-08-24 scientific-validation code audit
(docs/SCIENTIFIC_VALIDATION_AUDIT.md): scripts.fast_trades used to bind
HORIZON/LOOKAHEAD as module-level globals at IMPORT time from
scripts.mae_mfe_analysis, so a caller reassigning its own LOCAL HORIZON
variable would silently NOT affect the actual trade-simulation window.

scripts.fast_trades.build_trades_with_mae_mfe_fast has SINCE been
upgraded (by another agent on this project, verified 2026-08-24) to
accept `horizon`/`lookahead` as explicit keyword parameters, defaulting
to scripts.mae_mfe_analysis's HORIZON only when omitted -- this is the
CANONICAL, robust fix now: any caller that overrides its own HORIZON
must pass `horizon=HORIZON` (or equivalent) explicitly at every
build_trades_with_mae_mfe_fast call site. The OLDER monkey-patch style
fix (`_fast_trades_module.HORIZON = ...`) is still accepted by this test
as a valid (if superseded) alternative, since it was the fix originally
applied to multi_crypto_screen.py and is still functionally correct.

This test statically scans every script matching the risk pattern
(overrides HORIZON via a CLI-style reassignment AND calls
build_trades_with_mae_mfe_fast) and asserts EITHER valid fix pattern is
present at each call site, to catch a FUTURE recurrence of the class,
not just verify past instances.

Usage:
    python -m pytest tests/test_horizon_lookahead_binding.py
    python tests/test_horizon_lookahead_binding.py
"""
import glob
import os
import re
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")

# A script is AT RISK if it (1) imports build_trades_with_mae_mfe_fast from scripts.fast_trades,
# AND (2) has a CLI-style reassignment of its own HORIZON global (`HORIZON = args.horizon` or
# `HORIZON = <something>` inside an `if ... is not None:`-style override block, i.e. NOT just the
# top-level default `HORIZON = 10`).
IMPORT_PATTERN = re.compile(r"from\s+scripts\.fast_trades\s+import\s+build_trades_with_mae_mfe_fast")
OVERRIDE_PATTERN = re.compile(r"^\s+HORIZON\s*=\s*args\.horizon", re.MULTILINE)
CALL_SITE_PATTERN = re.compile(r"build_trades_with_mae_mfe\w*\(")
HORIZON_KWARG_PATTERN = re.compile(r"\bhorizon\s*=")
PATCH_PATTERN = re.compile(r"_fast_trades_module\.HORIZON\s*=")
CALL_SITE_WINDOW_LINES = 8  # nested calls (e.g. .to_numpy()) mean a simple paren-match regex
                             # can terminate early at the wrong ")" -- scan a line window instead.


def call_sites_pass_horizon_kwarg(src: str) -> bool:
    """EITHER every build_trades_with_mae_mfe(_fast) call site explicitly passes horizon=...,
    OR the older monkey-patch style fix (_fast_trades_module.HORIZON = ...) is present anywhere
    in the file -- both are treated as valid fixes for the bug class."""
    if PATCH_PATTERN.search(src):
        return True
    lines = src.splitlines()
    call_line_nums = [i for i, line in enumerate(lines) if CALL_SITE_PATTERN.search(line)]
    if not call_line_nums:
        return True  # no call sites at all -- nothing to check here
    for i in call_line_nums:
        window = "\n".join(lines[i:i + CALL_SITE_WINDOW_LINES])
        if not HORIZON_KWARG_PATTERN.search(window):
            return False
    return True


class TestHorizonLookaheadBinding(unittest.TestCase):
    def test_no_script_overrides_horizon_without_patching_fast_trades(self):
        offenders = []
        checked = []
        for path in glob.glob(os.path.join(SCRIPTS_DIR, "**", "*.py"), recursive=True):
            with open(path, "r", encoding="utf-8") as f:
                src = f.read()
            if not IMPORT_PATTERN.search(src):
                continue
            if not OVERRIDE_PATTERN.search(src):
                continue
            checked.append(path)
            if not call_sites_pass_horizon_kwarg(src):
                offenders.append(path)

        self.assertGreater(len(checked), 0, "No scripts matched the at-risk pattern -- test may be stale "
                                             "(check IMPORT_PATTERN/OVERRIDE_PATTERN still match current code).")
        self.assertEqual(offenders, [],
                          f"Found {len(offenders)} script(s) that override HORIZON via CLI but never pass "
                          f"horizon=... explicitly to build_trades_with_mae_mfe_fast NOR patch "
                          f"scripts.fast_trades's module-level HORIZON/LOOKAHEAD (the bug class found "
                          f"2026-08-24 in multi_crypto_walkforward.py): {offenders}")


if __name__ == "__main__":
    unittest.main()
