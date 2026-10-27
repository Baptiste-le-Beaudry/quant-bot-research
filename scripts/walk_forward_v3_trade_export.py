"""
scripts/walk_forward_v3_trade_export.py — Étape ⑦ of the user's "find more
positive-EV trades" plan: export every individual walk-forward TEST trade
under BASELINE_CANDIDATE_V3 (threshold=0.70+mandatory filter+dynamic
leverage, Experiment 28) in the SAME schema as Experiment 26's original
export (docs/walk_forward_trades_export.csv: symbol, fold, entry_time,
exit_time, raw_return, stop_distance, leverage_safe, was_stopped,
close_path), so the existing risk-sweep + Monte Carlo machinery
(scripts/walk_forward_risk_sweep.py) can be re-run unchanged on V3's much
larger trade population (544 vs the original 55) -- the user explicitly
asked for the risk sweep to be redone once the trade-frequency work
concluded, since the population composition has changed materially.

Resumable / one-fold-per-invocation via --max-folds, same proven pattern
as Experiments 28/30 (foreground calls, checkpoint CSV, cached price data).

Usage:
    python scripts/walk_forward_v3_trade_export.py --max-folds 1
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.walk_forward_engine import build_folds, SAFE_END, SYMBOLS
from scripts.walk_forward_threshold070_filter import (
    THRESHOLD, STOP_PCT_PERCENTILE, SAFETY_MARGIN, MAX_LEVERAGE_CAP, _load_full_cached,
)
from scripts.walk_forward_engine import fit_fold_model  # HORIZON=10 here matches V3 exactly, no patch needed

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def export_fold_symbol(symbol, train_df, test_df, model, train_feats_sym, fold_i):
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
    train_trades = build_trades_with_mae_mfe(
        train_close, train_filtered,
        train_feats_sym["ema_slope_20"].to_numpy(), train_feats_sym["ret_1"].to_numpy())
    if len(train_trades) < 10:
        return []
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)

    test_feats = build_feature_matrix(test_df)
    test_proba = model.predict_proba(test_feats)
    test_filtered = (
        (test_proba > THRESHOLD)
        & (test_feats["range_pos_60"] < range_pos_cut)
        & (test_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    test_close = test_df["close"].to_numpy()
    seq_trades = build_trades_with_mae_mfe(
        test_close, test_filtered,
        test_feats["ema_slope_20"].to_numpy(), test_feats["ret_1"].to_numpy())

    ACTIVATE_AT, TRAIL_DIST = 0.0063, 0.0080
    rows = []
    for t in seq_trades:
        i = t["entry_idx"]
        path = t["close_path"]
        peak, activated, was_stopped = -np.inf, False, False
        raw_return, exit_offset = None, len(path) - 1
        for j, x in enumerate(path):
            if x <= -protective:
                raw_return, was_stopped, exit_offset = -protective, True, j
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    raw_return, exit_offset = stop_level, j
                    break
        if raw_return is None:
            raw_return = path[-1]
        entry_time = test_df.index[i]
        exit_time = test_df.index[min(i + exit_offset, len(test_df) - 1)]
        rows.append({
            "symbol": symbol, "fold": fold_i, "entry_time": entry_time, "exit_time": exit_time,
            "raw_return": raw_return, "stop_distance": stop_distance, "leverage_safe": leverage,
            "was_stopped": was_stopped,
            "close_path": ";".join(f"{v:.8f}" for v in path),
        })
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-folds", type=int, default=1)
    args = parser.parse_args()

    full = {s: _load_full_cached(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)

    ckpt_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_v3_trades_export.csv")
    done_marker_path = ckpt_path + ".done_folds.txt"
    all_rows = []
    if os.path.exists(ckpt_path):
        prev = pd.read_csv(ckpt_path)
        all_rows = prev.to_dict("records")
    done_folds = set()
    if os.path.exists(done_marker_path):
        with open(done_marker_path) as f:
            done_folds = {int(x) for x in f.read().split() if x.strip()}
    if done_folds:
        print(f"Resuming: folds already exported = {sorted(done_folds)}")

    processed = 0
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        if fold_i in done_folds:
            print(f"FOLD {fold_i}/{len(folds)}: already done, skipping")
            continue
        if processed >= args.max_folds:
            print(f"Reached --max-folds={args.max_folds}, exiting cleanly.")
            break
        train_slices = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in SYMBOLS}
        test_slices = {s: full[s][(full[s].index >= train_end) & (full[s].index < test_end)] for s in SYMBOLS}
        model, train_feats = fit_fold_model(train_slices)
        fold_rows = []
        for symbol in SYMBOLS:
            fold_rows.extend(export_fold_symbol(symbol, train_slices[symbol], test_slices[symbol],
                                                 model, train_feats[symbol], fold_i))
        print(f"FOLD {fold_i}/{len(folds)}: exported {len(fold_rows)} trades")
        all_rows.extend(fold_rows)
        pd.DataFrame(all_rows).to_csv(ckpt_path, index=False)
        done_folds.add(fold_i)
        with open(done_marker_path, "w") as f:
            f.write(" ".join(str(x) for x in sorted(done_folds)))
        processed += 1

    remaining = [i for i in range(1, len(folds) + 1) if i not in done_folds]
    if remaining:
        print(f"\nFolds still remaining: {remaining} -- rerun to continue.")
    else:
        print(f"\nAll folds exported -> {ckpt_path} ({len(all_rows)} total trades)")


if __name__ == "__main__":
    main()
