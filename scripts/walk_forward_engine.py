"""
scripts/walk_forward_engine.py — Étape 22 (walk-forward), pulled ahead of
entry/exit optimization per the user's own explicit revision (research
plan section 37): several parameters (protective-stop percentile, trailing
activate/distance across two rounds, leverage) have already been tuned
sequentially on the SAME fixed VALIDATION window this session — a real
validation-overfitting risk the plan flags directly. No walk-forward engine
existed anywhere in this codebase before this file; every prior backtest
(1-min and H1) used one fixed chronological 60/20/20 split.

Design: EXPANDING TRAIN window (matches the plan's own example: 24mo,
27mo, 30mo, ... TRAIN, each followed by a 3-month TEST fold), stepping the
TEST window forward by 3 months each time. All folds stay strictly within
[data_start, min(BTC HOLDOUT_start, ETH HOLDOUT_start)] -- HOLDOUT is never
touched, per the master rule.

Per fold, EVERYTHING is (re)computed from that fold's TRAIN slice ONLY:
  - features + label
  - model fit (BTC+ETH jointly trained, same architecture as
    BASELINE_CANDIDATE_V2)
  - entry-filter cutoffs (range_pos_60/realized_vol_30, TRAIN-selected pop)
  - protective-stop MAE percentile (p90) -- THIS FIXES the methodological
    gap noted in docs/research_plan_status.md: earlier scripts this session
    computed the stop distance from VALIDATION's own trades (mildly
    self-referential); here it's computed from TRAIN only and then applied,
    unchanged, to that fold's TEST period.
The exit rule itself (trailing activate=+0.63%, trail=0.80% -- V2) and
leverage (ETH 12.1x, BTC 9.9x) are FROZEN constants, never re-tuned per
fold -- a walk-forward that re-optimized parameters per fold would just be
overfitting on a rolling basis instead of a single window.

Usage:
    python scripts/walk_forward_engine.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR, COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import _load_full
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
EXTENSION_CAP = 40
LOOKAHEAD = HORIZON + EXTENSION_CAP
CAPITAL = 10_000.0
RISK_PCT = 0.01

# BASELINE_CANDIDATE_V2, frozen (docs/research_plan_status.md) -- NOT re-tuned per fold.
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST

INITIAL_TRAIN_MONTHS = 24
TEST_MONTHS = 3
STEP_MONTHS = 3

# HOLDOUT boundaries (docs/research_plan_status.md Test 0.2) -- folds must never cross these.
HOLDOUT_START = {"BTCUSDT": pd.Timestamp("2025-03-28", tz="UTC"), "ETHUSDT": pd.Timestamp("2025-04-13", tz="UTC")}
SAFE_END = min(HOLDOUT_START.values())


def build_folds(data_start: pd.Timestamp, safe_end: pd.Timestamp) -> list:
    folds = []
    train_end = data_start + pd.DateOffset(months=INITIAL_TRAIN_MONTHS)
    while True:
        test_end = train_end + pd.DateOffset(months=TEST_MONTHS)
        if test_end > safe_end:
            break
        folds.append((data_start, train_end, test_end))
        train_end = train_end + pd.DateOffset(months=STEP_MONTHS)
    return folds


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


def run_fold_symbol(symbol: str, train_df: pd.DataFrame, test_df: pd.DataFrame, model, train_feats_sym) -> dict:
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    if train_selected_sym.sum() < 20:
        return {"n_trades": 0, "reason": "train-selected population < 20"}
    range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
    vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

    # Protective-stop MAE percentile computed on TRAIN's own filtered entries (the fix).
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

    # Apply frozen rule to TEST fold.
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

    leverage = LEVERAGE[symbol]
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = CAPITAL * RISK_PCT

    pnls, n_forced = [], 0
    for t in seq_trades:
        i = t["entry_idx"]
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
        "n_forced_liq": n_forced,
    }


def main():
    print("Loading full 1-min history for BTCUSDT/ETHUSDT...")
    full = {s: _load_full(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())  # both symbols must have data
    print(f"Common data start: {data_start:%Y-%m-%d}, safe end (min HOLDOUT start): {SAFE_END:%Y-%m-%d}")

    folds = build_folds(data_start, SAFE_END)
    print(f"{len(folds)} walk-forward folds "
          f"(expanding TRAIN from {INITIAL_TRAIN_MONTHS}mo, {TEST_MONTHS}mo TEST, {STEP_MONTHS}mo step)\n")

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
        print()

    df_res = pd.DataFrame(all_rows)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_raw.csv")
    df_res.to_csv(out_path, index=False)

    print("=" * 100)
    print("  WALK-FORWARD SUMMARY")
    print("=" * 100)
    for symbol in SYMBOLS:
        sub = df_res[(df_res["symbol"] == symbol) & (df_res["n_trades"] > 0)]
        if len(sub) == 0:
            print(f"{symbol}: no fold produced trades")
            continue
        pf = sub["profit_factor"].replace([np.inf], np.nan).dropna()
        print(f"\n{symbol} ({len(sub)}/{len(folds)} folds with trades, "
              f"{len(sub[sub['n_trades']<50])} folds n<50):")
        print(f"  mean PF={pf.mean():.3f}  median PF={pf.median():.3f}  "
              f"%% folds PF>1: {(sub['profit_factor']>1).mean()*100:.1f}%")
        print(f"  worst fold PF={sub['profit_factor'].min():.3f}  best fold PF={sub['profit_factor'].max():.3f}")
        print(f"  total return summed across folds: {sub['total_return_pct'].sum():+.2f}%")
        print(f"  total forced liquidations across folds: {sub['n_forced_liq'].sum()}")

    print(f"\nRaw per-fold results saved -> {out_path}")


if __name__ == "__main__":
    main()
