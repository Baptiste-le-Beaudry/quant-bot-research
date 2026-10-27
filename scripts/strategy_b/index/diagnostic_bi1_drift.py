"""scripts/strategy_b/index/diagnostic_bi1_drift.py — STRATEGY_ID =
B_INDEX, Experiment BI1: MFE/MAE forward-drift diagnostic on Nasdaq 100,
run BEFORE any exit-mechanics commitment (per the user's explicit
sequencing). Entry = trend regime (dist_ema200_atr>0) + range breakout
(N=60) + volatility confirmation (realized_vol_ratio>1.5), excluding
bars within 60 minutes of a known session gap. Reports raw forward path
drift/MFE/MAE at 15/30/60min horizons on VALIDATION-split data. If drift
is ~zero or negative at all three horizons, this REJECTS the hypothesis
immediately without building any walk-forward.

Usage:
    python scripts/strategy_b/index/diagnostic_bi1_drift.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "indices", "NASDAQ100_1m.csv")
TRAIN_FRACTION, VALIDATION_FRACTION = 0.60, 0.20
BREAKOUT_LOOKBACK = 60
VOL_EXPANSION_RATIO = 1.5
GAP_THRESHOLD_MIN = 10
POST_GAP_BARS = 60
HORIZONS_MIN = [15, 30, 60]
MAX_HORIZON = max(HORIZONS_MIN)
ROUND_TRIP_COST = 0.0005 * 2 + 0.0001 * 2  # fee+slip per side, both sides


def load_split(split: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, index_col=0, parse_dates=True)
    df["taker_buy_volume"] = df["volume"] / 2.0
    df["taker_sell_volume"] = df["volume"] / 2.0
    n = len(df)
    train_end = int(n * TRAIN_FRACTION)
    val_end = int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))
    bounds = {"train": (0, train_end), "validation": (train_end, val_end), "holdout": (val_end, n)}
    start, end = bounds[split]
    return df.iloc[start:end]


def post_gap_mask(index: pd.DatetimeIndex, n_bars: int, gap_threshold_min: int = GAP_THRESHOLD_MIN) -> np.ndarray:
    deltas_min = index.to_series().diff().dt.total_seconds().to_numpy() / 60.0
    is_gap = deltas_min > gap_threshold_min
    mask = np.zeros(len(index), dtype=bool)
    for pos in np.where(is_gap)[0]:
        mask[pos:pos + n_bars] = True
    return mask


def compute_entries(df: pd.DataFrame, feats: pd.DataFrame):
    breakout_level = df["high"].rolling(BREAKOUT_LOOKBACK).max().shift(1)
    breakout = df["close"] > breakout_level
    trend_ok = feats["dist_ema200_atr"] > 0
    vol_ok = feats["realized_vol_ratio"] > VOL_EXPANSION_RATIO
    gap_contaminated = post_gap_mask(df.index, POST_GAP_BARS)
    entries = (breakout.to_numpy() & trend_ok.to_numpy() & vol_ok.to_numpy() & ~gap_contaminated)
    return entries, breakout_level, gap_contaminated


def sanity_check(df, feats, entries, breakout_level, gap_contaminated, n_examples=5):
    idxs = np.flatnonzero(entries)[:n_examples]
    print(f"\n  --- BI1 manual sanity check (Nasdaq100, first {len(idxs)} signals) ---")
    for i in idxs:
        ts = df.index[i]
        window = df["high"].iloc[max(0, i - BREAKOUT_LOOKBACK):i]
        manual_max = window.max()
        ok = abs(manual_max - breakout_level.iloc[i]) < 1e-9
        print(f"  signal at {ts} idx={i}: close={df['close'].iloc[i]:.2f} "
              f"prior_60bar_high={breakout_level.iloc[i]:.2f} "
              f"dist_ema200_atr={feats['dist_ema200_atr'].iloc[i]:.3f} "
              f"vol_ratio={feats['realized_vol_ratio'].iloc[i]:.2f} "
              f"gap_contaminated={gap_contaminated[i]} "
              f"-> breakout recheck: {'MATCH' if ok else 'MISMATCH!!'}")
    if len(idxs) == 0:
        print("  (no signals in the inspected range)")


def main():
    print("=" * 100)
    print("  STRATEGY B_INDEX -- Experiment BI1: Nasdaq 100 MFE/MAE forward-drift diagnostic")
    print(f"  entry: dist_ema200_atr>0 AND breakout(N={BREAKOUT_LOOKBACK}) AND vol_ratio>{VOL_EXPANSION_RATIO}, "
          f"excluding {POST_GAP_BARS}min post-gap")
    print("=" * 100)

    val_df = load_split("validation")
    print(f"  VALIDATION: {len(val_df):,} bars, {val_df.index[0]} -> {val_df.index[-1]}")

    # DATA AUDIT (light re-check, already validated per Experiment 32)
    n_nan = int(val_df[["open", "high", "low", "close", "volume"]].isna().sum().sum())
    n_bad_range = int((val_df["high"] < val_df["low"]).sum())
    n_dupe = int(val_df.index.duplicated().sum())
    print(f"  DATA AUDIT: NaN={n_nan} bad_high<low={n_bad_range} dupe_ts={n_dupe} -> "
          f"{'PASS' if n_nan == 0 and n_bad_range == 0 and n_dupe == 0 else 'ISSUE FOUND'}")

    feats = build_feature_matrix(val_df)
    entries, breakout_level, gap_contaminated = compute_entries(val_df, feats)
    print(f"  entries={entries.sum()}  (gap-contaminated bars excluded: {gap_contaminated.sum()})")
    sanity_check(val_df, feats, entries, breakout_level, gap_contaminated)

    close_arr = val_df["close"].to_numpy()
    n = len(close_arr)
    limit = n - MAX_HORIZON - 1
    idxs = np.flatnonzero(entries[:limit])
    print(f"\n  usable entries (with full {MAX_HORIZON}min forward window available): {len(idxs)}")

    if len(idxs) < 10:
        print("\n  VERDICT: INSUFFICIENT SAMPLE -- cannot conclude yet.")
        return

    results = {}
    for h in HORIZONS_MIN:
        drifts, mfes, maes = [], [], []
        for i in idxs:
            entry_price = close_arr[i]
            path = close_arr[i:i + h + 1] / entry_price - 1.0
            drifts.append(path[-1])
            mfes.append(path.max())
            maes.append(path.min())
        drifts, mfes, maes = np.array(drifts), np.array(mfes), np.array(maes)
        results[h] = {
            "n": len(idxs),
            "drift_mean_pct": float(drifts.mean()) * 100, "drift_median_pct": float(np.median(drifts)) * 100,
            "mfe_mean_pct": float(mfes.mean()) * 100, "mae_mean_pct": float(maes.mean()) * 100,
            "pct_drift_positive": float((drifts > 0).mean()) * 100,
            "pct_drift_gt_cost": float((drifts > ROUND_TRIP_COST).mean()) * 100,
        }
        print(f"\n  Horizon={h}min: drift_mean={results[h]['drift_mean_pct']:+.4f}%  "
              f"drift_median={results[h]['drift_median_pct']:+.4f}%  "
              f"MFE_mean={results[h]['mfe_mean_pct']:+.4f}%  MAE_mean={results[h]['mae_mean_pct']:+.4f}%  "
              f"%%positive={results[h]['pct_drift_positive']:.1f}%%  "
              f"%%>roundtrip_cost({ROUND_TRIP_COST*100:.3f}%%)={results[h]['pct_drift_gt_cost']:.1f}%%")

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "strategy_b", "index", "bi1_nasdaq_drift_diagnostic.csv")
    pd.DataFrame(results).T.to_csv(out_path)
    print(f"\nSaved -> {out_path}")

    print("\n" + "=" * 100)
    print("  PRE-REGISTERED REJECTION CHECK (STRATEGY_B_INDEX_SPEC.md)")
    print("=" * 100)
    any_positive = any(results[h]["drift_mean_pct"] > 0 and results[h]["drift_median_pct"] > 0 for h in HORIZONS_MIN)
    for h in HORIZONS_MIN:
        print(f"  {h}min: drift_mean={results[h]['drift_mean_pct']:+.4f}%  drift_median={results[h]['drift_median_pct']:+.4f}%")
    if any_positive:
        print("  VERDICT: genuine positive drift found at >=1 horizon -- proceed to walk-forward with that horizon.")
    else:
        print("  VERDICT: REJECT -- drift ~zero or negative at all tested horizons. No walk-forward will be built.")


if __name__ == "__main__":
    main()
