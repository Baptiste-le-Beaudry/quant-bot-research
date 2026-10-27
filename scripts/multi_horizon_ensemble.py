"""
scripts/multi_horizon_ensemble.py — hypothesis: does averaging probability
signals across multiple label horizons (5/10/15/30min), each from its own
dedicated per-symbol model, give a better-ranked entry signal than the
single horizon=10 model used all session? The horizon=10 exit mechanics
(dca_rescue_trend, EXTENSION_CAP=40) are kept fixed throughout -- only the
ENTRY signal changes, from single-horizon proba to an ensemble average.

Baseline to beat (this session, dedicated per-symbol models,
scripts/btc_dedicated_model.py): BTCUSDT thr=0.75 n=47 PF=1.127
total_ret=+0.017%; ETHUSDT thr=0.70 n=77 PF=1.322 total_ret=+0.072%.

Usage:
    python scripts/multi_horizon_ensemble.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

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

HORIZONS = [5, 10, 15, 30]
EXIT_HORIZON = 10  # exit mechanics stay fixed at the session's established horizon
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
THRESHOLDS_TO_TRY = [0.50, 0.55, 0.60, 0.65, 0.70]


def fit_horizon_models(train_feats: pd.DataFrame, train_close: pd.Series):
    models = {}
    for h in HORIZONS:
        y = build_labels(train_close, h, COST_THRESHOLD_PCT, direction="long")
        kept, _ = prune_redundant(train_feats, y, corr_threshold=0.9)
        fit_n = min(200_000, len(train_feats))
        fit_idx = train_feats.sample(n=fit_n, random_state=42).index
        model = Tier2RandomForestSignal(kept, n_estimators=80).fit(
            train_feats.loc[fit_idx], y.loc[fit_idx])
        models[h] = model
    return models


def ensemble_proba(models: dict, feats: pd.DataFrame) -> pd.Series:
    probas = [models[h].predict_proba(feats) for h in HORIZONS]
    return pd.concat(probas, axis=1).mean(axis=1)


def run_symbol(symbol: str):
    print("=" * 80)
    print(f"  MULTI-HORIZON ENSEMBLE — {symbol} (dedicated models per horizon, avg proba)")
    print("=" * 80)

    train_df = load_split(symbol, "train", verbose=True)
    train_feats = build_feature_matrix(train_df)
    print(f"Fitting {len(HORIZONS)} horizon-specific models ({HORIZONS})...")
    models = fit_horizon_models(train_feats, train_df["close"])

    val_df = load_split(symbol, "validation", verbose=True)
    val_feats = build_feature_matrix(val_df)
    val_close = val_df["close"]
    bh = buy_and_hold(val_close)
    print(f"Buy & hold over VALIDATION: {bh['total_return_pct']:+.2f}%")

    train_ens = ensemble_proba(models, train_feats)
    val_ens = ensemble_proba(models, val_feats)
    print(f"Ensemble proba on VALIDATION: min={val_ens.min():.4f} p50={val_ens.median():.4f} "
          f"p90={val_ens.quantile(0.9):.4f} max={val_ens.max():.4f}\n")

    close_arr = val_close.to_numpy()
    ema_slope_arr = val_feats["ema_slope_20"].to_numpy()
    ret_1_arr = val_feats["ret_1"].to_numpy()
    val_ens_arr = val_ens.to_numpy()

    print(f"{'threshold':>10}{'n_filtered_entries':>20}{'n_trades':>10}{'win%':>8}"
          f"{'PF':>8}{'total_ret%':>12}")
    print("-" * 70)
    for thresh in THRESHOLDS_TO_TRY:
        train_selected = train_ens > thresh
        if train_selected.sum() < 20:
            print(f"{thresh:>10.2f}{'(train pop < 20)':>20}")
            continue
        range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
        vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()

        filtered_mask = (
            (val_ens > thresh)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()

        m = simulate_trend_rescue(close_arr, filtered_mask, val_ens_arr, ema_slope_arr, ret_1_arr,
                                   DEFAULT_EXTENSION_CAP, confidence_weighted=False)
        if m.get("n_trades", 0) == 0:
            print(f"{thresh:>10.2f}{int(filtered_mask.sum()):>20}{'no trades':>10}")
            continue
        print(f"{thresh:>10.2f}{int(filtered_mask.sum()):>20}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
              f"{m['profit_factor']:>8.3f}{m['total_return_pct_of_capital']:>12.3f}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    args = parser.parse_args()
    for symbol in args.symbols.split(","):
        run_symbol(symbol)
    print("Baseline (single horizon=10 dedicated model, this session): "
          "BTCUSDT thr=0.75 n=47 PF=1.127 total_ret=+0.017%; "
          "ETHUSDT thr=0.70 n=77 PF=1.322 total_ret=+0.072%.")


if __name__ == "__main__":
    main()
