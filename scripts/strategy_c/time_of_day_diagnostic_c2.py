"""scripts/strategy_c/time_of_day_diagnostic_c2.py — STRATEGY_ID = C,
Experiment C2's C14-equivalent time-of-day diagnostic on the SPY
CONFIRMATION sample: checks whether the reversal's SIGN stays
consistent across session sub-periods -- per the pre-registration,
this is a consistency check, NOT a search for the best-performing
slice (a slice-dependent edge is explicitly a REJECT criterion for C2).

Usage:
    python scripts/strategy_c/time_of_day_diagnostic_c2.py
"""
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
OBS_PATH = os.path.join(EXPERIMENTS_DIR, "c2_spy_observations.parquet")
NY_TZ = "America/New_York"
N_DECILES = 5

SUBPERIODS = [
    ("09:30-10:00", "09:30", "10:00"),
    ("10:00-12:00", "10:00", "12:00"),
    ("12:00-14:00", "12:00", "14:00"),
    ("14:00-15:30", "14:00", "15:30"),
    ("15:30-16:00", "15:30", "16:00"),
]


def subperiod_mask(ny_index, start_str, end_str):
    start_t = pd.Timestamp(start_str).time()
    end_t = pd.Timestamp(end_str).time()
    return (ny_index.time >= start_t) & (ny_index.time < end_t)


def report(obs: pd.DataFrame, feature_col: str, return_col: str):
    ny_idx = obs.index.tz_convert(NY_TZ)
    print(f"\n  --- {feature_col} vs {return_col}, by session sub-period (SPY) ---")
    rows = []
    for label, start_str, end_str in SUBPERIODS:
        mask = subperiod_mask(ny_idx, start_str, end_str)
        sub = obs[mask].dropna(subset=[feature_col, return_col])
        if len(sub) < N_DECILES * 20:
            rows.append({"subperiod": label, "n": len(sub), "top_bottom_spread_bps": np.nan,
                         "note": "insufficient n"})
            continue
        try:
            d = pd.qcut(sub[feature_col], N_DECILES, labels=False, duplicates="drop")
        except ValueError:
            rows.append({"subperiod": label, "n": len(sub), "top_bottom_spread_bps": np.nan,
                         "note": "qcut failed (degenerate distribution)"})
            continue
        bucket_means = sub.groupby(d, observed=True)[return_col].mean().sort_index()
        spread_bps = (bucket_means.iloc[-1] - bucket_means.iloc[0]) * 10000
        n_days = pd.Series(ny_idx[mask].date).nunique()
        rows.append({"subperiod": label, "n": len(sub), "n_session_days": n_days,
                      "top_bottom_spread_bps": round(float(spread_bps), 3), "note": ""})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    return df


def main():
    if not os.path.exists(OBS_PATH):
        print("c2_spy_observations.parquet not found -- run scripts/strategy_c/experiment_c2_reversal.py first.")
        return
    obs = pd.read_parquet(OBS_PATH)
    print("=" * 100)
    print("  STRATEGY C -- Experiment C2 time-of-day diagnostic (SPY confirmation sample)")
    print("  (checking SIGN CONSISTENCY, not hunting for the best slice)")
    print("=" * 100)

    os.makedirs(EXPERIMENTS_DIR, exist_ok=True)
    for horizon_label in ["30s", "60s", "5min"]:
        df = report(obs, "trade_flow_imbalance", f"fwd_mid_ret_{horizon_label}")
        df.to_csv(os.path.join(EXPERIMENTS_DIR, f"c2_spy_tod_{horizon_label}.csv"), index=False)


if __name__ == "__main__":
    main()
