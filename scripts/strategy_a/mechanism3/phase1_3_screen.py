"""Phase 1-3: TRANSFER SCREEN, computed and frozen BEFORE any Strategy A
backtest on the 6 new assets (docs/strategy_a/STRATEGY_A_TRANSFER_VALIDATION.md).
Reuses the exact compatibility-score formula from
scripts/strategy_a/mechanism2/phase21_30_transfer_synthesis.py (shock_structure
from mean KS vs crypto GENERIC population; feature_distribution_overlap from
pct of bars in crypto-SELECTED [p5,p95] envelope, per-feature averaged, same
method as the prior report's Phase 24; post_dip_asymmetry from a matched-event
test seeded by real crypto Strategy-A entries, same method as Phase 25).

Classification cutpoints (fixed HERE, before Phase 4 is ever run):
  INSUFFICIENT_DATA: < 12 months usable history, or matched-event sample < 10.
  LOW_COMPATIBILITY: feature_distribution_overlap_subscore < 10 OR composite < 35
    (the overlap subscore gates independently -- mirrors the screening
    playbook's own STEP 2 early-reject rule; a composite average can mask a
    near-zero overlap subscore if the other two subscores are high).
  HIGH_COMPATIBILITY: feature_distribution_overlap_subscore >= 10 AND composite >= 60.
  MEDIUM_COMPATIBILITY: everything else.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
from scipy import stats

from common3 import (MECH3_DOCS, NEW_ASSETS, ASSET_TYPE, load_equity_1m,
                      crypto_generic_pooled, crypto_selected_feats, psi, build_feature_matrix)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CORE_FEATURES = ["realized_vol_30", "atr_norm", "range_pos_60"]
MATCH_FEATURES = ["range_pos_60", "realized_vol_30"]
N_SEEDS_PER_ASSET = 60  # pooled sample across the 9-symbol crypto selected population


def setup_frequency_per_month(feats: pd.DataFrame, sel_feats: pd.DataFrame) -> float:
    """Self-referential structural-filter approximation (no ML gate --
    matches the prior report's index-approx method): range_pos_60 below
    ITS OWN sample median AND realized_vol_30 above ITS OWN sample median."""
    range_cut = feats["range_pos_60"].median()
    vol_cut = feats["realized_vol_30"].median()
    qualifying = (feats["range_pos_60"] < range_cut) & (feats["realized_vol_30"] > vol_cut)
    n_days = (feats.index.max() - feats.index.min()).days
    n_months = max(n_days / 30.44, 1e-6)
    return float(qualifying.sum() / n_months)


def main():
    print("=" * 100)
    print("  PHASE 1-3 TRANSFER SCREEN -- frozen BEFORE Phase 4 (any Strategy A backtest)")
    print("=" * 100)

    crypto_generic = {f: crypto_generic_pooled(f) for f in CORE_FEATURES}
    crypto_selected_all = crypto_selected_feats()
    print(f"  crypto generic pool sizes: {[(f, len(v)) for f, v in crypto_generic.items()]}")
    print(f"  crypto selected pool: {len(crypto_selected_all)} real Strategy-A entries, 9 symbols")

    rng = np.random.default_rng(0)
    seed_sample = crypto_selected_all.dropna(subset=MATCH_FEATURES).sample(
        n=min(N_SEEDS_PER_ASSET, len(crypto_selected_all.dropna(subset=MATCH_FEATURES))), random_state=0)

    rows = []
    dist_rows = []
    for asset in NEW_ASSETS:
        print(f"\n  --- {asset} ({ASSET_TYPE[asset]}) ---")
        raw = load_equity_1m(asset)
        n_months_hist = (raw.index.max() - raw.index.min()).days / 30.44
        feats = build_feature_matrix(raw)

        # ---- KS vs crypto GENERIC (shock_structure_subscore) ----
        ks_vals = []
        for f in CORE_FEATURES:
            asset_vals = feats[f].dropna()
            if len(asset_vals) < 30 or len(crypto_generic[f]) < 30:
                continue
            ks = stats.ks_2samp(crypto_generic[f], asset_vals)
            ks_vals.append(ks.statistic)
            psi_val = psi(crypto_generic[f].to_numpy(), asset_vals.to_numpy())
            dist_rows.append({"asset": asset, "feature": f, "ks_stat": float(ks.statistic),
                               "ks_pvalue": float(ks.pvalue), "psi": psi_val,
                               "asset_median": float(asset_vals.median()),
                               "crypto_generic_median": float(crypto_generic[f].median())})
        mean_ks = float(np.mean(ks_vals)) if ks_vals else np.nan
        shock_score = max(0.0, 100 * (1 - mean_ks)) if pd.notna(mean_ks) else np.nan

        # ---- pct of bars in crypto-SELECTED [p5,p95] envelope, per-feature averaged
        #      (feature_distribution_overlap_subscore -- same method as the prior
        #      report's Phase 24 "model extrapolation check") ----
        pct_list = []
        for f in MATCH_FEATURES:
            sel = crypto_selected_all[f].dropna()
            if len(sel) < 10:
                continue
            lo, hi = sel.quantile(0.05), sel.quantile(0.95)
            asset_vals = feats[f].dropna()
            pct_list.append(float(asset_vals.between(lo, hi).mean()) * 100)
        setup_score = float(np.mean(pct_list)) if pct_list else np.nan
        # supplementary (not part of the official score, disclosed separately): STRICT joint overlap
        joint_mask = pd.Series(True, index=feats.index)
        for f in MATCH_FEATURES:
            sel = crypto_selected_all[f].dropna()
            lo, hi = sel.quantile(0.05), sel.quantile(0.95)
            joint_mask &= feats[f].between(lo, hi).fillna(False)
        joint_pct = float(joint_mask.mean()) * 100

        setup_freq_month = setup_frequency_per_month(feats, crypto_selected_all)

        # ---- matched-event test (post_dip_asymmetry_subscore) ----
        match_feats_valid = feats[MATCH_FEATURES].dropna()
        outcome_score = np.nan
        n_matched = 0
        if len(match_feats_valid) >= 30 and len(seed_sample) >= 10:
            asset_z = (match_feats_valid - match_feats_valid.mean()) / match_feats_valid.std()
            hits = []
            for _, seed_row in seed_sample.iterrows():
                sym = seed_row.get("symbol", "UNKNOWN")
                sym_feats_full = None  # not needed: standardize seed using ITS OWN symbol pool below
                z = seed_row[MATCH_FEATURES].astype(float)
                # standardize the seed using the crypto SELECTED pool's own mean/std (consistent
                # single reference frame across all 9 seed symbols, simpler and equally valid vs.
                # the prior report's per-symbol-mean approach since this pools across symbols)
                sel_mean = crypto_selected_all[MATCH_FEATURES].mean()
                sel_std = crypto_selected_all[MATCH_FEATURES].std()
                z_std = (z - sel_mean) / sel_std
                dists = np.sqrt(((asset_z - z_std) ** 2).sum(axis=1))
                nearest_ts = dists.idxmin()
                nearest_dist = float(dists.min())
                pos = raw.index.get_indexer([nearest_ts])[0]
                if pos < 0 or pos + 30 >= len(raw):
                    continue
                entry_px = raw["close"].iloc[pos]
                fwd = raw["close"].iloc[pos:pos + 31].to_numpy() / entry_px - 1.0
                mfe, mae = float(fwd.max()), float(fwd.min())
                hits.append({"seed_symbol": sym, "match_distance_z": nearest_dist,
                             "matched_time": str(nearest_ts), "mfe_30m": mfe, "mae_30m": mae,
                             "favorable": mfe > abs(mae)})
            n_matched = len(hits)
            if n_matched >= 10:
                outcome_score = float(np.mean([h["favorable"] for h in hits])) * 100
            match_df = pd.DataFrame(hits)
            match_df.insert(0, "asset", asset)
            match_df.to_csv(os.path.join(MECH3_DOCS, f"{asset}_matched_events.csv"), index=False)

        composite = float(np.nanmean([v for v in [shock_score, setup_score, outcome_score] if pd.notna(v)])) \
            if any(pd.notna(v) for v in [shock_score, setup_score, outcome_score]) else np.nan

        insufficient = n_months_hist < 12 or n_matched < 10
        if insufficient:
            classification = "INSUFFICIENT_DATA"
        elif pd.isna(setup_score) or setup_score < 10 or pd.isna(composite) or composite < 35:
            classification = "LOW_COMPATIBILITY"
        elif setup_score >= 10 and composite >= 60:
            classification = "HIGH_COMPATIBILITY"
        else:
            classification = "MEDIUM_COMPATIBILITY"

        print(f"    months_history={n_months_hist:.1f}  shock_score={shock_score:.1f}  "
              f"setup_score(overlap)={setup_score:.2f}  joint_overlap_pct={joint_pct:.2f}  "
              f"outcome_score={outcome_score if pd.notna(outcome_score) else float('nan'):.1f}  "
              f"n_matched={n_matched}  setup_freq/month={setup_freq_month:.1f}  "
              f"COMPOSITE={composite:.1f}  -> {classification}")

        rows.append({
            "asset": asset, "asset_type": ASSET_TYPE[asset], "months_history": round(n_months_hist, 1),
            "shock_structure_subscore": round(shock_score, 2) if pd.notna(shock_score) else np.nan,
            "feature_distribution_overlap_subscore": round(setup_score, 2) if pd.notna(setup_score) else np.nan,
            "joint_overlap_pct_supplementary": round(joint_pct, 3),
            "post_dip_asymmetry_subscore": round(outcome_score, 2) if pd.notna(outcome_score) else np.nan,
            "n_matched_events": n_matched,
            "setup_frequency_per_month": round(setup_freq_month, 1),
            "TRANSFER_COMPATIBILITY_SCORE_0_100": round(composite, 1) if pd.notna(composite) else np.nan,
            "compatibility_classification": classification,
        })

    screen_df = pd.DataFrame(rows)
    screen_path = os.path.join(MECH3_DOCS, "strategy_a_transfer_screen.csv")
    screen_df.to_csv(screen_path, index=False)
    print(f"\nSaved (FROZEN, pre-Phase-4) -> {screen_path}")

    dist_df = pd.DataFrame(dist_rows)
    dist_path = os.path.join(MECH3_DOCS, "strategy_a_feature_distribution_shift.csv")
    dist_df.to_csv(dist_path, index=False)
    print(f"Saved -> {dist_path}")


if __name__ == "__main__":
    main()
