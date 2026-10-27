"""Compare raw-data reproduction outputs with preregistered trade exports."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPRO = DOCS / "validation_reproduction"
REFERENCES = {
    "BTCETH": DOCS / "walk_forward_v3_trades_export.csv",
    **{symbol: DOCS / f"multi_crypto_wf_{symbol}_trades.csv" for symbol in
       ("BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT")},
}
REFERENCE_MARKERS = {
    "BTCETH": DOCS / "walk_forward_v3_trades_export.csv.done_folds.txt",
    **{symbol: DOCS / f"multi_crypto_wf_{symbol}_summary.csv.done_folds.txt" for symbol in
       ("BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT")},
}
KEYS = ["symbol", "fold", "entry_time", "exit_time"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(tag: str) -> dict:
    actual_path, reference_path = REPRO / f"{tag}_trades.csv", REFERENCES[tag]
    done_path = REPRO / f"{tag}_done_folds.txt"
    if not actual_path.exists():
        return {"tag": tag, "status": "MISSING", "reference_rows": len(pd.read_csv(reference_path))}
    try:
        actual = pd.read_csv(actual_path)
    except pd.errors.EmptyDataError:
        actual = pd.DataFrame()
    reference = pd.read_csv(reference_path)
    done = {int(value) for value in done_path.read_text().split()} if done_path.exists() else set()
    expected_folds = {int(value) for value in REFERENCE_MARKERS[tag].read_text().split()}
    if done:
        reference = reference[reference.fold.isin(done)].copy()
    reference_columns = list(reference.columns)
    actual_columns = list(actual.columns)
    if actual.empty and not actual_columns:
        actual = pd.DataFrame(columns=reference_columns)
    common = [column for column in reference.columns if column in actual.columns]
    actual = actual[common].sort_values(KEYS).reset_index(drop=True)
    reference = reference[common].sort_values(KEYS).reset_index(drop=True)
    result = {
        "tag": tag, "status": "MATCH", "actual_rows": len(actual), "reference_rows": len(reference),
        "completed_folds": sorted(done), "expected_folds": sorted(expected_folds),
        "actual_sha256": digest(actual_path), "reference_sha256": digest(reference_path),
        "common_columns": len(common), "missing_columns": sorted(set(reference_columns) - set(actual_columns)),
    }
    if len(actual) != len(reference):
        result["status"] = "ROW_COUNT_MISMATCH"
        return result
    mismatches, max_abs = {}, {}
    for column in common:
        left, right = actual[column], reference[column]
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            delta = np.abs(left.to_numpy(float) - right.to_numpy(float))
            bad = ~np.isclose(left, right, rtol=1e-10, atol=1e-12, equal_nan=True)
            max_abs[column] = float(np.nanmax(delta)) if len(delta) else 0.0
        else:
            bad = left.fillna("<NA>").astype(str).to_numpy() != right.fillna("<NA>").astype(str).to_numpy()
        count = int(np.sum(bad))
        if count:
            mismatches[column] = count
    result["mismatches"] = mismatches
    result["max_abs_numeric_delta"] = max_abs
    if mismatches:
        result["status"] = "VALUE_MISMATCH"
    elif done != expected_folds:
        result["status"] = "PARTIAL_MATCH"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DOCS / "validation_reproduction_comparison.json")
    args = parser.parse_args()
    report = {"comparisons": [compare(tag) for tag in REFERENCES]}
    report["complete"] = all(row["status"] == "MATCH" for row in report["comparisons"])
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
