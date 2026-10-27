"""
scripts/adaptive_exit_screen.py — Experiment 46 (piste 4 screen): a
SELECTIVE extension rule instead of Experiment 43b's blanket one.

H46: at the current 50min time-exit deadline, a trade whose unrealized
return has IMPROVED over its last K bars (i.e. path[50] > path[50-K],
100% computable from information available at bar 50, no lookahead) gets
extended to a longer deadline; a trade that has flattened or declined
exits on schedule exactly as today. This is causally valid: the decision
at bar 50 uses only path[0..50]; bars beyond 50 are only ever inspected
after the decision to extend has already been made using bar<=50 data.

SCREENING ONLY (VALIDATION split, TRAIN-only calibration for
threshold/filter/stop, joint BTC+ETH model) -- narrows K x extension
candidates for a full walk-forward follow-up, exactly Experiment 29/43's
role. Reuses the exact HOLDOUT-safe loading pattern from Experiment 45
(load_split + pre_holdout clip) and the same stop/leverage calibration
methodology as Experiment 43b's baseline (ratio=5 TRAIN calibration).

Usage:
    python -u scripts/adaptive_exit_screen.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.data.splits import pre_holdout
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
HORIZON = 10
THRESHOLD = 0.70
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
COST = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
BASELINE_RATIO = 5
FIT_N = 100_000
N_ESTIMATORS = 50

K_CANDIDATES = [3, 5, 10]
EXT_RATIO_CANDIDATES = [6, 7, 8]  # -> 60/70/80min


def resolve_adaptive(entry_price, close_arr, i, lookahead_base, lookahead_ext, k, stop_distance, leverage):
    path = close_arr[i:i + lookahead_ext + 1] / entry_price - 1.0
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for off in range(0, lookahead_base + 1):
        x = path[off]
        if x > peak:
            peak = x
        if x <= -protective:
            return {"ret": -protective - COST, "exit_off": off, "reason": "stop", "extended": False}
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return {"ret": stop_level - COST, "exit_off": off, "reason": "trailing", "extended": False}
    trend_ok = path[lookahead_base] > path[max(0, lookahead_base - k)]
    if not trend_ok:
        return {"ret": path[lookahead_base] - COST, "exit_off": lookahead_base, "reason": "time", "extended": False}
    for off in range(lookahead_base + 1, lookahead_ext + 1):
        x = path[off]
        if x > peak:
            peak = x
        if x <= -protective:
            return {"ret": -protective - COST, "exit_off": off, "reason": "stop_ext", "extended": True}
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return {"ret": stop_level - COST, "exit_off": off, "reason": "trailing_ext", "extended": True}
    return {"ret": path[lookahead_ext] - COST, "exit_off": lookahead_ext, "reason": "time_ext", "extended": True}


def resolve_baseline(entry_price, close_arr, i, lookahead_base, stop_distance, leverage):
    return resolve_adaptive(entry_price, close_arr, i, lookahead_base, lookahead_base, 1, stop_distance, leverage)


def pf_and_return(rets):
    rets = np.asarray(rets)
    wins, losses = rets[rets > 0], rets[rets <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return pf, float(rets.sum())


def main():
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
    print(f"Fitting joint BTC+ETH model (FIT_N={FIT_N}, N_ESTIMATORS={N_ESTIMATORS})...")
    model = Tier2RandomForestSignal(kept, n_estimators=N_ESTIMATORS).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "adaptive_exit_screen_results.csv")
    results = []
    if os.path.exists(out_path):
        results = pd.read_csv(out_path).to_dict("records")
        print(f"Resuming: {len(results)} symbol rows already done")
    done_keys = {(r["symbol"]) for r in results}

    lookahead_base = BASELINE_RATIO * HORIZON

    for symbol in TRAIN_SYMBOLS:
        if symbol in done_keys:
            print(f"{symbol}: already done, skipping")
            continue
        train_feats = train_feats_all[symbol]
        train_proba = model.predict_proba(train_feats)
        train_selected = train_proba > THRESHOLD
        range_pos_cut = float(train_feats.loc[train_selected, "range_pos_60"].median())
        vol_cut = float(train_feats.loc[train_selected, "realized_vol_30"].median())
        train_df = load_split(symbol, "train", verbose=False)
        train_close = train_df["close"].to_numpy()
        train_filtered = (
            train_selected
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        n_train = len(train_close)
        idxs = np.where(train_filtered)[0]
        idxs = idxs[idxs < n_train - lookahead_base - 1]
        maes = [float((train_close[i:i + lookahead_base + 1] / train_close[i] - 1.0).min()) for i in idxs]
        stop_distance = float(np.percentile(np.abs(maes), STOP_PCT_PERCENTILE))
        leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
        print(f"{symbol}: TRAIN-calibrated stop={stop_distance*100:.2f}% leverage={leverage:.2f}x")

        val_df = pre_holdout(load_split(symbol, "validation", verbose=False), symbol)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_filtered = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        val_close = val_df["close"].to_numpy()
        n_val = len(val_close)
        max_ext = max(EXT_RATIO_CANDIDATES) * HORIZON

        entries = []
        i = 0
        n_entries = 0
        while i < n_val - max_ext - 1:
            if val_filtered[i]:
                entries.append(i)
                n_entries += 1
                if n_entries % 300 == 0:
                    print(f"  {symbol}: {n_entries} entries scanned so far ({i}/{n_val} bars)")
            i += HORIZON
        print(f"{symbol}: {len(entries)} VALIDATION entries total")

        baseline_rets = [resolve_baseline(val_close[i], val_close, i, lookahead_base, stop_distance, leverage)["ret"]
                          for i in entries]
        base_pf, base_ret = pf_and_return(baseline_rets)
        base_win = float(np.mean(np.array(baseline_rets) > 0)) * 100
        row = {"symbol": symbol, "variant": "baseline_ratio5", "k": None, "ext_ratio": 5,
               "n": len(entries), "pf": round(base_pf, 3), "total_ret_pct": round(base_ret * 100, 3),
               "win_pct": round(base_win, 1), "pct_extended": 0.0}
        results.append(row)
        print(f"  {symbol} baseline(ratio5): n={len(entries)} PF={base_pf:.3f} "
              f"ret={base_ret*100:+.3f}% win%={base_win:.1f}")

        for k in K_CANDIDATES:
            for ext_ratio in EXT_RATIO_CANDIDATES:
                lookahead_ext = ext_ratio * HORIZON
                out = [resolve_adaptive(val_close[i], val_close, i, lookahead_base, lookahead_ext, k,
                                         stop_distance, leverage) for i in entries]
                rets = [o["ret"] for o in out]
                pf, tot_ret = pf_and_return(rets)
                win = float(np.mean(np.array(rets) > 0)) * 100
                pct_ext = float(np.mean([o["extended"] for o in out])) * 100
                row = {"symbol": symbol, "variant": "adaptive", "k": k, "ext_ratio": ext_ratio,
                       "n": len(entries), "pf": round(pf, 3), "total_ret_pct": round(tot_ret * 100, 3),
                       "win_pct": round(win, 1), "pct_extended": round(pct_ext, 1)}
                results.append(row)
                print(f"  {symbol} k={k} ext_ratio={ext_ratio}: PF={pf:.3f} ret={tot_ret*100:+.3f}% "
                      f"win%={win:.1f} extended%={pct_ext:.1f}")

        done_keys.add(symbol)
        pd.DataFrame(results).to_csv(out_path, index=False)
        print(f"{symbol}: done, checkpoint saved")

    print(f"\nAll results -> {out_path}")
    df = pd.DataFrame(results)
    print(df.to_string())


if __name__ == "__main__":
    main()
