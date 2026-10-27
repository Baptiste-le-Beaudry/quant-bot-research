"""
scripts/walk_forward_threshold070_stress.py — stress test (Étape mandatory
before KEEP) for the threshold=0.70+mandatory-filter candidate validated in
Experiment 28 (docs/walk_forward_threshold070_raw.csv: ~10x more trades than
the threshold=0.75 baseline on BOTH symbols, higher median PF on both, zero
forced liquidations). Reuses the SAME per-fold entry selection (model fit,
range_pos_60/realized_vol_30 filter, dynamic leverage) as
walk_forward_h20.py, but instead of resolving each trade's
exit once, resolves it under multiple stress scenarios FROM THE SAME
close_path array already produced by build_trades_with_mae_mfe (Experiment 1's
established dimensions: slippage multiplier, gap, entry latency) -- no
second export phase needed since close_path is already available per trade
in-memory during the same walk.

Resumable / one-fold-per-invocation via --max-folds, same as
walk_forward_h20.py (this environment's background tasks get
killed unpredictably around 4-6min; per-fold foreground runs proved
reliable).

Usage:
    python scripts/walk_forward_threshold070_stress.py --max-folds 1
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.walk_forward_engine import build_folds, SAFE_END, SYMBOLS
from scripts.walk_forward_h20 import (
    THRESHOLD, ACTIVATE_AT, TRAIL_DIST, STOP_PCT_PERCENTILE, SAFETY_MARGIN, MAX_LEVERAGE_CAP,
    FEE_PER_SIDE, BASE_SLIP_PER_SIDE, CAPITAL, RISK_PCT, _load_full_cached, fit_fold_model,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCENARIOS = [
    ("frictionless", dict()),
    ("slippage 2x", dict(slip_mult=2.0)),
    ("slippage 3x", dict(slip_mult=3.0)),
    ("gap 0.10%", dict(gap_extra=0.0010)),
    ("gap 0.25%", dict(gap_extra=0.0025)),
    ("gap 0.50%", dict(gap_extra=0.0050)),
    ("latency 1min", dict(entry_delay=1)),
    ("latency 2min", dict(entry_delay=2)),
    ("WORST CASE (slip2x+gap.25%+delay1)", dict(slip_mult=2.0, gap_extra=0.0025, entry_delay=1)),
]


def resolve_stressed(path: np.ndarray, protective: float,
                      gap_extra: float = 0.0, slip_mult: float = 1.0, entry_delay: int = 0):
    if entry_delay > 0:
        if entry_delay >= len(path) - 1:
            return None
        new_entry = path[entry_delay]
        path = (1 + path[entry_delay:]) / (1 + new_entry) - 1.0
    cost = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - gap_extra - cost
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - gap_extra - cost
    return path[-1] - cost


def run_fold_symbol_stress(symbol, train_df, test_df, model, train_feats_sym):
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    if train_selected_sym.sum() < 20:
        return None
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
        return None
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
    if len(seq_trades) == 0:
        return None

    notional = CAPITAL * RISK_PCT
    out = {}
    for label, kwargs in SCENARIOS:
        pnls = []
        for t in seq_trades:
            ret = resolve_stressed(t["close_path"], protective, **kwargs)
            if ret is not None:
                pnls.append(ret * notional * leverage)
        if not pnls:
            continue
        pnls = np.array(pnls)
        wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
        out[label] = {"n": len(pnls), "pf": pf, "total_ret_pct": pnls.sum() / CAPITAL * 100}
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-folds", type=int, default=1)
    args = parser.parse_args()

    full = {s: _load_full_cached(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)

    ckpt_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_threshold070_stress_checkpoint.csv")
    all_rows = []
    done = set()
    if os.path.exists(ckpt_path):
        prev = pd.read_csv(ckpt_path)
        all_rows = prev.to_dict("records")
        done = {(int(r["fold"]), r["symbol"]) for r in all_rows}
        print(f"Resuming: {len(done)} (fold,symbol) pairs done")

    processed = 0
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        if all((fold_i, s) in done for s in SYMBOLS):
            print(f"FOLD {fold_i}/{len(folds)}: already done, skipping")
            continue
        if processed >= args.max_folds:
            print(f"Reached --max-folds={args.max_folds}, exiting cleanly.")
            break
        train_slices = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in SYMBOLS}
        test_slices = {s: full[s][(full[s].index >= train_end) & (full[s].index < test_end)] for s in SYMBOLS}
        model, train_feats = fit_fold_model(train_slices)
        print(f"FOLD {fold_i}/{len(folds)}: TEST [{train_end:%Y-%m-%d} -> {test_end:%Y-%m-%d}]")
        for symbol in SYMBOLS:
            if (fold_i, symbol) in done:
                continue
            r = run_fold_symbol_stress(symbol, train_slices[symbol], test_slices[symbol],
                                        model, train_feats[symbol])
            row = {"fold": fold_i, "symbol": symbol}
            if r:
                for label, m in r.items():
                    row[f"{label}__n"] = m["n"]
                    row[f"{label}__pf"] = m["pf"]
                    row[f"{label}__ret"] = m["total_ret_pct"]
                print(f"  {symbol}: frictionless n={r.get('frictionless',{}).get('n')} "
                      f"pf={r.get('frictionless',{}).get('pf', float('nan')):.3f}  |  "
                      f"worst n={r.get('WORST CASE (slip2x+gap.25%+delay1)',{}).get('n')} "
                      f"pf={r.get('WORST CASE (slip2x+gap.25%+delay1)',{}).get('pf', float('nan')):.3f}")
            else:
                print(f"  {symbol}: no trades")
            all_rows.append(row)
            pd.DataFrame(all_rows).to_csv(ckpt_path, index=False)
        processed += 1

    final_done = {(int(r["fold"]), r["symbol"]) for r in all_rows}
    incomplete = [i for i in range(1, len(folds) + 1) if not all((i, s) in final_done for s in SYMBOLS)]
    if incomplete:
        print(f"\nFolds still remaining: {incomplete} -- rerun to continue.")
        return

    df_res = pd.DataFrame(all_rows)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_threshold070_stress_raw.csv")
    df_res.to_csv(out_path, index=False)

    print("\n" + "=" * 110)
    print("  STRESS SUMMARY -- threshold=0.70 + mandatory filter")
    print("=" * 110)
    for symbol in SYMBOLS:
        sub = df_res[df_res["symbol"] == symbol]
        print(f"\n{symbol}:")
        for label, _ in SCENARIOS:
            ncol, pfcol, retcol = f"{label}__n", f"{label}__pf", f"{label}__ret"
            if ncol not in sub.columns:
                continue
            n_total = sub[ncol].sum()
            ret_total = sub[retcol].sum()
            pf_vals = sub[pfcol].replace([np.inf], np.nan).dropna()
            print(f"  {label:<38} n={n_total:>5.0f}  total_ret={ret_total:>+8.2f}%  "
                  f"mean_PF={pf_vals.mean():.3f}  median_PF={pf_vals.median():.3f}")
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
