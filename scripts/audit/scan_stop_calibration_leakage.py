"""scripts/audit/scan_stop_calibration_leakage.py — SCIENTIFIC AUDITOR,
Task A: static scanner for a CLASS of bug (not just the two already-
known instances in Experiments 5/8): a protective stop, trailing
parameter, MAE/MFE percentile, or stop-derived leverage calibrated on
VALIDATION/TEST data instead of TRAIN. Scans every .py file under
scripts/ and quant_bot/ using the ast module (not fragile regex) for:

1. Calls to np.percentile(...)/np.quantile(...)/<series>.quantile(...)
   whose ARGUMENT expression's source text references "val"/"test"
   population without also referencing "train".
2. Assignments to a stop/trail/leverage-named variable
   (stop_distance, trail_dist, trail_distance, activate_at, leverage,
   protective, mae*, mfe*) whose RHS source text has the same
   val/test-without-train signature.

This is a HEURISTIC (source-text substring matching on variable/call
names, not a full data-flow analysis) -- it produces CANDIDATES for
manual review, not certainties. Every candidate must be manually
verified before being called a real bug (see the audit document for
the manual review of each candidate this scan produced).

Usage:
    python scripts/audit/scan_stop_calibration_leakage.py
"""
import ast
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCAN_DIRS = [os.path.join(ROOT, "scripts"), os.path.join(ROOT, "quant_bot")]

RISKY_ASSIGN_NAMES = re.compile(
    r"^(stop_distance|trail_dist(ance)?|activate_at|leverage\w*|protective\w*|mae\w*|mfe\w*)$",
    re.IGNORECASE)
PERCENTILE_CALL_NAMES = {"percentile", "quantile", "nanpercentile"}

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Component-based, not \b-based: Python identifiers use snake_case, and `\b` does NOT create a
# boundary between "val" and "_" (both are \w characters) -- "val_trades" would never match
# r"\bval\b". Split each identifier on "_" and check whole COMPONENTS instead. Verified by a
# self-test (test_scan_stop_calibration_leakage.py) that this catches "val_trades" etc.
VAL_TEST_COMPONENTS = {"val", "validation", "test"}
TRAIN_COMPONENTS = {"train"}


def percentile_call_population_node(node: ast.AST):
    """Returns the AST node representing the DATA POPULATION being percentiled/quantiled, or
    None if this isn't a percentile/quantile call. Two distinct calling conventions:
      (a) function-style np.percentile(data, p) / np.nanpercentile(data, p) -- population is args[0].
      (b) method-style <series>.quantile(p) -- population is the object the method is called ON
          (node.func.value), NOT args[0] (which is just the quantile level, e.g. 0.90 -- a float
          literal with no train/val/test tokens at all, so checking args[0] here would silently
          never flag anything, a real gap found via manual review of this scanner's own output)."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in PERCENTILE_CALL_NAMES:
        if func.attr == "quantile":
            return func.value  # method-style: population is the caller object
        return node.args[0] if node.args else None  # e.g. np.percentile(...), an Attribute call too
    if isinstance(func, ast.Name) and func.id in PERCENTILE_CALL_NAMES:
        return node.args[0] if node.args else None  # bare `percentile(...)` after a `from x import percentile`
    return None


def source_of(node: ast.AST, src_lines: list) -> str:
    try:
        return ast.get_source_segment("\n".join(src_lines), node) or ""
    except Exception:
        return ""


def _identifier_components(text: str) -> set:
    components = set()
    for ident in IDENTIFIER_PATTERN.findall(text):
        components.update(part.lower() for part in ident.split("_") if part)
    return components


def classify(text: str) -> str:
    """Returns 'CANDIDATE_LEAK' if the text mentions val/test population
    without also mentioning train (in the SAME expression -- e.g.
    'val_feats' alone is suspicious; 'train_feats' or a variable that
    itself is clearly TRAIN-derived is not). Matches on snake_case
    IDENTIFIER COMPONENTS (split on '_'), not \\b-delimited substrings --
    r"\\bval\\b" would never match inside "val_trades" since '_' is a
    word character in Python identifiers (no boundary between val/_)."""
    components = _identifier_components(text)
    has_val_test = bool(components & VAL_TEST_COMPONENTS)
    has_train = bool(components & TRAIN_COMPONENTS)
    if has_val_test and not has_train:
        return "CANDIDATE_LEAK"
    return "OK"


def scan_file(path: str) -> list:
    findings = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except Exception:
        return findings
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError:
        return findings
    src_lines = src.splitlines()

    for node in ast.walk(tree):
        # Case 1: percentile/quantile calls -- population node depends on calling convention
        # (function-style np.percentile(data, p) vs method-style series.quantile(p)).
        pop_node = percentile_call_population_node(node)
        if pop_node is not None:
            arg_src = source_of(pop_node, src_lines) or ast.dump(pop_node)
            verdict = classify(arg_src)
            if verdict == "CANDIDATE_LEAK":
                findings.append({
                    "file": path, "line": node.lineno, "kind": "percentile/quantile call",
                    "snippet": arg_src[:120],
                })
        # Case 2: assignment to a risky-named variable
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and RISKY_ASSIGN_NAMES.match(target.id):
                    rhs_src = source_of(node.value, src_lines) or ""
                    verdict = classify(rhs_src)
                    if verdict == "CANDIDATE_LEAK":
                        findings.append({
                            "file": path, "line": node.lineno, "kind": f"assignment to '{target.id}'",
                            "snippet": rhs_src[:120],
                        })
    return findings


def main():
    all_findings = []
    n_files = 0
    for d in SCAN_DIRS:
        for path in glob.glob(os.path.join(d, "**", "*.py"), recursive=True):
            n_files += 1
            all_findings.extend(scan_file(path))

    print("=" * 100)
    print(f"  STOP CALIBRATION LEAKAGE SCAN -- {n_files} files scanned under scripts/ and quant_bot/")
    print("=" * 100)
    if not all_findings:
        print("  No candidates found.")
    for f in all_findings:
        rel = os.path.relpath(f["file"], ROOT)
        print(f"  {rel}:{f['line']}  [{f['kind']}]  {f['snippet']!r}")
    print(f"\n  Total candidates: {len(all_findings)} (heuristic -- each requires manual verification)")
    return all_findings


if __name__ == "__main__":
    main()
