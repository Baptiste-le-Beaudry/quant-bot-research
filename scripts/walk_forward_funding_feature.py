"""
scripts/walk_forward_funding_feature.py — walk-forward validation of
Experiment 18/20's funding-feature candidate, the strongest lead found
this session (improves both symbols frictionlessly AND under gap stress,
with only one narrow tail-risk caveat on BTC). Same 13-fold expanding
walk-forward engine as scripts/walk_forward_engine.py and
scripts/walk_forward_ev_filter.py, reporting BASELINE (no funding feature)
vs WITH funding_ma_3 side by side per fold, model refit from scratch each
fold with the funding feature computed from that fold's own available
funding history only (no lookahead -- funding_ma_3 uses merge_asof
direction="backward").

Usage:
    python scripts/walk_forward_funding_feature.py
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
from scripts.step27_funding_feature import load_funding_full, add_funding_feature
from scripts.walk_forward_engine import (
    SYMBOLS, THRESHOLD, ACTIVATE_AT, TRAIL_DIST, STOP_PCT_PERCENTILE, LEVERAGE,
    FEE_PER_SIDE, BASE_SLIP_PER_SIDE, CAPITAL, RISK_PCT, SAFE_END, HORIZON,
    build_folds,
)
from scripts.phase3_baseline import _load_full

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def resolve_return(path, stop_distance, leverage):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2


def simulate(returns, leverage) -> dict:
    pnls = np.array(returns) * CAPITAL * RISK_PCT * leverage
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3)}


def fit_fold_model(train_slices: dict, funding_full: dict, use_funding: bool):
    train_feats, train_labels = {}, {}
    for symbol, df in train_slices.items():
        feats = build_feature_matrix(df)
        if use_funding:
            feats = add_funding_feature(feats, funding_full[symbol])
        train_feats[symbol] = feats
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    return model, train_feats


def run_fold_symbol(symbol, train_df, test_df, model, train_feats_sym):
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

    test_feats = test_df["_feats"]
    test_proba = model.predict_proba(test_feats)
    test_filtered = (
        (test_proba > THRESHOLD)
        & (test_feats["range_pos_60"] < range_pos_cut)
        & (test_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    test_ema_slope = test_feats["ema_slope_20"].to_numpy()
    test_ret_1 = test_feats["ret_1"].to_numpy()
    test_close = test_df["_close"]
    seq_trades = build_trades_with_mae_mfe(test_close, test_filtered, test_ema_slope, test_ret_1)
    if len(seq_trades) == 0:
        return {"n_trades": 0, "reason": "no TEST entries"}

    leverage = LEVERAGE[symbol]
    returns = [resolve_return(t["close_path"], stop_distance, leverage) for t in seq_trades]
    return simulate(returns, leverage)


def main():
    print("Loading full 1-min history + full funding history for BTCUSDT/ETHUSDT...")
    full = {s: _load_full(s) for s in SYMBOLS}
    funding_full = {s: load_funding_full(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)
    print(f"{len(folds)} walk-forward folds\n")

    all_rows = []
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        print("=" * 100)
        print(f"  FOLD {fold_i}/{len(folds)}: TRAIN [{t0:%Y-%m-%d} -> {train_end:%Y-%m-%d}]  "
              f"TEST [{train_end:%Y-%m-%d} -> {test_end:%Y-%m-%d}]")
        print("=" * 100)
        train_slices = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in SYMBOLS}
        test_slices_raw = {s: full[s][(full[s].index >= train_end) & (full[s].index < test_end)] for s in SYMBOLS}

        for use_funding, tag in [(False, "BASE"), (True, "FUND")]:
            model, train_feats = fit_fold_model(train_slices, funding_full, use_funding)
            for symbol in SYMBOLS:
                test_df = test_slices_raw[symbol]
                test_feats = build_feature_matrix(test_df)
                if use_funding:
                    test_feats = add_funding_feature(test_feats, funding_full[symbol])
                test_wrapped = {"_feats": test_feats, "_close": test_df["close"].to_numpy()}
                r = run_fold_symbol(symbol, train_slices[symbol], test_wrapped, model, train_feats[symbol])
                if r.get("n_trades", 0) == 0:
                    print(f"  [{tag}] {symbol}: {r.get('reason', 'no trades')}")
                else:
                    print(f"  [{tag}] {symbol}: n={r['n_trades']:>3} PF={r['profit_factor']:>7.3f} "
                          f"ret={r['total_return_pct']:>+7.3f}%")
                all_rows.append({"fold": fold_i, "symbol": symbol, "variant": tag, **r})
        print()

    df_res = pd.DataFrame(all_rows)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_funding_raw.csv")
    df_res.to_csv(out_path, index=False)

    print("=" * 100)
    print("  WALK-FORWARD SUMMARY: baseline vs WITH funding feature")
    print("=" * 100)
    for symbol in SYMBOLS:
        for tag in ["BASE", "FUND"]:
            sub = df_res[(df_res["symbol"] == symbol) & (df_res["variant"] == tag) & (df_res["n_trades"] > 0)]
            if len(sub) == 0:
                print(f"{symbol} [{tag}]: no folds with trades")
                continue
            pf = sub["profit_factor"].replace([np.inf], np.nan)
            print(f"{symbol} [{tag}]: {len(sub)}/{len(folds)} folds w/ trades, mean PF={pf.mean():.3f} "
                  f"median PF={pf.median():.3f} %%folds PF>1={(sub['profit_factor']>1).mean()*100:.1f}% "
                  f"total_ret_summed={sub['total_return_pct'].sum():+.2f}%")

    print(f"\nRaw per-fold results saved -> {out_path}")


if __name__ == "__main__":
    main()
