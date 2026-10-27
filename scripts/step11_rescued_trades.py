"""
scripts/step11_rescued_trades.py — Étape 11, adapted to the CURRENT
BASELINE_CANDIDATE_V2 architecture: the plan's original "rescued trades"
concept came from the OLD dca_rescue_trend exit (a trend-confirmed second
leg that saved trades which would have lost at the base horizon). V2
doesn't use dca_rescue_trend at all anymore (trailing + protective stop +
time-exit only) -- there is no "rescue leg" to study directly.

The natural adaptation: compare each trade's return AT the base horizon
(10min mark, what the OLD label/exit would have locked in) against its
ACTUAL V2 exit return (which may have run much longer via the trailing
stop or a time-exit up to 50min). Four categories:
  - CLEAN WINNER: positive at horizon AND positive at actual V2 exit
  - RESCUED: negative at horizon, positive at actual V2 exit (V2's longer
    leash saved it)
  - CLEAN LOSER: negative at horizon AND negative at actual V2 exit
  - DETERIORATED: positive at horizon, negative at actual V2 exit (V2's
    longer leash let a winner turn into a loser -- the failure mode a
    fixed-horizon exit would have avoided)

This directly quantifies how much of V2's edge comes from "letting winners
run / giving losers room to recover" vs simply "clean immediate wins", and
whether the DETERIORATED category is big enough to worry about.

Usage:
    python scripts/step11_rescued_trades.py
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
from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01


def resolve_exit_return(path: np.ndarray, stop_distance: float, leverage: float):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    exit_ret, exit_offset = None, len(path) - 1
    for j, x in enumerate(path):
        if x <= -protective:
            exit_ret, exit_offset = -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, j
            break
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                exit_ret, exit_offset = stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, j
                break
    if exit_ret is None:
        exit_ret = path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
    return exit_ret, exit_offset


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min...")
    train_feats_all, train_labels_all = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats_all[symbol] = build_feature_matrix(df)
        train_labels_all[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train = pd.concat(train_labels_all.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.\n")

    all_cats = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df = load_split(symbol, "train", verbose=False)
        train_feats = build_feature_matrix(train_df)
        train_proba = model.predict_proba(train_feats)
        train_selected = train_proba > THRESHOLD
        range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
        vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()
        train_close = train_df["close"].to_numpy()
        train_ema_slope = train_feats["ema_slope_20"].to_numpy()
        train_ret_1 = train_feats["ret_1"].to_numpy()
        train_filtered = (
            (train_proba > THRESHOLD)
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        train_trades = build_trades_with_mae_mfe(train_close, train_filtered, train_ema_slope, train_ret_1)
        stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
        leverage = LEVERAGE[symbol]

        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()
        val_filtered = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        val_trades = build_trades_with_mae_mfe(val_close, val_filtered, val_ema_slope, val_ret_1)

        notional = CAPITAL * RISK_PCT
        rows = []
        for t in val_trades:
            path = t["close_path"]
            horizon_ret = path[HORIZON] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
            actual_ret, exit_offset = resolve_exit_return(path, stop_distance, leverage)
            if horizon_ret > 0 and actual_ret > 0:
                cat = "CLEAN WINNER"
            elif horizon_ret <= 0 and actual_ret > 0:
                cat = "RESCUED"
            elif horizon_ret <= 0 and actual_ret <= 0:
                cat = "CLEAN LOSER"
            else:
                cat = "DETERIORATED"
            rows.append({"symbol": symbol, "category": cat, "horizon_ret": horizon_ret,
                         "actual_ret": actual_ret, "pnl": actual_ret * notional * leverage,
                         "holding_time": exit_offset})
        df_cat = pd.DataFrame(rows)
        all_cats.append(df_cat)

        print("=" * 100)
        print(f"  {symbol} — rescued-trade categorization (n={len(df_cat)})")
        print("=" * 100)
        for cat, sub in df_cat.groupby("category"):
            n = len(sub)
            pnl_sum = sub["pnl"].sum()
            avg_hold = sub["holding_time"].mean()
            print(f"  {cat:<14} n={n:>4} ({n/len(df_cat)*100:>5.1f}%)  total_pnl=${pnl_sum:>+9.2f}  "
                  f"avg_hold={avg_hold:>5.1f}min  avg_actual_ret={sub['actual_ret'].mean()*100:>+7.4f}%")
        print()

    combined = pd.concat(all_cats, ignore_index=True)
    print("=" * 100)
    print("  COMBINED (both symbols)")
    print("=" * 100)
    for cat, sub in combined.groupby("category"):
        n = len(sub)
        print(f"  {cat:<14} n={n:>4} ({n/len(combined)*100:>5.1f}%)  total_pnl=${sub['pnl'].sum():>+9.2f}  "
              f"share_of_total_pnl={sub['pnl'].sum()/combined['pnl'].sum()*100:>+7.1f}%")

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step11_rescued_trades_raw.csv")
    combined.to_csv(out_path, index=False)
    print(f"\nRaw results saved -> {out_path}")


if __name__ == "__main__":
    main()
