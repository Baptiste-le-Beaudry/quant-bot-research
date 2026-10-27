"""
scripts/walk_forward_trade_export.py — Phase A of the risk-per-trade sweep
protocol: runs the 13-fold walk-forward ONCE (same engine as
walk_forward_dynamic_leverage.py -- dynamic, TRAIN-calibrated leverage
ceiling per fold, same entries/exits as BASELINE_CANDIDATE_V2) and saves
EVERY individual TEST trade (not just fold aggregates) to a CSV:
  symbol, fold, entry_time, exit_time, raw_return (post-cost, BEFORE
  notional/leverage -- a plain fraction), stop_distance (that fold's own
  TRAIN-calibrated value), leverage_safe (that fold's dynamic ceiling),
  was_stopped (bool, whether the protective stop/liquidation level was
  the exit reason).

This is the expensive, one-time step (one model fit per fold, ~45-90min).
Everything downstream (risk-per-trade sweep, compounding equity curves,
Monte Carlo, stress testing) reads this CSV and runs in seconds --
built as a separate script (walk_forward_risk_sweep.py) specifically so
the risk-sweep logic can be iterated on freely without re-paying this cost.

Usage:
    python scripts/walk_forward_trade_export.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.walk_forward_engine import (
    SYMBOLS, THRESHOLD, ACTIVATE_AT, TRAIL_DIST, STOP_PCT_PERCENTILE,
    FEE_PER_SIDE, BASE_SLIP_PER_SIDE, SAFE_END, build_folds, fit_fold_model,
)
from scripts.phase3_baseline import _load_full

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0


def resolve(path, stop_distance, liq_move):
    """Returns (raw_return, was_stopped, exit_offset). protective =
    min(stop_distance, liq_move) -- with dynamic leverage sized so
    liq_move >= stop_distance (SAFETY_MARGIN=0.75 buffer), the voluntary
    stop should almost always bind first; kept general in case a fold's
    cap (MAX_LEVERAGE_CAP) forces liq_move tighter than stop_distance.
    exit_offset is the bar index (within path) the trade actually closed
    at -- path itself is always the full fixed-length lookahead window
    (build_trades_with_mae_mfe does not truncate it), so this must be
    tracked explicitly rather than inferred from len(path)."""
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for j, x in enumerate(path):
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, True, j
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, False, j
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, False, len(path) - 1


def run_fold_symbol(symbol, fold_i, train_df, test_df, model, train_feats_sym):
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    if train_selected_sym.sum() < 20:
        return []
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
        return []
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
    leverage_safe = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage_safe

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
        return []

    timestamps = test_df.index
    rows = []
    for t in seq_trades:
        i = t["entry_idx"]
        path = t["close_path"]
        ret, was_stopped, exit_offset = resolve(path, stop_distance, liq_move)
        exit_i = min(i + exit_offset, len(test_close) - 1)
        rows.append({
            "symbol": symbol, "fold": fold_i,
            "entry_time": timestamps[i], "exit_time": timestamps[exit_i],
            "raw_return": ret, "stop_distance": stop_distance,
            "leverage_safe": leverage_safe, "was_stopped": was_stopped,
            # Full 51-bar relative-return path, semicolon-joined -- lets Phase B
            # (walk_forward_risk_sweep.py) re-resolve exits under stress
            # (gap/slippage/latency) without needing to reload any price data
            # or refit any model, per the Phase A/B split's whole purpose.
            "close_path": ";".join(f"{x:.8f}" for x in path),
        })
    return rows


def main():
    print("Loading full 1-min history for BTCUSDT/ETHUSDT...")
    full = {s: _load_full(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)
    print(f"{len(folds)} walk-forward folds\n")

    all_rows = []
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        print(f"FOLD {fold_i}/{len(folds)}: TRAIN [{t0:%Y-%m-%d} -> {train_end:%Y-%m-%d}]  "
              f"TEST [{train_end:%Y-%m-%d} -> {test_end:%Y-%m-%d}]")
        train_slices = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in SYMBOLS}
        test_slices = {s: full[s][(full[s].index >= train_end) & (full[s].index < test_end)] for s in SYMBOLS}
        model, train_feats = fit_fold_model(train_slices)

        for symbol in SYMBOLS:
            rows = run_fold_symbol(symbol, fold_i, train_slices[symbol], test_slices[symbol],
                                    model, train_feats[symbol])
            print(f"  {symbol}: {len(rows)} trades exported")
            all_rows.extend(rows)

    df_out = pd.DataFrame(all_rows).sort_values("entry_time").reset_index(drop=True)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_trades_export.csv")
    df_out.to_csv(out_path, index=False)
    print(f"\n{len(df_out)} total trades exported -> {out_path}")
    print(df_out.groupby("symbol").agg(n=("raw_return", "count"), win_rate=("raw_return", lambda s: (s > 0).mean() * 100)))


if __name__ == "__main__":
    main()
