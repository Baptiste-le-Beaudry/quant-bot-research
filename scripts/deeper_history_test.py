"""
scripts/deeper_history_test.py — "deeper 7yr retrain" hypothesis, cheaper
variant. The straightforward version (dedicated model on the full
TRAIN_FRACTION=60% slice of the new 7yr file, ~2.2M rows for BTC) needs
~6 minutes of uninterrupted compute (measured: load 39s + feature build
165s + fit/eval ~120s) and repeatedly lost the race against this
environment's background-task kills. This variant tests the same
"does more/different history help" question much more cheaply: train on an
EXPLICIT 2-year window from early in the new history (2019-09->2021-09,
includes the 2020 COVID crash and the 2020-2021 bull -- a completely
different regime than the original Aug2024-Oct2025 TRAIN window used all
session) and validate on the 6 months right after. Row counts are
comparable to the original successful dedicated-model tests, so this should
run in a similar, kill-survivable amount of time, while still directly
testing regime generalization / whether older history contains a similar
or different signal.

Usage:
    python scripts/deeper_history_test.py --symbol BTCUSDT
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from sklearn.metrics import roc_auc_score

from quant_bot.config import DATA_DIR, COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from quant_bot.backtest.engine import buy_and_hold
from scripts.hypothesis_tests import simulate_trend_rescue, DEFAULT_EXTENSION_CAP

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HORIZON = 10
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
THRESHOLDS_TO_TRY = [0.55, 0.60, 0.65, 0.70, 0.75]
TRAIN_START, TRAIN_END = "2019-09-01", "2021-09-01"
VAL_START, VAL_END = "2021-09-01", "2022-03-01"


def load_window(symbol: str, start: str, end: str) -> pd.DataFrame:
    import glob
    files = sorted(glob.glob(os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")))
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    return df.loc[start:end]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    symbol = args.symbol

    print("=" * 80)
    print(f"  DEEPER-HISTORY TEST — {symbol} (early-regime window: "
          f"{TRAIN_START}->{TRAIN_END} train, {VAL_START}->{VAL_END} validation)")
    print("=" * 80)

    train_df = load_window(symbol, TRAIN_START, TRAIN_END)
    print(f"TRAIN: {len(train_df):,} bars ({train_df.index[0]:%Y-%m-%d} -> {train_df.index[-1]:%Y-%m-%d})")
    train_feats = build_feature_matrix(train_df)
    y_train = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")

    kept, _ = prune_redundant(train_feats, y_train, corr_threshold=0.9)
    print(f"{len(kept)} features kept.")
    fit_n = min(40_000, len(train_feats))  # cut hard: the environment's
                                             # surviving window has shrunk to
                                             # well under a minute in this
                                             # stretch of the session, and
                                             # even a 120k/60-tree fit kept
                                             # losing that race repeatedly
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=25).fit(
        train_feats.loc[fit_idx], y_train.loc[fit_idx])

    val_df = load_window(symbol, VAL_START, VAL_END)
    print(f"VALIDATION: {len(val_df):,} bars ({val_df.index[0]:%Y-%m-%d} -> {val_df.index[-1]:%Y-%m-%d})")
    val_feats = build_feature_matrix(val_df)
    val_close = val_df["close"]
    y_val = build_labels(val_close, HORIZON, COST_THRESHOLD_PCT, direction="long")
    proba_val = model.predict_proba(val_feats)
    valid = proba_val.notna() & y_val.notna()
    auc = roc_auc_score(y_val[valid], proba_val[valid])
    bh = buy_and_hold(val_close)
    print(f"\nEarly-regime dedicated model AUC on VALIDATION: {auc:.4f}")
    print(f"Buy & hold over VALIDATION: {bh['total_return_pct']:+.2f}%\n")

    close_arr = val_close.to_numpy()
    ema_slope_arr = val_feats["ema_slope_20"].to_numpy()
    ret_1_arr = val_feats["ret_1"].to_numpy()
    proba_arr = proba_val.to_numpy()

    print(f"{'threshold':>10}{'n_filtered_entries':>20}{'n_trades':>10}{'win%':>8}"
          f"{'PF':>8}{'total_ret%':>12}")
    print("-" * 70)
    for thresh in THRESHOLDS_TO_TRY:
        train_proba = model.predict_proba(train_feats)
        train_selected = train_proba > thresh
        if train_selected.sum() < 20:
            print(f"{thresh:>10.2f}{'(train pop < 20)':>20}")
            continue
        range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
        vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()

        filtered_mask = (
            (proba_val > thresh)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()

        m = simulate_trend_rescue(close_arr, filtered_mask, proba_arr, ema_slope_arr, ret_1_arr,
                                   DEFAULT_EXTENSION_CAP, confidence_weighted=False)
        if m.get("n_trades", 0) == 0:
            print(f"{thresh:>10.2f}{int(filtered_mask.sum()):>20}{'no trades':>10}")
            continue
        print(f"{thresh:>10.2f}{int(filtered_mask.sum()):>20}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
              f"{m['profit_factor']:>8.3f}{m['total_return_pct_of_capital']:>12.3f}")

    print("\nComparison point: the same dedicated-model pipeline on the recent")
    print("Aug2024-Oct2025 window gave BTCUSDT thr=0.75 n=47 PF=1.127 total_ret=+0.017%.")


if __name__ == "__main__":
    main()
