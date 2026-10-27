"""
scripts/walk_forward_dynamic_leverage.py — fixes the structural problem
found in Experiment 22: the registered leverage (12.1x ETH / 9.9x BTC) is
a constant frozen at whatever the ONE fixed VALIDATION split's stop
distance happened to be (4.69%/3.68%). Across the walk-forward's 13 folds,
stop_distance ranges 3.9%-15.4%, and a frozen leverage drifts in and out
of the forced-liquidation zone as a result (75% of fold x symbol
combinations were structurally exposed at the frozen leverage).

This recomputes leverage EVERY FOLD from that fold's own TRAIN-calibrated
stop_distance, using the exact same formula already used everywhere else
this session (SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance,
confirmed correct in Experiment 6 -- this IS the "zero forced liquidation"
ceiling, not "2x" it). Reports BOTH the static-leverage walk-forward
(reusing docs/walk_forward_raw.csv's saved numbers, not re-run) and this
new dynamic-leverage version side by side, plus the forced-liquidation
zone status per fold (same check as Experiment 22) to confirm the fix
actually closes the gap.

Usage:
    python scripts/walk_forward_dynamic_leverage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from quant_bot.config import COST_THRESHOLD_PCT
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.walk_forward_engine import (
    SYMBOLS, THRESHOLD, ACTIVATE_AT, TRAIL_DIST, STOP_PCT_PERCENTILE,
    FEE_PER_SIDE, BASE_SLIP_PER_SIDE, CAPITAL, RISK_PCT, SAFE_END, HORIZON,
    build_folds, fit_fold_model,
)
from scripts.phase3_baseline import _load_full

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0  # sanity cap: a fold with a very tight stop (e.g. <1.25%) would otherwise
                          # imply an absurd >30x from the raw formula alone -- cap it, don't extrapolate blindly


def resolve_return(path, stop_distance, leverage):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    forced = liq_move <= stop_distance
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, forced
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, False
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, False


def simulate(returns_forced) -> dict:
    if not returns_forced:
        return {"n_trades": 0}
    rets = np.array([r for r, _ in returns_forced])
    forced_flags = [f for _, f in returns_forced]
    pnls = rets * CAPITAL * RISK_PCT  # leverage already folded into notional by caller via rets scaling? -- see caller
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
            "n_forced_liq": int(sum(forced_flags))}


def run_fold_symbol_dynamic(symbol, train_df, test_df, model, train_feats_sym):
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

    # THE FIX: leverage re-derived from THIS fold's own stop_distance, not a frozen constant.
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)

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

    returns_forced = []
    for t in seq_trades:
        ret, forced = resolve_return(t["close_path"], stop_distance, leverage)
        returns_forced.append((ret * leverage, forced))  # fold leverage into the return itself
    r = simulate(returns_forced)
    r["leverage"] = round(leverage, 2)
    r["stop_distance_pct"] = round(stop_distance * 100, 3)
    return r


def main():
    print("Loading full 1-min history for BTCUSDT/ETHUSDT...")
    full = {s: _load_full(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)
    print(f"{len(folds)} walk-forward folds\n")

    static_df = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_raw.csv"))

    all_rows = []
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        print("=" * 100)
        print(f"  FOLD {fold_i}/{len(folds)}: TRAIN [{t0:%Y-%m-%d} -> {train_end:%Y-%m-%d}]  "
              f"TEST [{train_end:%Y-%m-%d} -> {test_end:%Y-%m-%d}]")
        print("=" * 100)
        train_slices = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in SYMBOLS}
        test_slices = {s: full[s][(full[s].index >= train_end) & (full[s].index < test_end)] for s in SYMBOLS}
        model, train_feats = fit_fold_model(train_slices)

        for symbol in SYMBOLS:
            r = run_fold_symbol_dynamic(symbol, train_slices[symbol], test_slices[symbol],
                                         model, train_feats[symbol])
            static_row = static_df[(static_df["fold"] == fold_i) & (static_df["symbol"] == symbol)]
            static_forced = static_row["n_forced_liq"].values[0] if len(static_row) and pd.notna(static_row["n_forced_liq"].values[0]) else None

            if r.get("n_trades", 0) == 0:
                print(f"  {symbol}: {r.get('reason', 'no trades')}")
            else:
                print(f"  {symbol}: DYNAMIC lev={r['leverage']}x (stop={r['stop_distance_pct']}%) "
                      f"n={r['n_trades']:>3} PF={r['profit_factor']:>7.3f} "
                      f"ret={r['total_return_pct']:>+7.3f}% forced_liq={r['n_forced_liq']}"
                      f"  |  static forced_liq was: {static_forced}")
            all_rows.append({"fold": fold_i, "symbol": symbol, **r, "static_forced_liq": static_forced})
        print()

    df_res = pd.DataFrame(all_rows)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_dynamic_leverage_raw.csv")
    df_res.to_csv(out_path, index=False)

    print("=" * 100)
    print("  SUMMARY: dynamic leverage vs static leverage")
    print("=" * 100)
    for symbol in SYMBOLS:
        sub = df_res[(df_res["symbol"] == symbol) & (df_res["n_trades"] > 0)]
        static_sub = static_df[(static_df["symbol"] == symbol) & (static_df["n_trades"] > 0)]
        if len(sub) == 0:
            continue
        pf = sub["profit_factor"].replace([np.inf], np.nan)
        static_pf = static_sub["profit_factor"].replace([np.inf], np.nan)
        print(f"\n{symbol}:")
        print(f"  DYNAMIC: {len(sub)} folds, mean PF={pf.mean():.3f} median PF={pf.median():.3f} "
              f"total_ret_summed={sub['total_return_pct'].sum():+.2f}% "
              f"total_forced_liq={sub['n_forced_liq'].sum():.0f} "
              f"leverage_range=[{sub['leverage'].min():.1f}x, {sub['leverage'].max():.1f}x]")
        print(f"  STATIC:  {len(static_sub)} folds, mean PF={static_pf.mean():.3f} median PF={static_pf.median():.3f} "
              f"total_ret_summed={static_sub['total_return_pct'].sum():+.2f}% "
              f"total_forced_liq={static_sub['n_forced_liq'].sum():.0f} (frozen leverage)")

    print(f"\nRaw per-fold results saved -> {out_path}")


if __name__ == "__main__":
    main()
