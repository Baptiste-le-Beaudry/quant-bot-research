"""
scripts/step5_threshold_sweep.py — Étape 5: sweep the RF decision threshold
(0.70-0.925) on top of BASELINE_CANDIDATE_V2, framed the way the plan
insists on -- not "which threshold gives the max PF" but "which threshold
gives the best avg_return_per_trade x n_trades" (i.e. total realized
return), since a tighter threshold with a higher PF but a fraction of the
trades can lose on total $ return to a looser threshold with more trades.

Everything downstream of the threshold choice is re-derived per threshold,
never held over from THRESHOLD=0.75's values:
  - entry filter cutoffs (range_pos_60/realized_vol_30, TRAIN-selected pop
    AT THAT THRESHOLD)
  - protective-stop MAE percentile (TRAIN-selected pop AT THAT THRESHOLD --
    same fix as the walk-forward engine, not the VALIDATION-calibrated
    number used in Experiments 1/1b/4)
The model itself is fit ONCE (threshold only changes the decision cutoff
on its output probability, not what the model learned) and reused across
the whole sweep for efficiency.

Usage:
    python scripts/step5_threshold_sweep.py
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
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080  # V2
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01

THRESHOLDS = [0.70, 0.725, 0.75, 0.775, 0.80, 0.825, 0.85, 0.875, 0.90, 0.925]


def simulate(trades, leverage, stop_distance) -> dict:
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = CAPITAL * RISK_PCT
    pnls, n_forced = [], 0
    for t in trades:
        path = t["close_path"]
        peak, activated = -np.inf, False
        exit_ret, forced = None, False
        for x in path:
            if x <= -protective:
                exit_ret = -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                forced = liq_move <= stop_distance
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
        n_forced += int(forced)
    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    per_trade_ret = pnls / CAPITAL
    sharpe_like = float(per_trade_ret.mean() / (per_trade_ret.std() + 1e-12))
    return {
        "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
        "avg_return_per_trade_pct": round(pnls.mean() / CAPITAL * 100, 4),
        "max_dd_pct": round(float(dd.min() * 100), 3),
        "win_rate_pct": round((pnls > 0).mean() * 100, 1),
        "sharpe_like": round(sharpe_like, 4),
        "n_forced_liq": n_forced,
    }


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min (ONE fit, reused across all thresholds)...")
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

    all_rows = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df = load_split(symbol, "train", verbose=False)
        train_feats = build_feature_matrix(train_df)
        train_proba = model.predict_proba(train_feats)
        train_close = train_df["close"].to_numpy()
        train_ema_slope = train_feats["ema_slope_20"].to_numpy()
        train_ret_1 = train_feats["ret_1"].to_numpy()

        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()

        print("=" * 110)
        print(f"  {symbol} — RF threshold sweep")
        print("=" * 110)
        print(f"  {'thr':>6}{'n':>6}{'PF':>9}{'avg_ret/trade%':>16}{'total_ret%':>12}{'win%':>7}"
              f"{'maxDD%':>9}{'sharpe':>9}{'forced_liq':>12}")

        for thr in THRESHOLDS:
            train_selected = train_proba > thr
            if train_selected.sum() < 20:
                print(f"  {thr:>6.3f}  train-selected population < 20, skipping")
                all_rows.append({"symbol": symbol, "threshold": thr, "n_trades": 0})
                continue
            range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
            vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()

            train_filtered = (
                (train_proba > thr)
                & (train_feats["range_pos_60"] < range_pos_cut)
                & (train_feats["realized_vol_30"] > vol_cut)
            ).to_numpy()
            train_trades = build_trades_with_mae_mfe(train_close, train_filtered, train_ema_slope, train_ret_1)
            if len(train_trades) < 10:
                print(f"  {thr:>6.3f}  too few TRAIN trades to calibrate stop, skipping")
                all_rows.append({"symbol": symbol, "threshold": thr, "n_trades": 0})
                continue
            stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))

            val_filtered = (
                (val_proba > thr)
                & (val_feats["range_pos_60"] < range_pos_cut)
                & (val_feats["realized_vol_30"] > vol_cut)
            ).to_numpy()
            val_trades = build_trades_with_mae_mfe(val_close, val_filtered, val_ema_slope, val_ret_1)
            r = simulate(val_trades, LEVERAGE[symbol], stop_distance)

            if r.get("n_trades", 0) == 0:
                print(f"  {thr:>6.3f}  no VALIDATION entries")
                all_rows.append({"symbol": symbol, "threshold": thr, "n_trades": 0})
                continue
            print(f"  {thr:>6.3f}{r['n_trades']:>6}{r['profit_factor']:>9.3f}"
                  f"{r['avg_return_per_trade_pct']:>+16.4f}{r['total_return_pct']:>+12.3f}"
                  f"{r['win_rate_pct']:>7.1f}{r['max_dd_pct']:>+9.3f}{r['sharpe_like']:>9.4f}"
                  f"{r['n_forced_liq']:>12}")
            all_rows.append({"symbol": symbol, "threshold": thr, "stop_distance": stop_distance, **r})
        print()

    df_res = pd.DataFrame(all_rows)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step5_threshold_sweep_raw.csv")
    df_res.to_csv(out_path, index=False)

    print("=" * 110)
    print("  BEST THRESHOLD BY TOTAL RETURN (expected-value framing) vs BY PF")
    print("=" * 110)
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        sub = df_res[(df_res["symbol"] == symbol) & (df_res["n_trades"] > 0)]
        if len(sub) == 0:
            continue
        best_ret = sub.loc[sub["total_return_pct"].idxmax()]
        best_pf = sub.loc[sub["profit_factor"].replace([np.inf], np.nan).idxmax()] if sub["profit_factor"].replace([np.inf], np.nan).notna().any() else None
        print(f"\n{symbol}:")
        print(f"  best TOTAL RETURN: thr={best_ret['threshold']}, n={best_ret['n_trades']:.0f}, "
              f"PF={best_ret['profit_factor']:.3f}, total_ret={best_ret['total_return_pct']:+.3f}%")
        if best_pf is not None:
            print(f"  best PF (finite):  thr={best_pf['threshold']}, n={best_pf['n_trades']:.0f}, "
                  f"PF={best_pf['profit_factor']:.3f}, total_ret={best_pf['total_return_pct']:+.3f}%")
        print(f"  registered baseline thr=0.75: n={sub[sub['threshold']==0.75]['n_trades'].values}, "
              f"PF={sub[sub['threshold']==0.75]['profit_factor'].values}, "
              f"total_ret={sub[sub['threshold']==0.75]['total_return_pct'].values}")

    print(f"\nRaw results saved -> {out_path}")


if __name__ == "__main__":
    main()
