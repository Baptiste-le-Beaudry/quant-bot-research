"""
scripts/btc_dedicated_model.py — autonomous-session step 2: "une [version]
qui serait possiblement compatible avec le btc." This session's repeated
finding (diagnostic_btc_generalization.py v1/v2) was that applying the
ETH-derived config (jointly-trained BTC+ETH model, ETH-calibrated cutoffs)
to BTC gives only 6-11 trades over 9.6 months regardless of how the entry
filter's cutoffs are recalibrated — the deeper issue looked like BTC's
model-predicted probabilities being systematically more compressed than
ETH's WITHIN the jointly-trained model, not a cutoff-scaling problem.

This script tests the fix directly: train a model on BTC's OWN train split
ONLY (not jointly with ETH), so BTC's label distribution and feature
relationships aren't diluted/averaged against ETH's. Then run the identical
threshold + entry-filter + dca_rescue_trend pipeline used all session,
comparing against the earlier joint-model BTC result.

Usage:
    python scripts/btc_dedicated_model.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from quant_bot.backtest.engine import buy_and_hold
from scripts.phase3_baseline import load_split
from scripts.hypothesis_tests import simulate_trend_rescue, DEFAULT_EXTENSION_CAP

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HORIZON = 10
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
THRESHOLDS_TO_TRY = [0.55, 0.60, 0.65, 0.70, 0.75]


def run_for_threshold(model, kept_feats_ignore, train_feats, val_feats, val_close, threshold):
    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > threshold
    if train_selected.sum() < 20:
        return None, None
    range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
    vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()

    proba_val = model.predict_proba(val_feats)
    filtered_mask = (
        (proba_val > threshold)
        & (val_feats["range_pos_60"] < range_pos_cut)
        & (val_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()

    close_arr = val_close.to_numpy()
    ema_slope_arr = val_feats["ema_slope_20"].to_numpy()
    ret_1_arr = val_feats["ret_1"].to_numpy()
    proba_arr = proba_val.to_numpy()

    m = simulate_trend_rescue(close_arr, filtered_mask, proba_arr, ema_slope_arr, ret_1_arr,
                               DEFAULT_EXTENSION_CAP, confidence_weighted=False)
    return filtered_mask.sum(), m


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    symbol = args.symbol

    print("=" * 80)
    print(f"  {symbol}-DEDICATED MODEL (trained on {symbol} TRAIN only, not jointly with the other symbol)")
    print("=" * 80)

    train_df = load_split(symbol, "train", verbose=True)
    train_feats = build_feature_matrix(train_df)
    y_train = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")

    kept, _ = prune_redundant(train_feats, y_train, corr_threshold=0.9)
    print(f"{len(kept)} features kept ({symbol}-only pruning, may differ from the joint set).")

    fit_n = min(250_000, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(
        train_feats.loc[fit_idx], y_train.loc[fit_idx])

    val_df = load_split(symbol, "validation", verbose=True)
    val_feats = build_feature_matrix(val_df)
    val_close = val_df["close"]
    y_val = build_labels(val_close, HORIZON, COST_THRESHOLD_PCT, direction="long")
    proba_val = model.predict_proba(val_feats)
    valid = proba_val.notna() & y_val.notna()
    auc = roc_auc_score(y_val[valid], proba_val[valid])
    print(f"\n{symbol}-dedicated model AUC on VALIDATION: {auc:.4f}")
    print(f"Probability distribution on VALIDATION: "
          f"min={proba_val[valid].min():.4f} p50={proba_val[valid].median():.4f} "
          f"p90={proba_val[valid].quantile(0.90):.4f} p99={proba_val[valid].quantile(0.99):.4f} "
          f"max={proba_val[valid].max():.4f}")

    bh = buy_and_hold(val_close)
    print(f"Buy & hold over VALIDATION: {bh['total_return_pct']:+.2f}%\n")

    print(f"{'threshold':>10}{'n_filtered_entries':>20}{'n_trades':>10}{'win%':>8}"
          f"{'PF':>8}{'total_ret%':>12}")
    print("-" * 70)
    for thresh in THRESHOLDS_TO_TRY:
        n_filtered, m = run_for_threshold(model, kept, train_feats, val_feats, val_close, thresh)
        if m is None:
            print(f"{thresh:>10.2f}{'(train pop < 20)':>20}")
            continue
        if m.get("n_trades", 0) == 0:
            print(f"{thresh:>10.2f}{n_filtered:>20}{'no trades':>10}")
            continue
        print(f"{thresh:>10.2f}{n_filtered:>20}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
              f"{m['profit_factor']:>8.3f}{m['total_return_pct_of_capital']:>12.3f}")

    print("\nComparison point: the jointly-trained (BTC+ETH) model with ETH-derived config")
    print("gave only 6-11 filtered entries over 9.6mo on this same BTC VALIDATION-ish window")
    print("(diagnostic_btc_generalization.py v1/v2). If the BTC-dedicated model above produces")
    print("meaningfully more filtered entries at a usable threshold, that confirms the")
    print("compression was a joint-training artifact, not a property of BTC itself.")


if __name__ == "__main__":
    main()
