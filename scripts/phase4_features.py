"""
scripts/phase4_features.py — Phase 4: build the candidate feature matrix
(quant_bot.features.build) across BOTH BTCUSDT and ETHUSDT TRAIN slices
(concatenated), and run the mandatory redundancy pruning (SPEC.md section
5). Using both assets, not just BTC, follows directly from Phase 3's
finding that a BTC-only signal can look good and not generalize
(docs/phase3_results.md) — the same discipline applies to features.

Horizon defaults to 30min, the short end of the range Phase 3's cross-asset
check favored (docs/phase3_results.md) — override with --horizon to check
others before finalizing.

Usage:
    python scripts/phase4_features.py --horizon 30
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant, write_report
from scripts.phase3_baseline import load_train_slice

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--report", default=os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "docs", "redundancy_report.md"))
    args = parser.parse_args()

    all_features, all_labels = [], []
    for symbol in args.symbols:
        df = load_train_slice(symbol)
        feats = build_feature_matrix(df)
        label = build_labels(df["close"], args.horizon, COST_THRESHOLD_PCT)
        all_features.append(feats)
        all_labels.append(label)
        print(f"  {symbol}: {feats.shape[1]} candidate features built")

    features = pd.concat(all_features, ignore_index=True)
    label = pd.concat(all_labels, ignore_index=True)

    print(f"\nCombined: {len(features):,} rows, {features.shape[1]} candidate features, "
          f"horizon={args.horizon}min, label positive rate={label.mean()*100:.2f}%\n")

    kept, report = prune_redundant(features, label, corr_threshold=0.9)
    write_report(report, args.report)

    print(f"Kept {len(kept)} of {features.shape[1]} candidate features (report: {args.report}):")
    for f in kept:
        print(f"  - {f}  (MI={report['mutual_info'][f]:.5f})")
    if report["dropped"]:
        print(f"\nDropped as redundant ({len(report['dropped'])}):")
        for f, keeper in report["dropped"].items():
            print(f"  - {f}  ->  redundant with {keeper}")


if __name__ == "__main__":
    main()
