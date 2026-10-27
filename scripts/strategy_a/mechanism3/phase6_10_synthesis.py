"""Phases 6-10: gate-vs-ranker (data-availability note), entry-alpha /
fixed-exit diagnostic, edge-to-friction, failure-type classification,
and small-n theory-validation correlation. Reads all prior mechanism3
CSVs plus the real docs/multi_crypto_wf_{symbol}_*.csv outputs. No new
model fits.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from common3 import MECH3_DOCS, NEW_ASSETS, ASSET_TYPE, REPO_ROOT

DOCS = os.path.join(REPO_ROOT, "docs")

# Proxy round-trip cost (bps), from STRATEGY_A_CROSS_MARKET_MECHANISM.md's own
# already-measured QQQ/SPY spread figures -- NOT a fresh per-asset measurement.
SPREAD_PROXY_PCT = {"QQQ": 0.0051, "SPY": 0.0044}
GENERIC_EQUITY_SPREAD_PROXY_PCT = float(np.mean(list(SPREAD_PROXY_PCT.values())))  # 0.00475%

screen = pd.read_csv(os.path.join(MECH3_DOCS, "strategy_a_transfer_screen.csv"))
logistic = pd.read_csv(os.path.join(MECH3_DOCS, "strategy_a_phase5_logistic_results.csv"))

rows = []
for asset in NEW_ASSETS:
    rf_summary_path = os.path.join(DOCS, f"multi_crypto_wf_{asset}_summary.csv")
    rf = pd.read_csv(rf_summary_path)
    rf_trades = rf.get("n_trades", pd.Series([0])).fillna(0).astype(float).sum()
    rf_folds_with_trades = rf[rf.get("n_trades", 0) > 0] if "n_trades" in rf.columns else pd.DataFrame()
    if len(rf_folds_with_trades):
        rf_pf = "/".join(f"{v:.2f}" for v in rf_folds_with_trades["profit_factor"])
        rf_expectancy = "/".join(f"{v:.3f}" for v in rf_folds_with_trades.get("total_return_pct", pd.Series([np.nan])))
    else:
        rf_pf, rf_expectancy = "n/a (no viable population)", "n/a"

    log_sub = logistic[logistic["symbol"] == asset]
    log_folds_with_trades = log_sub[log_sub["n_trades"] > 0]
    if len(log_folds_with_trades):
        log_pf = "/".join(f"{v:.2f}" for v in log_folds_with_trades["profit_factor"])
        log_mfe_mae = "/".join(f"{v:.2f}" for v in log_folds_with_trades["mfe_over_abs_mae"])
        log_n = int(log_folds_with_trades["n_trades"].sum())
        # typical MFE (bps) for edge/friction, from the fold with the most trades
        best_fold = log_folds_with_trades.loc[log_folds_with_trades["n_trades"].idxmax()]
        typical_mfe_pct = float(best_fold["mean_mfe_pct"])
    else:
        log_pf, log_mfe_mae, log_n, typical_mfe_pct = "n/a", "n/a", 0, np.nan

    edge_to_friction = typical_mfe_pct / GENERIC_EQUITY_SPREAD_PROXY_PCT if pd.notna(typical_mfe_pct) else np.nan

    scr = screen[screen["asset"] == asset].iloc[0]

    # ---- Phase 9: failure-type classification (AFTER Phase 4-8, distinct from the
    # FROZEN Phase 1-3 compatibility score) ----
    setup_freq_raw = scr["setup_frequency_per_month"]  # raw per-minute bar count, not independent episodes
    overlap = scr["feature_distribution_overlap_subscore"]
    if rf_trades == 0 and log_n < 10:
        # neither model found a workable population, AND the underlying feature-overlap
        # is itself near-zero -- the structural filters alone can't jointly clear the bar
        # often enough for either model to have a usable TRAIN population
        failure_type = "TYPE 1 (NO SETUPS) -- both RF and logistic TRAIN populations too thin"
    elif rf_trades == 0 and log_n >= 10:
        failure_type = "TYPE 2 (DOMAIN SHIFT) -- logistic finds a population RF's stricter decision boundary rejects; RF specifically fails, not the underlying setup"
    elif log_n >= 10 and (log_folds_with_trades["profit_factor"] < 1).sum() >= max(1, len(log_folds_with_trades) - 1):
        failure_type = "TYPE 3 (SAME SETUP, DIFFERENT OUTCOME) -- a population exists but is not fold-robustly profitable"
    else:
        failure_type = "TYPE 5 (INSUFFICIENT DATA) -- too few folds/trades for a confident call"

    if overlap < 10 and rf_trades == 0:
        decision = "REJECT -- do not pursue further without a materially different asset"
    elif log_n >= 10:
        decision = "INCONCLUSIVE -- logistic shows candidate trades but not fold-robust; needs a longer/independent sample before any further step"
    else:
        decision = "REJECT"

    rows.append({
        "asset": asset, "asset_type": ASSET_TYPE[asset],
        "compatibility_score": scr["TRANSFER_COMPATIBILITY_SCORE_0_100"],
        "compatibility_classification": scr["compatibility_classification"],
        "setup_frequency_per_month_raw_bars": setup_freq_raw,
        "feature_overlap_subscore": overlap,
        "shock_structure_subscore": scr["shock_structure_subscore"],
        "rf_trades": int(rf_trades), "rf_pf_by_fold": rf_pf, "rf_return_by_fold": rf_expectancy,
        "logistic_trades": log_n, "logistic_pf_by_fold": log_pf, "logistic_mfe_mae_by_fold": log_mfe_mae,
        "edge_to_friction_ratio_logistic": round(edge_to_friction, 1) if pd.notna(edge_to_friction) else np.nan,
        "failure_type": failure_type, "decision": decision,
    })

final = pd.DataFrame(rows)
out_path = os.path.join(MECH3_DOCS, "strategy_a_transfer_validation_summary.csv")
final.to_csv(out_path, index=False)
print(final.to_string(index=False))
print(f"\nSaved -> {out_path}")

# ---- Phase 10: theory validation -- does compatibility score correlate with outcome? ----
final["any_viable_trades"] = (final["rf_trades"] > 0) | (final["logistic_trades"] >= 10)
final["best_available_pf"] = final.apply(
    lambda r: (float(str(r["rf_pf_by_fold"]).split("/")[0]) if r["rf_pf_by_fold"] not in ("n/a (no viable population)", "n/a")
               else (float(str(r["logistic_pf_by_fold"]).split("/")[0]) if r["logistic_pf_by_fold"] != "n/a" else np.nan)),
    axis=1)
corr = final[["compatibility_score", "best_available_pf"]].dropna()
spearman = corr["compatibility_score"].corr(corr["best_available_pf"], method="spearman") if len(corr) >= 3 else np.nan
print(f"\nPhase 10 (n={len(final)}, correlation computed on n={len(corr)} with both values available):")
print(f"  Spearman(compatibility_score, best_available_fold_PF) = {spearman}")
print(final[["asset", "compatibility_score", "compatibility_classification", "any_viable_trades", "best_available_pf"]].to_string(index=False))
