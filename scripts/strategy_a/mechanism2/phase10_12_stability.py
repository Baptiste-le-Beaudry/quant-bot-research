"""Phases 10-12: temporal (year/fold) stability, cross-symbol invariance,
leave-one-symbol-out mechanism comparison. Pure synthesis from
strategy_a_component_decomposition.csv (Phase 1-3) and
strategy_a_feature_importance_by_fold.csv (Phase 4-9) -- no new model
fits, cheap.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from common import MECH2_DOCS

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    decomp = pd.read_csv(os.path.join(MECH2_DOCS, "strategy_a_component_decomposition.csv"),
                          parse_dates=["train_start", "train_end", "test_end"])
    decomp["test_year"] = decomp["test_end"].dt.year

    # ---- Phase 10: temporal stability (H layer ratio by year, per symbol) ----
    h = decomp[decomp["layer"] == "H_full_strategy_a"].copy()
    year_stab = h.groupby(["symbol", "test_year"]).agg(
        n_folds=("fold", "nunique"), total_n=("n", "sum"),
        mean_ratio=("mfe_over_abs_mae", "mean"), median_ratio=("mfe_over_abs_mae", "median"),
    ).reset_index()
    year_path = os.path.join(MECH2_DOCS, "strategy_a_temporal_stability.csv")
    year_stab.to_csv(year_path, index=False)
    print(f"Saved -> {year_path} ({len(year_stab)} rows)")

    # stability verdict per symbol: coefficient of variation of the H-layer ratio across years
    stab_rows = []
    for symbol, sub in year_stab.groupby("symbol"):
        vals = sub["mean_ratio"].dropna()
        if len(vals) < 2:
            stab_rows.append({"symbol": symbol, "n_years": len(vals), "cv": np.nan, "verdict": "INSUFFICIENT_YEARS"})
            continue
        cv = float(vals.std() / abs(vals.mean())) if vals.mean() != 0 else np.nan
        verdict = "MECHANISM_STABILITY" if cv < 0.5 else "MECHANISM_INSTABILITY" if cv > 1.0 else "MODERATE"
        stab_rows.append({"symbol": symbol, "n_years": len(vals), "cv": cv, "verdict": verdict})
    stab_df = pd.DataFrame(stab_rows)
    stab_path = os.path.join(MECH2_DOCS, "strategy_a_temporal_stability_verdict.csv")
    stab_df.to_csv(stab_path, index=False)
    print(f"Saved -> {stab_path}")
    print(stab_df.to_string(index=False))

    # ---- Phase 11-12: cross-symbol invariance ----
    # (a) Component decomposition pattern per symbol -- does D>A and H>=D hold universally?
    pivot = decomp.pivot_table(index=["symbol", "fold"], columns="layer", values="mfe_over_abs_mae")
    pivot = pivot.reset_index()
    cross_rows = []
    for _, row in pivot.iterrows():
        a, d, h_ = row.get("A_all_eligible"), row.get("D_both_filters"), row.get("H_full_strategy_a")
        cross_rows.append({"symbol": row["symbol"], "fold": row["fold"],
                            "A": a, "D": d, "H": h_,
                            "filters_help": (d > a) if pd.notna(d) and pd.notna(a) else np.nan,
                            "rf_adds_on_filters": (h_ > d) if pd.notna(h_) and pd.notna(d) else np.nan})
    cross_df = pd.DataFrame(cross_rows)
    cross_path = os.path.join(MECH2_DOCS, "strategy_a_cross_symbol_mechanism.csv")
    cross_df.to_csv(cross_path, index=False)
    print(f"Saved -> {cross_path} ({len(cross_df)} rows)")

    summary = cross_df.groupby("symbol").agg(
        n_folds=("fold", "nunique"),
        pct_folds_filters_help=("filters_help", lambda s: float(s.mean()) * 100 if s.notna().any() else np.nan),
        pct_folds_rf_adds=("rf_adds_on_filters", lambda s: float(s.mean()) * 100 if s.notna().any() else np.nan),
        mean_H_ratio=("H", "mean"),
    ).reset_index()
    print("\nCross-symbol summary:")
    print(summary.to_string(index=False))
    summary_path = os.path.join(MECH2_DOCS, "strategy_a_cross_symbol_summary.csv")
    summary.to_csv(summary_path, index=False)
    print(f"Saved -> {summary_path}")

    # (b) Feature importance overlap across symbols (leave-one-out framing: does symbol i's
    # top-5 feature set overlap with the union of the other 8 symbols' top-5 sets?)
    imp_path = os.path.join(MECH2_DOCS, "strategy_a_feature_importance_by_fold.csv")
    if os.path.exists(imp_path):
        imp = pd.read_csv(imp_path)
        top5 = imp.groupby("symbol").apply(
            lambda g: set(g.groupby("feature")["gini_importance"].mean().sort_values(ascending=False).head(5).index)
        )
        loo_rows = []
        for sym in top5.index:
            others = set().union(*[top5[s] for s in top5.index if s != sym]) if len(top5.index) > 1 else set()
            overlap = len(top5[sym] & others) / len(top5[sym]) if len(top5[sym]) else np.nan
            loo_rows.append({"symbol": sym, "top5_features": sorted(top5[sym]),
                              "overlap_with_other_8_pct": float(overlap) * 100 if pd.notna(overlap) else np.nan})
        loo_df = pd.DataFrame(loo_rows)
        loo_path = os.path.join(MECH2_DOCS, "strategy_a_leave_one_symbol_out.csv")
        loo_df.to_csv(loo_path, index=False)
        print(f"Saved -> {loo_path}")
        print(loo_df.to_string(index=False))


if __name__ == "__main__":
    main()
