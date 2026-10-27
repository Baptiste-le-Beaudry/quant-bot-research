"""
scripts/window_ratio_sweep_validation.py — Experiment 43 (exit-window
multiplier sweep, horizon held fixed): the frozen bundle uses
max_holding_bars = horizon * 5 (EXTENSION_MULTIPLIER=4 in fast_trades.py).
Experiments 29/30 already tested horizon+window scaled *together*
(horizon=20 -> REJECTED, BTC median PF fell to 0.819 under proper
walk-forward). This is a different, narrower question: with horizon FIXED
at 10 (the frozen default, same model/filters/entries), does the window
RATIO itself (currently 5x) matter?

Because horizon does not change, the model does not need refitting per
ratio: fit ONE joint BTC+ETH TRAIN model at horizon=10 (same as the
production bundle build), then for each window ratio only recompute what
actually depends on the lookahead window: the TRAIN-only p90 protective
stop (a wider window can catch a deeper drawdown before the label
horizon closes -> may shift stop_distance/leverage) and the VALIDATION
trade resolution (the trailing-stop replay over a longer or shorter
path). This makes the whole ratio sweep cheap relative to a horizon
sweep, so all ratios run in one pass (still degradable via --max-ratios
if this environment kills the process).

Usage:
    python scripts/window_ratio_sweep_validation.py
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10  # FROZEN default -- the only thing Experiment 43 does NOT sweep.
THRESHOLD = 0.70
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0

# Baseline (deployed) ratio is 5. Sweep both directions; escalate past 10 if
# the frontier is still improving monotonically at the edge (per user request).
WINDOW_RATIOS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 21, 25]

FIT_N = 100_000
N_ESTIMATORS = 50  # lighter than the frozen bundle's 250k/100 -- screening only


def resolve(entry_price, close_arr, i, lookahead, stop_distance, leverage):
    path = close_arr[i:i + lookahead + 1] / entry_price - 1.0
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    exit_offset = len(path) - 1
    for off, x in enumerate(path):
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, off, "stop"
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, off, "trailing"
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, exit_offset, "time"


def fit_joint_model():
    train_feats_all, train_labels_all = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats_all[symbol] = build_feature_matrix(df)
        train_labels_all[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train = pd.concat(train_labels_all.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(FIT_N, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=N_ESTIMATORS).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    return model, train_feats_all


def prepare_symbol(symbol, model, train_feats_all):
    """Entry rule + selected TRAIN/VALIDATION populations -- independent of window ratio."""
    train_feats = train_feats_all[symbol]
    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > THRESHOLD
    if train_selected.sum() < 20:
        return None
    range_pos_cut = float(train_feats.loc[train_selected, "range_pos_60"].median())
    vol_cut = float(train_feats.loc[train_selected, "realized_vol_30"].median())
    train_df = load_split(symbol, "train", verbose=False)
    train_close = train_df["close"].to_numpy()
    train_filtered = (
        train_selected
        & (train_feats["range_pos_60"] < range_pos_cut)
        & (train_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()

    val_df = load_split(symbol, "validation", verbose=False)
    val_feats = build_feature_matrix(val_df)
    val_proba = model.predict_proba(val_feats)
    val_filtered = (
        (val_proba > THRESHOLD)
        & (val_feats["range_pos_60"] < range_pos_cut)
        & (val_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    val_close = val_df["close"].to_numpy()
    return {
        "train_close": train_close, "train_filtered": train_filtered,
        "val_close": val_close, "val_filtered": val_filtered,
        "range_pos_cut": range_pos_cut, "vol_cut": vol_cut,
    }


def evaluate_ratio(prep, ratio):
    lookahead = ratio * HORIZON
    train_close, train_filtered = prep["train_close"], prep["train_filtered"]
    n_train = len(train_close)
    idxs = np.where(train_filtered)[0]
    idxs = idxs[idxs < n_train - lookahead - 1]
    if len(idxs) < 10:
        return {"n_trades": 0, "reason": "too few TRAIN trades to calibrate stop"}
    maes = [float((train_close[i:i + lookahead + 1] / train_close[i] - 1.0).min()) for i in idxs]
    stop_distance = float(np.percentile(np.abs(maes), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)

    val_close, val_filtered = prep["val_close"], prep["val_filtered"]
    n_val = len(val_close)
    pnls, exit_offsets, exit_reasons = [], [], []
    i = 0
    while i < n_val - lookahead - 1:
        if not val_filtered[i]:
            i += 1
            continue
        ret, off, reason = resolve(val_close[i], val_close, i, lookahead, stop_distance, leverage)
        pnls.append(ret * leverage)
        exit_offsets.append(off)
        exit_reasons.append(reason)
        i += HORIZON
    if not pnls:
        return {"n_trades": 0, "reason": "no VALIDATION entries"}
    pnls = np.array(pnls)
    exit_reasons = np.array(exit_reasons)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    time_mask = exit_reasons == "time"
    time_exit_win_rate = float((pnls[time_mask] > 0).mean() * 100) if time_mask.sum() else None
    return {
        "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "avg_ret_pct": round(float(pnls.mean()) * 100, 4),
        "win_rate_pct": round((pnls > 0).mean() * 100, 1),
        "total_ret_pct": round(float(pnls.sum()) * 100, 3),
        "stop_distance_pct": round(stop_distance * 100, 3),
        "leverage": round(leverage, 2),
        "n_time_exits": int(time_mask.sum()),
        "time_exit_win_rate_pct": round(time_exit_win_rate, 1) if time_exit_win_rate is not None else None,
        "n_stop_exits": int((exit_reasons == "stop").sum()),
        "n_trailing_exits": int((exit_reasons == "trailing").sum()),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-ratios", type=int, default=len(WINDOW_RATIOS))
    args = parser.parse_args()

    ckpt_path = os.path.join(os.path.dirname(__file__), "..", "docs", "window_ratio_sweep_validation_raw.csv")
    all_rows = []
    done_ratios = set()
    if os.path.exists(ckpt_path):
        prev = pd.read_csv(ckpt_path)
        all_rows = prev.to_dict("records")
        done_ratios = set(prev["window_ratio"].unique())
        print(f"Resuming: ratios already done = {sorted(done_ratios)}")

    print(f"Fitting ONE joint BTC+ETH TRAIN model at horizon={HORIZON}min "
          f"(FIT_N={FIT_N}, N_ESTIMATORS={N_ESTIMATORS})...")
    model, train_feats_all = fit_joint_model()
    prep = {}
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        p = prepare_symbol(symbol, model, train_feats_all)
        if p is None:
            print(f"{symbol}: train-selected population < 20, aborting sweep")
            return
        prep[symbol] = p
        print(f"{symbol}: entry rule fixed (range_pos_cut={p['range_pos_cut']:.4f}, "
              f"vol_cut={p['vol_cut']:.6f}), independent of window ratio")

    processed = 0
    for ratio in WINDOW_RATIOS:
        if ratio in done_ratios:
            print(f"RATIO {ratio}x: already done, skipping")
            continue
        if processed >= args.max_ratios:
            print(f"Reached --max-ratios={args.max_ratios}, exiting cleanly.")
            break
        print(f"\n=== WINDOW_RATIO = {ratio}x (max hold = {ratio*HORIZON}min) ===")
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            r = evaluate_ratio(prep[symbol], ratio)
            if r.get("n_trades", 0) == 0:
                print(f"  {symbol}: {r.get('reason')}")
            else:
                print(f"  {symbol}: n={r['n_trades']:>4} PF={r['profit_factor']:>7.3f} "
                      f"avg_ret={r['avg_ret_pct']:>+7.4f}% win%={r['win_rate_pct']:>5.1f} "
                      f"total_ret={r['total_ret_pct']:>+7.2f}% stop={r['stop_distance_pct']:.2f}% "
                      f"lev={r['leverage']}x | time_exits={r['n_time_exits']} "
                      f"(win%={r['time_exit_win_rate_pct']}) stop_exits={r['n_stop_exits']} "
                      f"trailing_exits={r['n_trailing_exits']}")
            all_rows.append({"window_ratio": ratio, "symbol": symbol, **r})
        pd.DataFrame(all_rows).to_csv(ckpt_path, index=False)
        processed += 1

    remaining = [r for r in WINDOW_RATIOS if r not in {row["window_ratio"] for row in all_rows}]
    if remaining:
        print(f"\nRatios still remaining: {remaining} -- rerun to continue.")
        return
    print(f"\nAll ratios done -> {ckpt_path}")


if __name__ == "__main__":
    main()
