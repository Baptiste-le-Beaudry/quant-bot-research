"""scripts/strategy_c/null_baselines_c2.py — STRATEGY_ID = C, Experiment
C2's C13-equivalent null baselines, applied to the SPY CONFIRMATION
sample only. Reuses the exact same 4 null-baseline implementations from
null_baselines.py (same-time-of-day, same-vol-regime, random-direction,
permutation) verbatim -- per the C2 pre-registration's explicit "reuse
the nulls already defined scientifically" instruction -- restricted to
`trade_flow_imbalance` (C2's only feature) across the 3 frozen horizons.

Usage:
    python scripts/strategy_c/null_baselines_c2.py
"""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from null_baselines import run_all_nulls, NY_TZ  # noqa: E402  (reuse, do not duplicate)

EXPERIMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "experiments")
OBS_PATH = os.path.join(EXPERIMENTS_DIR, "c2_spy_observations.parquet")


def main():
    if not os.path.exists(OBS_PATH):
        print("c2_spy_observations.parquet not found -- run scripts/strategy_c/experiment_c2_reversal.py first.")
        return
    obs = pd.read_parquet(OBS_PATH)
    print("=" * 100)
    print("  STRATEGY C -- Experiment C2 null baselines (SPY confirmation sample)")
    print("=" * 100)

    ny_idx = obs.index.tz_convert(NY_TZ)
    minute_of_day = (ny_idx.hour * 60 + ny_idx.minute).to_numpy()

    log_ret = np.log(obs["mid"]).diff()
    vol = log_ret.rolling("60s").std()
    try:
        vol_q = pd.qcut(vol, 5, labels=False, duplicates="drop").to_numpy(dtype="float64")
    except ValueError:
        vol_q = np.full(len(obs), np.nan)

    feature_col = "trade_flow_imbalance"
    for horizon_label in ["30s", "60s", "5min"]:
        return_col = f"fwd_mid_ret_{horizon_label}"
        feature_vals = obs[feature_col].to_numpy()
        return_vals = obs[return_col].to_numpy()
        run_all_nulls(feature_vals, return_vals, minute_of_day, vol_q, feature_col, return_col)
        gc.collect()


if __name__ == "__main__":
    main()
