"""
scripts/walk_forward_threshold070_filter.py — Experiment 28: walk-forward
validation of the ONE hypothesis produced by Experiment 27's missed-winners
analysis: lower THRESHOLD from 0.75 to 0.70 while KEEPING the existing
range_pos_60/realized_vol_30 filter mandatory (cutoffs recomputed per fold
on the new, broader TRAIN-selected population -- same TRAIN-only discipline
as scripts/walk_forward_engine.py). Everything else (trailing 0.63%/0.80%,
p90 protective stop, dynamic leverage per fold) is FROZEN, unchanged from
walk_forward_engine.py -- this isolates the single change: does keeping the
filter mandatory let us safely recover some of the 0.70-0.75 band that
Experiment 8 correctly rejected recovering via a BLANKET threshold drop
(no filter requirement)?

This is scripts/walk_forward_engine.py with THRESHOLD=0.70 as the only
substantive change (duplicated rather than parameterized, so the frozen
baseline script stays untouched and comparable).

Usage:
    python scripts/walk_forward_threshold070_filter.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import _load_full
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.walk_forward_engine import build_folds, fit_fold_model

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.70  # the ONLY change vs walk_forward_engine.py (was 0.75)
EXTENSION_CAP = 40
LOOKAHEAD = HORIZON + EXTENSION_CAP
CAPITAL = 10_000.0
RISK_PCT = 0.01

ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75  # Experiment 23's dynamic-leverage fix -- NOT the frozen 12.1x/9.9x constants,
MAX_LEVERAGE_CAP = 30.0  # which were calibrated for the threshold=0.75 stop distribution and produced
                          # spurious forced liquidations here once threshold=0.70 shifts stop_distance.
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST

INITIAL_TRAIN_MONTHS = 24
TEST_MONTHS = 3
STEP_MONTHS = 3

HOLDOUT_START = {"BTCUSDT": pd.Timestamp("2025-03-28", tz="UTC"), "ETHUSDT": pd.Timestamp("2025-04-13", tz="UTC")}
SAFE_END = min(HOLDOUT_START.values())


def run_fold_symbol(symbol: str, train_df: pd.DataFrame, test_df: pd.DataFrame, model, train_feats_sym) -> dict:
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    if train_selected_sym.sum() < 20:
        return {"n_trades": 0, "reason": "train-selected population < 20"}
    range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
    vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

    train_close = train_df["close"].to_numpy()
    train_filtered = (
        (train_proba_sym > THRESHOLD)
        & (train_feats_sym["range_pos_60"] < range_pos_cut)
        & (train_feats_sym["realized_vol_30"] > vol_cut)
    ).to_numpy()
    train_ema_slope = train_feats_sym["ema_slope_20"].to_numpy()
    train_ret_1 = train_feats_sym["ret_1"].to_numpy()
    train_trades = build_trades_with_mae_mfe(train_close, train_filtered, train_ema_slope, train_ret_1)
    if len(train_trades) < 10:
        return {"n_trades": 0, "reason": "too few TRAIN trades to calibrate stop"}
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))

    test_feats = build_feature_matrix(test_df)
    test_proba = model.predict_proba(test_feats)
    test_filtered = (
        (test_proba > THRESHOLD)
        & (test_feats["range_pos_60"] < range_pos_cut)
        & (test_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    test_ema_slope = test_feats["ema_slope_20"].to_numpy()
    test_ret_1 = test_feats["ret_1"].to_numpy()
    test_close = test_df["close"].to_numpy()

    seq_trades = build_trades_with_mae_mfe(test_close, test_filtered, test_ema_slope, test_ret_1)
    if len(seq_trades) == 0:
        return {"n_trades": 0, "reason": "no TEST entries"}

    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = CAPITAL * RISK_PCT

    pnls, n_forced = [], 0
    for t in seq_trades:
        path = t["close_path"]
        peak, activated = -np.inf, False
        exit_ret = None
        for x in path:
            if x <= -protective:
                exit_ret = -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                n_forced += int(liq_move <= stop_distance)
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    exit_ret = stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                    break
        if exit_ret is None:
            exit_ret = path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        pnls.append(exit_ret * notional * leverage)

    pnls = np.array(pnls)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    return {
        "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
        "max_dd_pct": round(float(dd.min() * 100), 3),
        "win_rate_pct": round((pnls > 0).mean() * 100, 1) if len(pnls) else None,
        "stop_distance_pct": round(stop_distance * 100, 3),
        "leverage": round(leverage, 2),
        "n_forced_liq": n_forced,
    }


CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "_full_data_cache")


def _load_full_cached(symbol: str) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}_full.pkl")
    if os.path.exists(cache_path):
        return pd.read_pickle(cache_path)
    df = _load_full(symbol)
    df.to_pickle(cache_path)
    return df


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-folds", type=int, default=1,
                         help="process at most this many NEW folds this invocation, then exit "
                              "(keeps each run short enough to survive this environment's kills)")
    args = parser.parse_args()

    print(f"THRESHOLD={THRESHOLD} (vs 0.75 baseline) -- filter still mandatory. Loading full history (cached)...")
    full = {s: _load_full_cached(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)
    print(f"{len(folds)} walk-forward folds\n")

    ckpt_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_threshold070_checkpoint.csv")
    all_rows = []
    done_folds = set()
    if os.path.exists(ckpt_path):
        prev = pd.read_csv(ckpt_path)
        all_rows = prev.to_dict("records")
        done_folds = {(int(r["fold"]), r["symbol"]) for r in all_rows}
        print(f"Resuming: {len(done_folds)} (fold,symbol) pairs already done in {ckpt_path}")

    folds_processed_this_run = 0
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        if all((fold_i, s) in done_folds for s in SYMBOLS):
            print(f"FOLD {fold_i}/{len(folds)}: already done, skipping")
            continue
        if folds_processed_this_run >= args.max_folds:
            print(f"Reached --max-folds={args.max_folds} new folds this invocation, exiting cleanly.")
            break
        train_slices = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in SYMBOLS}
        test_slices = {s: full[s][(full[s].index >= train_end) & (full[s].index < test_end)] for s in SYMBOLS}
        model, train_feats = fit_fold_model(train_slices)

        print(f"FOLD {fold_i}/{len(folds)}: TEST [{train_end:%Y-%m-%d} -> {test_end:%Y-%m-%d}]")
        for symbol in SYMBOLS:
            if (fold_i, symbol) in done_folds:
                print(f"  {symbol}: already done, skipping")
                continue
            r = run_fold_symbol(symbol, train_slices[symbol], test_slices[symbol], model, train_feats[symbol])
            if r.get("n_trades", 0) == 0:
                print(f"  {symbol}: {r.get('reason', 'no trades')}")
            else:
                print(f"  {symbol}: n={r['n_trades']:>3} PF={r['profit_factor']:>7.3f} "
                      f"ret={r['total_return_pct']:>+7.3f}% DD={r['max_dd_pct']:>+7.3f}% "
                      f"win%={r['win_rate_pct']:>5.1f} stop={r['stop_distance_pct']:.2f}% "
                      f"forced_liq={r['n_forced_liq']}")
            all_rows.append({"fold": fold_i, "symbol": symbol,
                              "train_start": t0, "train_end": train_end, "test_end": test_end, **r})
            pd.DataFrame(all_rows).to_csv(ckpt_path, index=False)  # checkpoint after every symbol/fold
        folds_processed_this_run += 1

    final_done = {(int(r["fold"]), r["symbol"]) for r in all_rows}
    incomplete = [i for i in range(1, len(folds) + 1) if not all((i, s) in final_done for s in SYMBOLS)]
    if incomplete:
        print(f"\nFolds still remaining: {incomplete} -- rerun this script to continue.")
        return

    df_res = pd.DataFrame(all_rows)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_threshold070_raw.csv")
    df_res.to_csv(out_path, index=False)

    print("\n" + "=" * 100)
    print("  SUMMARY -- THRESHOLD=0.70 + mandatory filter")
    print("=" * 100)
    for symbol in SYMBOLS:
        sub = df_res[(df_res["symbol"] == symbol) & (df_res["n_trades"] > 0)]
        if len(sub) == 0:
            print(f"{symbol}: no fold produced trades")
            continue
        pf = sub["profit_factor"].replace([np.inf], np.nan).dropna()
        print(f"\n{symbol} ({len(sub)}/{len(folds)} folds with trades, total n_trades={sub['n_trades'].sum()}):")
        print(f"  mean PF={pf.mean():.3f}  median PF={pf.median():.3f}  %% folds PF>1: {(sub['profit_factor']>1).mean()*100:.1f}%")
        print(f"  worst fold PF={sub['profit_factor'].min():.3f}  best fold PF={sub['profit_factor'].max():.3f}")
        print(f"  total return summed across folds: {sub['total_return_pct'].sum():+.2f}%")
        print(f"  total forced liquidations across folds: {sub['n_forced_liq'].sum()}")

    print(f"\nRaw per-fold results saved -> {out_path}")


if __name__ == "__main__":
    main()
