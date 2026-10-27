"""
scripts/walk_forward_window_ratio.py — Experiment 43b: full walk-forward
validation of a window-ratio candidate surfaced by Experiment 43's screen
(window_ratio_sweep_validation.py). Horizon stays FIXED at 10 (the frozen
default) -- only the exit-window ratio (EXTENSION_CAP) changes, unlike
Experiment 30 which changed horizon+window together.

Derived from scripts/walk_forward_h20.py (Experiment 30's engine) with
the same two structural properties: HORIZON never changes here, and
mae_mfe_analysis's module globals are patched so nothing downstream
silently reuses the wrong window (the exact bug caught mid-Experiment 30).

Usage:
    python scripts/walk_forward_window_ratio.py --ratio 6 --max-folds 1
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
import scripts.mae_mfe_analysis as _mae_module
from scripts.walk_forward_engine import build_folds
from scripts.walk_forward_threshold070_filter import _load_full_cached

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10  # FROZEN -- Experiment 43's whole point is to isolate the window ratio from horizon.
THRESHOLD = 0.70
CAPITAL = 10_000.0
RISK_PCT = 0.01

ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0

HOLDOUT_START = {"BTCUSDT": pd.Timestamp("2025-03-28", tz="UTC"), "ETHUSDT": pd.Timestamp("2025-04-13", tz="UTC")}
SAFE_END = min(HOLDOUT_START.values())


def fit_fold_model(train_slices: dict):
    train_feats, train_labels = {}, {}
    for symbol, df in train_slices.items():
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    return model, train_feats


def run_fold_symbol(symbol, train_df, test_df, model, train_feats_sym, lookahead) -> dict:
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
    n_train = len(train_close)
    idxs = np.where(train_filtered)[0]
    idxs = idxs[idxs < n_train - lookahead - 1]
    if len(idxs) < 10:
        return {"n_trades": 0, "reason": "too few TRAIN trades to calibrate stop"}
    stop_distance = float(np.percentile(
        np.abs([(train_close[i:i + lookahead + 1] / train_close[i] - 1.0).min() for i in idxs]),
        STOP_PCT_PERCENTILE))

    test_feats = build_feature_matrix(test_df)
    test_proba = model.predict_proba(test_feats)
    test_filtered = (
        (test_proba > THRESHOLD)
        & (test_feats["range_pos_60"] < range_pos_cut)
        & (test_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    test_close = test_df["close"].to_numpy()
    n_test = len(test_close)

    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = CAPITAL * RISK_PCT

    pnls, n_forced = [], 0
    i = 0
    while i < n_test - lookahead - 1:
        if not test_filtered[i]:
            i += 1
            continue
        path = test_close[i:i + lookahead + 1] / test_close[i] - 1.0
        peak, activated, exit_ret = -np.inf, False, None
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
        i += HORIZON

    if not pnls:
        return {"n_trades": 0, "reason": "no TEST entries"}
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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratio", type=int, required=True, help="window ratio (max_holding_bars = ratio*HORIZON)")
    parser.add_argument("--max-folds", type=int, default=1)
    args = parser.parse_args()
    lookahead = args.ratio * HORIZON
    _mae_module.HORIZON = HORIZON
    _mae_module.LOOKAHEAD = lookahead

    print(f"HORIZON={HORIZON}min (frozen), ratio={args.ratio}x -> max hold {lookahead}min. Loading cached data...")
    full = {s: _load_full_cached(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)
    print(f"{len(folds)} walk-forward folds\n")

    ckpt_path = os.path.join(os.path.dirname(__file__), "..", "docs", f"walk_forward_ratio{args.ratio}_checkpoint.csv")
    all_rows = []
    done_folds = set()
    if os.path.exists(ckpt_path):
        prev = pd.read_csv(ckpt_path)
        all_rows = prev.to_dict("records")
        done_folds = {(int(r["fold"]), r["symbol"]) for r in all_rows}
        print(f"Resuming: {len(done_folds)} (fold,symbol) pairs already done")

    processed = 0
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        if all((fold_i, s) in done_folds for s in SYMBOLS):
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
            if (fold_i, symbol) in done_folds:
                continue
            r = run_fold_symbol(symbol, train_slices[symbol], test_slices[symbol], model, train_feats[symbol], lookahead)
            if r.get("n_trades", 0) == 0:
                print(f"  {symbol}: {r.get('reason', 'no trades')}")
            else:
                print(f"  {symbol}: n={r['n_trades']:>3} PF={r['profit_factor']:>7.3f} "
                      f"ret={r['total_return_pct']:>+7.3f}% DD={r['max_dd_pct']:>+7.3f}% "
                      f"win%={r['win_rate_pct']:>5.1f} stop={r['stop_distance_pct']:.2f}% "
                      f"forced_liq={r['n_forced_liq']}")
            all_rows.append({"fold": fold_i, "symbol": symbol,
                              "train_start": t0, "train_end": train_end, "test_end": test_end, **r})
            pd.DataFrame(all_rows).to_csv(ckpt_path, index=False)
        processed += 1

    final_done = {(int(r["fold"]), r["symbol"]) for r in all_rows}
    incomplete = [i for i in range(1, len(folds) + 1) if not all((i, s) in final_done for s in SYMBOLS)]
    if incomplete:
        print(f"\nFolds still remaining: {incomplete} -- rerun to continue.")
        return

    df_res = pd.DataFrame(all_rows)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", f"walk_forward_ratio{args.ratio}_raw.csv")
    df_res.to_csv(out_path, index=False)

    print("\n" + "=" * 100)
    print(f"  SUMMARY -- HORIZON=10min (frozen), window ratio={args.ratio}x ({lookahead}min max hold)")
    print("=" * 100)
    for symbol in SYMBOLS:
        sub = df_res[(df_res["symbol"] == symbol) & (df_res["n_trades"] > 0)]
        if len(sub) == 0:
            print(f"{symbol}: no fold produced trades")
            continue
        pf = sub["profit_factor"].replace([np.inf], np.nan).dropna()
        print(f"\n{symbol} ({len(sub)}/{len(folds)} folds with trades, total n_trades={sub['n_trades'].sum()}):")
        print(f"  mean PF={pf.mean():.3f}  median PF={pf.median():.3f}  %% folds PF>1: {(sub['profit_factor']>1).mean()*100:.1f}%")
        print(f"  total return summed across folds: {sub['total_return_pct'].sum():+.2f}%")
        print(f"  total forced liquidations across folds: {sub['n_forced_liq'].sum()}")
    print(f"\nRaw per-fold results saved -> {out_path}")


if __name__ == "__main__":
    main()
