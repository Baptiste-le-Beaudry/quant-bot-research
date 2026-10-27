"""Exp 70 step 0 (blocking) -- revision check of the frozen SqueezeMetrics DIX.csv snapshot.

Preregistration: docs/agents/hypotheses/Exp-70.md.
Rule: compare the frozen snapshot to >= 2 archived copies of DIX.csv (Wayback Machine, one dated
2023 or earlier, one dated 2025) on all common dates; if more than 1 % of `gex` values differ by
more than 1 %, REJET for revised data.

Conservative reading (the preregistration does not say relative to which value "differ by more
than 1 %" is measured): a value counts as different when |a - s| > 1 % * min(|a|, |s|), which flags
at least as many values as either "relative to snapshot" or "relative to archive". The rule is
applied to each archived copy separately, and REJET is triggered if ANY copy exceeds 1 %. Both
alternative denominators and the pooled count are reported without effect.

This script does not touch the decision window H. It only reads the snapshot and the archives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FROZEN_SHA256 = "75495c7b1bf8260679504c1370e43833c618415b252b3b29491f0fb9d8d8c190"
VALUE_TOL = 0.01      # a value "differs" if relative gap > 1 %
SHARE_TOL = 0.01      # REJET if more than 1 % of common values differ


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_dix(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    dup = int(df["date"].duplicated().sum())
    df = df.drop_duplicates("date", keep="last").set_index("date").sort_index()
    df.attrs["duplicates_dropped"] = dup
    return df


def compare(snap: pd.DataFrame, arch: pd.DataFrame, col: str = "gex") -> dict:
    common = snap.index.intersection(arch.index)
    s = snap.loc[common, col].astype(float).to_numpy()
    a = arch.loc[common, col].astype(float).to_numpy()
    gap = np.abs(a - s)
    den_min = np.minimum(np.abs(a), np.abs(s))
    diff_cons = gap > VALUE_TOL * den_min
    diff_snap = gap > VALUE_TOL * np.abs(s)
    diff_arch = gap > VALUE_TOL * np.abs(a)
    n = int(len(common))
    rel = np.divide(gap, np.abs(s), out=np.where(gap > 0, np.inf, 0.0), where=np.abs(s) > 0)
    out = {
        "n_common": n,
        "first_common": str(min(common)) if n else None,
        "last_common": str(max(common)) if n else None,
        "n_diff_conservative": int(diff_cons.sum()),
        "share_diff_conservative": float(diff_cons.mean()) if n else None,
        "n_diff_rel_snapshot": int(diff_snap.sum()),
        "share_diff_rel_snapshot": float(diff_snap.mean()) if n else None,
        "n_diff_rel_archive": int(diff_arch.sum()),
        "share_diff_rel_archive": float(diff_arch.mean()) if n else None,
        "n_exact_equal": int((gap == 0).sum()),
        "max_rel_gap_vs_snapshot": float(np.max(rel)) if n else None,
        "median_rel_gap_vs_snapshot": float(np.median(rel)) if n else None,
        "dates_only_in_archive": int(len(arch.index.difference(snap.index))),
        "snapshot_dates_in_archive_range_missing_from_archive": int(len(
            snap.index[(snap.index >= arch.index.min()) & (snap.index <= arch.index.max())].difference(arch.index))),
        "archive_dates_missing_from_snapshot_sample": [str(d) for d in list(arch.index.difference(snap.index))[:10]],
    }
    if n:
        idx = np.argsort(-np.where(np.isfinite(rel), rel, 1e300))[:10]
        out["largest_gaps"] = [{"date": str(common[i]), "snapshot": float(s[i]), "archive": float(a[i]),
                                "rel_gap_vs_snapshot": float(rel[i])} for i in idx if diff_cons[i]]
    return out


def step0(snapshot_path, archives: dict, expected_sha=FROZEN_SHA256) -> dict:
    """archives: {label (wayback timestamp) -> path}."""
    snap_sha = sha256(snapshot_path)
    if expected_sha is not None and snap_sha != expected_sha:
        raise ValueError(f"snapshot sha256 {snap_sha} != frozen {expected_sha}")
    snap = load_dix(snapshot_path)
    res, pooled_n, pooled_d = {}, 0, 0
    for label, p in sorted(archives.items()):
        arch = load_dix(p)
        r = {"path": str(p), "sha256": sha256(p), "rows": int(len(arch)),
             "first_date": str(arch.index.min()), "last_date": str(arch.index.max()),
             "duplicates_dropped": arch.attrs["duplicates_dropped"]}
        r["gex"] = compare(snap, arch, "gex")
        r["dix_reported_without_effect"] = {k: v for k, v in compare(snap, arch, "dix").items()
                                           if k in ("n_common", "n_diff_conservative", "share_diff_conservative")}
        r["price_reported_without_effect"] = {k: v for k, v in compare(snap, arch, "price").items()
                                             if k in ("n_common", "n_diff_conservative", "share_diff_conservative")}
        # publication timing (reported without effect): last row present at capture time vs capture date
        cap = pd.Timestamp(str(label)[:14], tz="UTC") if len(str(label)) >= 14 else None
        if cap is not None:
            last = arch.index.max()
            r["capture_utc"] = str(cap)
            r["capture_et"] = str(cap.tz_convert("America/New_York"))
            r["last_row_date"] = str(last)
            r["last_row_is_capture_et_date"] = bool(last == cap.tz_convert("America/New_York").date())
            r["last_row_gex_equals_snapshot"] = bool(last in snap.index and float(arch.loc[last, "gex"]) == float(snap.loc[last, "gex"]))
        r["exceeds_1pct"] =bool(r["gex"]["n_common"] > 0 and r["gex"]["share_diff_conservative"] > SHARE_TOL)
        pooled_n += r["gex"]["n_common"]
        pooled_d += r["gex"]["n_diff_conservative"]
        res[label] = r
    years = {lbl: int(str(lbl)[:4]) for lbl in res}
    has_old = any(y <= 2023 for y in years.values())
    has_2025 = any(y == 2025 for y in years.values())
    if not res:
        verdict = "AUCUNE_ARCHIVE_FORWARD_SEUL"
    elif any(r["exceeds_1pct"] for r in res.values()):
        verdict = "REJET_DONNEES_REVISEES"
    elif has_old and has_2025:
        verdict = "OK_CONTINUER"
    else:
        verdict = "INCOMPLET_ARCHIVES_MANQUANTES"
    return {
        "prereg": "docs/agents/hypotheses/Exp-70.md",
        "snapshot": {"path": str(snapshot_path), "sha256": snap_sha, "rows": int(len(snap)),
                     "first_date": str(snap.index.min()), "last_date": str(snap.index.max())},
        "rule": "REJET if, for any archived copy, more than 1 % of gex values on common dates differ by "
                "more than 1 % (|a-s| > 1 % * min(|a|,|s|), conservative)",
        "archives": res,
        "pooled_reported_without_effect": {"n_common": pooled_n, "n_diff_conservative": pooled_d,
                                           "share": pooled_d / pooled_n if pooled_n else None},
        "has_archive_2023_or_before": has_old, "has_archive_2025": has_2025,
        "verdict_step0": verdict,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--archive", action="append", default=[], help="LABEL=PATH (label = wayback timestamp)")
    ap.add_argument("--archive-dir", action="append", default=[], help="dir of DIX_wayback_<timestamp>.csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    archives = dict(x.split("=", 1) for x in a.archive)
    for d in a.archive_dir:
        for p in sorted(Path(d).glob("DIX_wayback_*.csv")):
            archives[p.stem.split("_")[-1]] = str(p)
    res = step0(a.snapshot, archives)
    Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: (v["gex"]["n_common"], v["gex"]["n_diff_conservative"], v["gex"]["share_diff_conservative"])
                      for k, v in res["archives"].items()}, indent=1))
    print("verdict_step0:", res["verdict_step0"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
