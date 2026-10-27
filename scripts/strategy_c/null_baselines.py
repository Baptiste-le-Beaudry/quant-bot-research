"""scripts/strategy_c/null_baselines.py — STRATEGY_ID = C, C13 null
baselines (pre-registered in docs/strategy_c/STRATEGY_C_FEASIBILITY_REPORT.md
Section 11, BEFORE any real result is seen, per the mandate: "decidées
AVANT de juger les resultats"). Four null baseline types:

  1. SAME-TIME-OF-DAY RANDOM: shuffle which session-day each observation's
     feature value comes from, but keep its time-of-day slot fixed --
     tests whether the apparent edge is just a time-of-day artifact
     rather than genuinely tied to the imbalance value itself.
  2. SAME-VOLATILITY-REGIME RANDOM: within short_term_volatility
     quintiles, shuffle feature values across observations that share a
     volatility regime -- tests whether the edge is just "high vol
     periods have more drift generally" rather than imbalance-specific.
  3. RANDOM DIRECTION: keep the real |feature| magnitude/bucketing but
     randomize the SIGN of the assigned decile-to-return mapping --
     tests whether a directional (not just magnitude) relationship is
     real.
  4. PERMUTATION (imbalance shuffled, intraday structure of returns
     preserved) -- already implemented inline in experiment_c1_raw_drift.py
     as the primary/cheapest null; reused here via bucket_report import
     for a combined report.

This script assumes scripts/strategy_c/experiment_c1_raw_drift.py has
already been run once and c1_observations.parquet exists (it re-uses
that saved observation set rather than recomputing features).

PERFORMANCE NOTE (2026-08-25): the first version of this script called
`obs.copy()` (all ~20 columns, 294,840 rows) plus recomputed
`tz_convert`/`rolling("60s").std()` from scratch inside EVERY one of the
4,800 draws (200 draws x 4 null types x 6 feature/horizon combos) --
this thrashed the machine's ~1-2GB free RAM and made no visible
progress after 30+ minutes. Rewritten to precompute the grouping keys
(minute-of-day, volatility quintile) ONCE, and to shuffle plain numpy
arrays via a vectorized group-preserving permutation instead of a
per-draw DataFrame copy + groupby().groups + get_indexer loop. Same
null definitions, same N_DECILES/N_DRAWS -- this is a performance fix,
not a methodology change.

Usage:
    python scripts/strategy_c/null_baselines.py
"""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EXPERIMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "experiments")
OBS_PATH = os.path.join(EXPERIMENTS_DIR, "c1_observations.parquet")
NY_TZ = "America/New_York"
N_DECILES = 10
N_DRAWS = 200


def _decile_means_arr(feature_vals: np.ndarray, return_vals: np.ndarray) -> np.ndarray:
    try:
        d = pd.qcut(pd.Series(feature_vals), N_DECILES, labels=False, duplicates="drop")
    except ValueError:
        return np.array([])
    return pd.Series(return_vals).groupby(d.to_numpy(), observed=True).mean().sort_index().to_numpy()


def _shuffle_within_groups(values: np.ndarray, group_codes: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Vectorized group-preserving shuffle: sort by group once (O(n log n)), permute each
    contiguous group slice with plain numpy indexing, scatter back. Operates on 1-D arrays only --
    never copies the full observation DataFrame, which is what previously thrashed memory."""
    order = np.argsort(group_codes, kind="stable")
    sorted_vals = values[order].copy()
    sorted_groups = group_codes[order]
    boundaries = np.flatnonzero(np.diff(sorted_groups)) + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [len(sorted_groups)]))
    for s, e in zip(starts, ends):
        if e - s > 1:
            sorted_vals[s:e] = rng.permutation(sorted_vals[s:e])
    result = np.empty_like(values)
    result[order] = sorted_vals
    return result


def _report_null(name: str, spreads: list, real_spread_bps: float):
    if not spreads:
        print(f"    NULL[{name}]: insufficient data")
        return
    arr = np.array(spreads)
    z = (real_spread_bps - arr.mean()) / (arr.std() + 1e-9)
    print(f"    NULL[{name}] (n={len(arr)} draws): mean_spread={arr.mean():.3f} bps  "
          f"std={arr.std():.3f}  z_of_real_vs_null={z:.2f}")


def run_all_nulls(feature_vals: np.ndarray, return_vals: np.ndarray, minute_of_day: np.ndarray,
                   vol_q: np.ndarray, feature_col: str, return_col: str):
    real = _decile_means_arr(feature_vals, return_vals)
    if real.size < 2:
        print(f"    [{feature_col} / {return_col}] insufficient data for bucketing, skipping")
        return
    real_spread_bps = (real[-1] - real[0]) * 10000
    print(f"\n  {feature_col} vs {return_col}: REAL top-bottom decile spread = {real_spread_bps:.3f} bps")

    # 1. same-time-of-day: shuffle feature only within observations sharing the same NY-local
    # minute-of-day (minute_of_day is never NaN, so no row exclusion needed).
    spreads = []
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        shuffled = _shuffle_within_groups(feature_vals, minute_of_day, rng)
        arr = _decile_means_arr(shuffled, return_vals)
        if arr.size >= 2:
            spreads.append((arr[-1] - arr[0]) * 10000)
    _report_null("1_same_time_of_day", spreads, real_spread_bps)

    # 2. same-volatility-regime: rows with an undefined vol quintile (rolling window not yet full)
    # are excluded entirely, matching the original script's explicit dropna(subset=["_vol_q"]).
    valid_vol = ~np.isnan(vol_q)
    fvals_v, rvals_v, volq_v = feature_vals[valid_vol], return_vals[valid_vol], vol_q[valid_vol].astype(int)
    spreads = []
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        shuffled = _shuffle_within_groups(fvals_v, volq_v, rng)
        arr = _decile_means_arr(shuffled, rvals_v)
        if arr.size >= 2:
            spreads.append((arr[-1] - arr[0]) * 10000)
    _report_null("2_same_vol_regime", spreads, real_spread_bps)

    # 3. random direction: keep magnitude, randomize sign.
    spreads = []
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        sign_flip = rng.choice([-1.0, 1.0], size=len(feature_vals))
        arr = _decile_means_arr(feature_vals * sign_flip, return_vals)
        if arr.size >= 2:
            spreads.append((arr[-1] - arr[0]) * 10000)
    _report_null("3_random_direction", spreads, real_spread_bps)

    # 4. full permutation: feature values shuffled across all observations.
    spreads = []
    for seed in range(N_DRAWS):
        rng = np.random.default_rng(seed)
        arr = _decile_means_arr(rng.permutation(feature_vals), return_vals)
        if arr.size >= 2:
            spreads.append((arr[-1] - arr[0]) * 10000)
    _report_null("4_permutation", spreads, real_spread_bps)


def main():
    if not os.path.exists(OBS_PATH):
        print("c1_observations.parquet not found -- run scripts/strategy_c/experiment_c1_raw_drift.py first.")
        return
    obs = pd.read_parquet(OBS_PATH)
    print("=" * 100)
    print("  STRATEGY C -- C13 null baselines (4 types), applied to the real C1 observation set")
    print("=" * 100)

    ny_idx = obs.index.tz_convert(NY_TZ)
    minute_of_day = (ny_idx.hour * 60 + ny_idx.minute).to_numpy()

    log_ret = np.log(obs["mid"]).diff()
    vol = log_ret.rolling("60s").std()
    try:
        vol_q = pd.qcut(vol, 5, labels=False, duplicates="drop").to_numpy(dtype="float64")
    except ValueError:
        vol_q = np.full(len(obs), np.nan)

    for feature_col in ["quote_imbalance", "trade_flow_imbalance"]:
        for horizon_label in ["30s", "60s", "5min"]:
            return_col = f"fwd_mid_ret_{horizon_label}"
            feature_vals = obs[feature_col].to_numpy()
            return_vals = obs[return_col].to_numpy()
            run_all_nulls(feature_vals, return_vals, minute_of_day, vol_q, feature_col, return_col)
            gc.collect()


if __name__ == "__main__":
    main()
