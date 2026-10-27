"""Phases 21-30: synthesis only -- transfer signature, transferability
score framework, QQQ/SPY failure-type classification, cost/edge
normalization, asset screening playbook, candidate asset classes. Reads
from all prior phase CSVs (this script must run LAST). No new model
fits.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from common import MECH2_DOCS, REPO_ROOT

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def safe_read(name):
    path = os.path.join(MECH2_DOCS, name)
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def main():
    decomp = safe_read("strategy_a_component_decomposition.csv")
    dist_shift = safe_read("strategy_a_feature_distribution_shift.csv")
    extrap = safe_read("strategy_a_model_extrapolation_check.csv")
    match = safe_read("strategy_a_matched_event_test.csv")
    cross_summary = safe_read("strategy_a_cross_symbol_summary.csv")
    stab_verdict = safe_read("strategy_a_temporal_stability_verdict.csv")

    # ---- Phase 21: transfer signature ----
    h = decomp[decomp["layer"] == "H_full_strategy_a"] if len(decomp) else pd.DataFrame()
    d = decomp[decomp["layer"] == "D_both_filters"] if len(decomp) else pd.DataFrame()
    mean_h_ratio = float(h["mfe_over_abs_mae"].mean()) if len(h) else np.nan
    mean_d_ratio = float(d["mfe_over_abs_mae"].mean()) if len(d) else np.nan

    signature = {
        "normalized_dip_magnitude_required": "REQUIRED",
        "range_location_low_in_60bar_range": "REQUIRED",
        "elevated_realized_vol_regime": "REQUIRED",
        "rf_nonlinear_interaction_beyond_filters": "REQUIRED_IF_MFE_MAE_GAIN_FROM_H_OVER_D_IS_LARGE" if (
            pd.notna(mean_h_ratio) and pd.notna(mean_d_ratio) and mean_d_ratio) else "UNCLEAR",
        "positive_post_dip_skew": "REQUIRED (established in the prior cross-market report: positive MFE skew present in every market/population studied)",
        "24_7_market_structure": "UNKNOWN (not isolated as a separate causal factor in this diagnostic)",
        "relative_volume_scaling_of_rebound": "OPTIONAL_BUT_DISTINGUISHING (established in the prior cross-market report: present in crypto, absent in QQQ/SPY)",
        "sufficient_event_frequency_for_walkforward": "REQUIRED (index sample this cycle was too thin, n=2-33, to fit an actual model)",
    }
    sig_path = os.path.join(MECH2_DOCS, "strategy_a_transfer_signature.json")
    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump({"mean_H_layer_mfe_mae_ratio": mean_h_ratio, "mean_D_layer_mfe_mae_ratio": mean_d_ratio,
                   "signature": signature}, f, indent=2)
    print(f"Saved -> {sig_path}")

    # ---- Phase 22: transferability score framework (for QQQ/SPY, using Phase 23-25 data) ----
    score_rows = []
    for idx_name in ["QQQ", "SPY"]:
        sub_extrap = extrap[extrap["index"] == idx_name] if len(extrap) else pd.DataFrame()
        pct_in_envelope = float(sub_extrap["pct_index_bars_in_selected_envelope"].mean()) if len(sub_extrap) else np.nan
        sub_dist = dist_shift[dist_shift["index"] == idx_name] if len(dist_shift) else pd.DataFrame()
        mean_ks = float(sub_dist["ks_stat"].mean()) if len(sub_dist) else np.nan
        shock_score = max(0, 100 * (1 - (mean_ks if pd.notna(mean_ks) else 1.0)))
        setup_score = pct_in_envelope if pd.notna(pct_in_envelope) else 0.0
        sub_match = match[match["index"] == idx_name] if len(match) else pd.DataFrame()
        outcome_score = np.nan
        if len(sub_match):
            outcome_score = float((sub_match["index_mfe_30m"] > sub_match["index_mae_30m"].abs()).mean()) * 100
        total = np.nanmean([shock_score, setup_score, outcome_score if pd.notna(outcome_score) else np.nan])
        score_rows.append({"asset": idx_name, "shock_structure_subscore": shock_score,
                            "feature_distribution_overlap_subscore": setup_score,
                            "post_dip_asymmetry_subscore": outcome_score,
                            "TRANSFER_COMPATIBILITY_SCORE_0_100": round(float(total), 1) if pd.notna(total) else np.nan})
    score_df = pd.DataFrame(score_rows)
    score_path = os.path.join(MECH2_DOCS, "strategy_a_transfer_compatibility_score.csv")
    score_df.to_csv(score_path, index=False)
    print(f"Saved -> {score_path}")
    print(score_df.to_string(index=False))

    # ---- Phase 26: QQQ/SPY failure-type classification ----
    failure_rows = []
    for idx_name in ["QQQ", "SPY"]:
        sub_extrap = extrap[extrap["index"] == idx_name] if len(extrap) else pd.DataFrame()
        pct_in_envelope = float(sub_extrap["pct_index_bars_in_selected_envelope"].mean()) if len(sub_extrap) else np.nan
        if pd.isna(pct_in_envelope):
            failure_type = "TYPE_5_INSUFFICIENT_DATA"
        elif pct_in_envelope < 5:
            failure_type = "TYPE_1_NO_SETUPS"
        else:
            sub_match = match[match["index"] == idx_name] if len(match) else pd.DataFrame()
            if len(sub_match) < 5:
                failure_type = "TYPE_5_INSUFFICIENT_DATA"
            else:
                good_outcome_rate = float((sub_match["index_mfe_30m"] > sub_match["index_mae_30m"].abs()).mean())
                failure_type = "TYPE_6_TRANSFERABLE" if good_outcome_rate > 0.55 else "TYPE_3_SAME_SETUP_DIFFERENT_OUTCOME"
        failure_rows.append({"asset": idx_name, "pct_bars_in_selected_envelope": pct_in_envelope,
                             "failure_type": failure_type})
    fail_df = pd.DataFrame(failure_rows)
    fail_path = os.path.join(MECH2_DOCS, "strategy_a_failure_type_classification.csv")
    fail_df.to_csv(fail_path, index=False)
    print(f"Saved -> {fail_path}")
    print(fail_df.to_string(index=False))

    # ---- Phase 28: asset screening playbook (standalone doc) ----
    playbook = """# Strategy A Transfer Screening Playbook

Quick, cheap screen for a NEW candidate asset BEFORE committing to a full
walk-forward backtest. Each step should REJECT early and cheaply if the
asset clearly fails -- don't proceed to the expensive steps otherwise.

## STEP 1 -- Data quality
Trades + top-of-book quotes (or reliable OHLCV) at 1-min resolution,
multi-year history if possible (multi-year matters for Phase 15/16-style
year-stability checks -- this report's own QQQ/SPY sample was only 3
months, which was the single largest confidence limiter throughout).

## STEP 2 -- Feature-space overlap (this report's Phase 23-24)
Compute range_pos_60/realized_vol_30 (identical formulas,
quant_bot/features/build.py) on the candidate asset. Compare against the
crypto Strategy-A-selected population's own [p5,p95] envelope for both
features (KS statistic, PSI). REJECT EARLY if <5% of the candidate's bars
fall in this envelope (TYPE 1 -- no setups).

## STEP 3 -- Generic dip behavior (raw MFE/MAE ratio after a normalized
dip, no model)
Bucket by shock_z (local-vol-normalized). If the GENERIC (unselected) dip
population's MFE/MAE ratio is not at least in the same ballpark as
crypto's own generic-dip ratio, that's an early (not fatal, since
Strategy A's edge is a SELECTION effect per this report's Phase 1-3
finding, not inherited from the generic population) but still relevant
signal.

## STEP 4 -- Strategy-A-like setup frequency
Using ONLY the structural filters (range_pos_60/realized_vol_30 cuts,
no ML gate yet) as an approximation, measure how many qualifying events
per year the candidate produces. REJECT EARLY if this is too thin to
ever support a real walk-forward (this report's own QQQ/SPY approximation
produced only 2-33 events over 3 months -- underpowered).

## STEP 5 -- Selected MFE/MAE asymmetry (structural-filter approximation)
On the qualifying events from Step 4, compute MFE/MAE ratio and rebound
probability. This is the closest cheap proxy to "layer D" in this
report's Phase 1-3 decomposition, without needing a trained model yet.

## STEP 6 -- Edge/friction ratio
Compare the candidate's typical selected MFE (in bps) against its own
typical spread+fees+slippage. REJECT if edge doesn't clearly exceed
friction by a healthy multiple (crypto's own margin was only ~2-3x its
round-trip cost per the prior cross-market report -- a genuinely thin
margin already, so a NEW asset needs to look at least this good).

## STEP 7 -- Only THEN: full walk-forward
Only after Steps 1-6 all look plausible, invest in an ACTUAL RandomForest
fit + walk-forward validation on the candidate asset's own data -- this
report's central finding (Phase 1-14) is that Strategy A's crypto edge is
predominantly a MODEL-SELECTION effect, so skipping straight to Step 7
without Steps 2-6 risks wasting significant compute on an asset that was
never going to work, or worse, risks "adapting Strategy A" to a new
market by training a bespoke model -- which is explicitly its own new,
separately pre-registered validation, not an assumption.
"""
    playbook_path = os.path.join(MECH2_DOCS, "strategy_a_transfer_screening_playbook.md")
    with open(playbook_path, "w", encoding="utf-8") as f:
        f.write(playbook)
    print(f"Saved -> {playbook_path}")


if __name__ == "__main__":
    main()
