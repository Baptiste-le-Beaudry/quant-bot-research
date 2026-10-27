"""
scripts/horizon_sweep_validation.py — Experiment 29 (Étape ③ of the user's
"find more positive-EV trades" plan): cheap TRAIN-fit / VALIDATION-screen
pass across label horizons [5,10,20,30,50,60] min, to see whether some of
the current 10-min "losers" are actually good trades at a longer horizon
(or whether a shorter horizon trades more often with less give-back).

Per horizon H: refit Tier2RandomForestSignal from scratch (BTC+ETH joint
TRAIN, label = build_labels(H)), recompute BASELINE_CANDIDATE_V3's entry
rule (threshold=0.70, range_pos_60/realized_vol_30 filter, cutoffs from
THIS horizon's TRAIN-selected population), recompute the p90 protective
stop from TRAIN, and keep the exit-window scaled with the horizon (same
5x ratio V3 already uses: LOOKAHEAD = 5*HORIZON, i.e. EXTENSION_CAP=4*H)
-- the trailing activate/trail distances stay FIXED (0.63%/0.80%, V2/V3's
frozen values) since those aren't a function of label horizon.

This is a SCREEN on VALIDATION only (not walk-forward) -- cheap, one pass
per horizon, to identify which horizon(s) merit the expensive walk-forward
+ stress-test treatment, mirroring how Experiment 5's threshold sweep was
screened before promising candidates got the full treatment.

Usage:
    python scripts/horizon_sweep_validation.py
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
THRESHOLD = 0.70  # BASELINE_CANDIDATE_V3 (Experiment 28)
STOP_PCT_PERCENTILE = 90
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01

HORIZONS = [5, 10, 20, 30, 50, 60]
WINDOW_RATIO = 5  # V2/V3's existing ratio: LOOKAHEAD = 5*HORIZON (10min label -> 50min max hold)
# Screening-only speed knobs (this environment's background tasks keep getting killed around
# 8-10min per full-cost fit) -- lighter than the full 250k/100-tree config used for the
# already-validated horizon=5/10 results and for the final walk-forward treatment of any winner.
FIT_N = 100_000
N_ESTIMATORS = 50


def resolve(entry_price, close_arr, i, lookahead, stop_distance, leverage):
    path = close_arr[i:i + lookahead + 1] / entry_price - 1.0
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


def run_horizon(horizon: int):
    lookahead = WINDOW_RATIO * horizon
    cost_pct = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST

    train_feats_all, train_labels_all = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats_all[symbol] = build_feature_matrix(df)
        train_labels_all[symbol] = build_labels(df["close"], horizon, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train = pd.concat(train_labels_all.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(FIT_N, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=N_ESTIMATORS).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])

    results = {}
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        train_feats = train_feats_all[symbol]
        train_proba = model.predict_proba(train_feats)
        train_selected = train_proba > THRESHOLD
        if train_selected.sum() < 20:
            results[symbol] = {"n_trades": 0, "reason": "train-selected < 20"}
            continue
        range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
        vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()
        train_df = load_split(symbol, "train", verbose=False)
        train_close = train_df["close"].to_numpy()
        train_filtered = (
            train_selected
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()

        # TRAIN-only p90 stop, using this horizon's own lookahead window.
        n_train = len(train_close)
        maes = []
        idxs = np.where(train_filtered)[0]
        idxs = idxs[idxs < n_train - lookahead - 1]
        for i in idxs:
            path = train_close[i:i + lookahead + 1] / train_close[i] - 1.0
            maes.append(float(path.min()))
        if len(maes) < 10:
            results[symbol] = {"n_trades": 0, "reason": "too few TRAIN trades to calibrate stop"}
            continue
        stop_distance = float(np.percentile(np.abs(maes), STOP_PCT_PERCENTILE))
        leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)

        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_filtered = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        val_close = val_df["close"].to_numpy()
        n_val = len(val_close)

        pnls = []
        i = 0
        while i < n_val - lookahead - 1:
            if not val_filtered[i]:
                i += 1
                continue
            ret = resolve(val_close[i], val_close, i, lookahead, stop_distance, leverage)
            pnls.append(ret * leverage)
            i += horizon
        if not pnls:
            results[symbol] = {"n_trades": 0, "reason": "no VALIDATION entries"}
            continue
        pnls = np.array(pnls)
        wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
        results[symbol] = {
            "n_trades": len(pnls), "profit_factor": round(pf, 3),
            "avg_ret_pct": round(float(pnls.mean()) * 100, 4),
            "win_rate_pct": round((pnls > 0).mean() * 100, 1),
            "total_ret_pct": round(float(pnls.sum()) * 100, 3),
            "stop_distance_pct": round(stop_distance * 100, 3),
            "leverage": round(leverage, 2),
        }
    return results


def main():
    all_rows = []
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-horizons", type=int, default=1)
    args = parser.parse_args()

    ckpt_path = os.path.join(os.path.dirname(__file__), "..", "docs", "horizon_sweep_validation_raw.csv")
    done_horizons = set()
    if os.path.exists(ckpt_path):
        prev = pd.read_csv(ckpt_path)
        all_rows = prev.to_dict("records")
        done_horizons = set(prev["horizon"].unique())
        print(f"Resuming: horizons already done = {sorted(done_horizons)}")

    processed = 0
    for h in HORIZONS:
        if h in done_horizons:
            print(f"HORIZON {h}: already done, skipping")
            continue
        if processed >= args.max_horizons:
            print(f"Reached --max-horizons={args.max_horizons}, exiting cleanly.")
            break
        print(f"\n=== HORIZON = {h}min (max hold = {WINDOW_RATIO*h}min) ===")
        res = run_horizon(h)
        for symbol, r in res.items():
            if r.get("n_trades", 0) == 0:
                print(f"  {symbol}: {r.get('reason')}")
            else:
                print(f"  {symbol}: n={r['n_trades']:>4} PF={r['profit_factor']:>7.3f} "
                      f"avg_ret={r['avg_ret_pct']:>+7.4f}% win%={r['win_rate_pct']:>5.1f} "
                      f"total_ret={r['total_ret_pct']:>+7.2f}% stop={r['stop_distance_pct']:.2f}% "
                      f"lev={r['leverage']}x")
            all_rows.append({"horizon": h, "symbol": symbol, **r})
        pd.DataFrame(all_rows).to_csv(ckpt_path, index=False)
        processed += 1

    remaining = [h for h in HORIZONS if h not in {r["horizon"] for r in all_rows}]
    if remaining:
        print(f"\nHorizons still remaining: {remaining} -- rerun to continue.")
        return
    print(f"\nAll horizons done -> {ckpt_path}")


if __name__ == "__main__":
    main()
