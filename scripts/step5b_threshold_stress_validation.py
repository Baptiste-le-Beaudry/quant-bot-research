"""
scripts/step5b_threshold_stress_validation.py — follow-up to Experiment 5:
a UNIFORM threshold=0.725 (not per-asset-tuned) looked like a clear win on
BTC (n, PF, and return all better than 0.75) and a modest giveback on ETH,
with a better COMBINED total return than the registered threshold=0.75.
That was frictionless VALIDATION only. Before considering promotion to
BASELINE_CANDIDATE_V3, this repeats Experiment 1's stress dimensions
(slippage, fill gap, latency, funding, combined worst case) on threshold=
0.725 exactly as it did for the registered 0.75, so the two are compared
on equal footing rather than adopting a frictionless-only win (the same
mistake Experiment 6/6b was built to catch for the stop-percentile lead).

Usage:
    python scripts/step5b_threshold_stress_validation.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.step1_stress_test import (
    TRAIN_SYMBOLS, HORIZON, LEVERAGE, load_funding, simulate_stressed, historical_mae_stop_distance,
)
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

THRESHOLDS_TO_COMPARE = [0.75, 0.725]


def get_setup_for_threshold(symbol: str, model, threshold: float):
    """Returns VALIDATION setup AND the TRAIN-calibrated stop distance --
    fixed after finding this script originally computed the stop from
    VALIDATION's own trades (the exact self-referential leak flagged after
    Experiment 1, reintroduced here by mistake -- historical_mae_stop_distance
    was called on VALIDATION trades, not TRAIN ones, in the first version
    of this script)."""
    train_df = load_split(symbol, "train", verbose=False)
    train_feats = build_feature_matrix(train_df)
    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > threshold
    range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
    vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()

    train_close = train_df["close"].to_numpy()
    train_ema_slope = train_feats["ema_slope_20"].to_numpy()
    train_ret_1 = train_feats["ret_1"].to_numpy()
    train_filtered_mask = (
        (train_proba > threshold)
        & (train_feats["range_pos_60"] < range_pos_cut)
        & (train_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    train_trades = build_trades_with_mae_mfe(train_close, train_filtered_mask, train_ema_slope, train_ret_1)
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), 90))

    val_df = load_split(symbol, "validation", verbose=False)
    val_feats = build_feature_matrix(val_df)
    val_proba = model.predict_proba(val_feats)
    filtered_mask = (
        (val_proba > threshold)
        & (val_feats["range_pos_60"] < range_pos_cut)
        & (val_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    ema_slope_arr = val_feats["ema_slope_20"].to_numpy()
    ret_1_arr = val_feats["ret_1"].to_numpy()
    return val_df, filtered_mask, ema_slope_arr, ret_1_arr, stop_distance


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min...")
    train_feats_all, train_labels_all = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats_all[symbol] = build_feature_matrix(df)
        train_labels_all[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train = pd.concat(train_labels_all.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.\n")

    all_rows = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        funding = load_funding(symbol)
        print("=" * 100)
        print(f"  {symbol} — threshold 0.75 (registered) vs 0.725 (candidate) under stress")
        print("=" * 100)

        for thr in THRESHOLDS_TO_COMPARE:
            df_val, filtered_mask, ema_slope_arr, ret_1_arr, stop_distance = get_setup_for_threshold(symbol, model, thr)
            close_arr = df_val["close"].to_numpy()
            timestamps = df_val.index
            trades = build_trades_with_mae_mfe(close_arr, filtered_mask, ema_slope_arr, ret_1_arr)
            leverage = LEVERAGE[symbol]

            label = f"thr={thr}"
            print(f"\n  -- {label} (n_entries={len(trades)}, stop={stop_distance*100:.2f}%, lev={leverage}x) --")
            for gap in [0.0, 0.0025, 0.0050]:
                r = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage, gap_extra=gap)
                print(f"    gap={gap*100:>5.2f}%  n={r.get('n_trades',0):>4} "
                      f"PF={r.get('profit_factor',float('nan')):>7.3f} "
                      f"ret={r.get('total_return_pct',float('nan')):>+7.3f}% "
                      f"DD={r.get('max_dd_pct',float('nan')):>+7.3f}%")
                all_rows.append({"symbol": symbol, "threshold": thr, "scenario": f"gap{gap}", **r})
            worst = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage,
                                       slip_mult_entry=2, slip_mult_trailing=2, slip_mult_stop=2,
                                       slip_mult_time=2, gap_extra=0.0025, funding_mult=2, entry_delay=1)
            print(f"    WORST CASE  n={worst.get('n_trades',0):>4} "
                  f"PF={worst.get('profit_factor',float('nan')):>7.3f} "
                  f"ret={worst.get('total_return_pct',float('nan')):>+7.3f}% "
                  f"DD={worst.get('max_dd_pct',float('nan')):>+7.3f}%")
            all_rows.append({"symbol": symbol, "threshold": thr, "scenario": "worst_case", **worst})
        print()

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step5b_threshold_stress_raw.csv")
    pd.DataFrame(all_rows).to_csv(out_path, index=False)
    print(f"Raw results saved -> {out_path}")


if __name__ == "__main__":
    main()
