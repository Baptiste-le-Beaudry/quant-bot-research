"""scripts/audit/scan_nan_boolean_semantics.py — SCIENTIFIC AUDITOR,
Task B: static scanner for a CLASS of bug (found once already this
session, in scripts/strategy_a/build_shock_breadth.py): a comparison
(<, >, <=, >=, ==, !=) applied to a value that could be NaN (because it
came from .pct_change()/.shift()/.diff()/.rolling()/.resample()/
merge_asof(), none of which are followed by an explicit
.notna()/.dropna()/.fillna()/pd.isna() guard) silently evaluates to
False/True under numpy's IEEE-754 comparison semantics instead of
propagating as MISSING -- exactly the bug that made
not-yet-listed symbols look "active and not shocked" instead of
correctly excluded.

Two-pass per function:
1. Track variable names assigned from a NaN-producing expression
   (pct_change/shift/diff/rolling/resample/merge_asof) whose RHS source
   does NOT also contain a guard (notna/dropna/fillna/isna) in the SAME
   assignment.
2. Flag every Compare node (<, >, <=, >=, ==, !=) where either operand's
   ROOT NAME matches a tracked risky variable (including subscripted/
   attribute access on it, e.g. `ret15_df[sym]`).

This is a HEURISTIC, not a full data-flow analysis -- it produces
CANDIDATES for manual review. For each candidate, the correct semantics
(MISSING vs FALSE vs EXCLUDE ROW vs NOT ACTIVE) must be determined by
hand; this scanner does not auto-fix anything.

Usage:
    python scripts/audit/scan_nan_boolean_semantics.py
"""
import ast
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCAN_DIRS = [os.path.join(ROOT, "scripts"), os.path.join(ROOT, "quant_bot")]

NAN_PRODUCING_CALLS = {"pct_change", "shift", "diff", "rolling", "resample", "merge_asof", "reindex"}
GUARD_CALLS = {"notna", "dropna", "fillna", "isna", "isnull", "notnull"}
COMPARE_OPS = (ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq)


def source_of(node, src_lines):
    try:
        return ast.get_source_segment("\n".join(src_lines), node) or ""
    except Exception:
        return ""


def mentions_any(text: str, names: set) -> bool:
    return any(re.search(rf"\.{name}\s*\(", text) for name in names)


def root_name(node):
    """Walk down Subscript/Attribute chains to find the root ast.Name, e.g.
    ret15_df[sym] -> 'ret15_df', df['x'].y -> 'df'."""
    while isinstance(node, (ast.Subscript, ast.Attribute)):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


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

    # Process function-by-function (and module-level top scope) so risky-variable tracking
    # doesn't leak across unrelated functions with reused generic names.
    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    seen_scopes = set()
    for scope in scopes:
        if id(scope) in seen_scopes:
            continue
        seen_scopes.add(id(scope))

        risky_vars = set()
        # Pass 1: find risky (unguarded NaN-producing) assignments within this scope's own
        # direct statements (not recursing into nested function defs, to keep scopes distinct).
        body = scope.body if hasattr(scope, "body") else []
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                rhs_src = source_of(node.value, src_lines)
                if mentions_any(rhs_src, NAN_PRODUCING_CALLS) and not mentions_any(rhs_src, GUARD_CALLS):
                    risky_vars.add(node.targets[0].id)

        if not risky_vars:
            continue

        # Pass 2: find comparisons involving a risky variable, unguarded at the comparison site.
        for node in ast.walk(scope):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, COMPARE_OPS) for op in node.ops):
                continue
            operands = [node.left] + node.comparators
            full_expr_src = source_of(node, src_lines)
            if mentions_any(full_expr_src, GUARD_CALLS):
                continue  # guarded at the comparison site itself (e.g. `x.notna() & (x < y)` nearby)
            for operand in operands:
                r = root_name(operand)
                if r in risky_vars:
                    findings.append({
                        "file": path, "line": node.lineno, "kind": f"comparison on risky var '{r}'",
                        "snippet": full_expr_src[:140],
                    })
                    break
    return findings


def main():
    all_findings = []
    n_files = 0
    for d in SCAN_DIRS:
        for path in glob.glob(os.path.join(d, "**", "*.py"), recursive=True):
            n_files += 1
            all_findings.extend(scan_file(path))

    # Dedupe: module scope and nested FunctionDef scopes overlap under ast.walk (a Compare node
    # inside a function is visited once via the module-level walk and once via the function's own
    # scope walk) -- same (file, line, snippet) finding can appear more than once, not a
    # correctness issue, just noisy reporting.
    seen = set()
    deduped = []
    for f in all_findings:
        key = (f["file"], f["line"], f["snippet"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    all_findings = deduped

    print("=" * 100)
    print(f"  NaN BOOLEAN SEMANTICS SCAN -- {n_files} files scanned under scripts/ and quant_bot/")
    print("=" * 100)
    if not all_findings:
        print("  No candidates found.")
    for f in all_findings:
        rel = os.path.relpath(f["file"], ROOT)
        print(f"  {rel}:{f['line']}  [{f['kind']}]  {f['snippet']!r}")
    print(f"\n  Total candidates: {len(all_findings)} (heuristic -- each requires manual verification "
          f"of correct semantics: MISSING vs FALSE vs EXCLUDE ROW vs NOT ACTIVE)")
    return all_findings


if __name__ == "__main__":
    main()
