"""scripts/strategy_b/index/diagnostic_bi2_orb.py — STRATEGY_ID =
B_INDEX, Experiment BI2: classic opening-range-breakout (ORB)
forward-drift diagnostic on Nasdaq 100. See docs/strategy_b/index/
STRATEGY_B_INDEX_SPEC.md REVISION 1. Session start = bar after a >10min
gap; opening range = first 30min high/low of that session; entry = first
breakout of that range within the following 2h, trend-regime-gated.
One entry per session max.

Usage:
    python scripts/strategy_b/index/diagnostic_bi2_orb.py
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
GAP_THRESHOLD_MIN = 10
OR_MINUTES = 30
BREAKOUT_WINDOW_MIN = 120
HORIZONS_MIN = [15, 30, 60]
MAX_HORIZON = max(HORIZONS_MIN)
ROUND_TRIP_COST = 0.0005 * 2 + 0.0001 * 2


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


def find_session_starts(index: pd.DatetimeIndex) -> np.ndarray:
    deltas_min = index.to_series().diff().dt.total_seconds().to_numpy() / 60.0
    is_gap = deltas_min > GAP_THRESHOLD_MIN
    return np.where(is_gap)[0]


def compute_orb_entries(df: pd.DataFrame, feats: pd.DataFrame, session_starts: np.ndarray):
    n = len(df)
    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    trend_ok = (feats["dist_ema200_atr"] > 0).to_numpy()
    entries = np.zeros(n, dtype=bool)
    log_rows = []
    for s in session_starts:
        or_end = s + OR_MINUTES
        if or_end >= n:
            continue
        or_high = high[s:or_end].max()
        window_end = min(n, or_end + BREAKOUT_WINDOW_MIN)
        for i in range(or_end, window_end):
            if close[i] > or_high and trend_ok[i]:
                entries[i] = True
                log_rows.append({"session_start_idx": s, "session_start_time": df.index[s],
                                  "or_high": or_high, "entry_idx": i, "entry_time": df.index[i],
                                  "entry_close": close[i]})
                break  # one entry per session
    return entries, pd.DataFrame(log_rows)


def sanity_check(log: pd.DataFrame, df: pd.DataFrame, n_examples=5):
    print(f"\n  --- BI2 manual sanity check (first {min(n_examples, len(log))} ORB signals) ---")
    for _, row in log.head(n_examples).iterrows():
        s, or_end = int(row["session_start_idx"]), int(row["session_start_idx"]) + OR_MINUTES
        manual_or_high = df["high"].iloc[s:or_end].max()
        ok = abs(manual_or_high - row["or_high"]) < 1e-9
        within_window = row["entry_idx"] < or_end + BREAKOUT_WINDOW_MIN
        after_or = row["entry_idx"] >= or_end
        print(f"  session_start={row['session_start_time']} or_high={row['or_high']:.2f} "
              f"entry={row['entry_time']} entry_close={row['entry_close']:.2f} -> "
              f"OR recheck: {'MATCH' if ok else 'MISMATCH!!'}  "
              f"entry_after_OR_window: {after_or}  entry_within_breakout_window: {within_window}")


def main():
    print("=" * 100)
    print("  STRATEGY B_INDEX -- Experiment BI2: Nasdaq 100 opening-range-breakout (ORB) diagnostic")
    print(f"  OR_MINUTES={OR_MINUTES}  BREAKOUT_WINDOW_MIN={BREAKOUT_WINDOW_MIN}  trend-gated (dist_ema200_atr>0)")
    print("=" * 100)

    val_df = load_split("validation")
    print(f"  VALIDATION: {len(val_df):,} bars, {val_df.index[0]} -> {val_df.index[-1]}")

    feats = build_feature_matrix(val_df)
    session_starts = find_session_starts(val_df.index)
    print(f"  sessions detected (gap > {GAP_THRESHOLD_MIN}min): {len(session_starts)}")

    entries, log = compute_orb_entries(val_df, feats, session_starts)
    print(f"  ORB entries (sessions that actually broke out within the window): {entries.sum()} "
          f"({entries.sum()/max(1,len(session_starts))*100:.1f}% of sessions)")
    sanity_check(log, val_df)

    close_arr = val_df["close"].to_numpy()
    n = len(close_arr)
    limit = n - MAX_HORIZON - 1
    idxs = log["entry_idx"].to_numpy()
    idxs = idxs[idxs < limit]
    print(f"\n  usable entries (full {MAX_HORIZON}min forward window available): {len(idxs)}")

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

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "strategy_b", "index", "bi2_nasdaq_orb_diagnostic.csv")
    pd.DataFrame(results).T.to_csv(out_path)
    print(f"\nSaved -> {out_path}")

    print("\n" + "=" * 100)
    print("  PRE-REGISTERED REJECTION CHECK (STRATEGY_B_INDEX_SPEC.md REVISION 1)")
    print("=" * 100)
    any_positive = any(results[h]["drift_mean_pct"] > 0 and results[h]["drift_median_pct"] > 0 for h in HORIZONS_MIN)
    if any_positive:
        print("  VERDICT: genuine positive drift found at >=1 horizon -- proceed to walk-forward with that horizon.")
    else:
        print("  VERDICT: REJECT -- drift ~zero or negative at all tested horizons.")


if __name__ == "__main__":
    main()
