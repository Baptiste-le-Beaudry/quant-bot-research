"""
scripts/exit_pattern_mining.py — Experiment 44 (pattern-mining screen):
does trade "speed" (how fast price reaches its favorable extreme), entry
realized volatility, or entry relative volume predict whether a trade
would have benefited from a longer or shorter holding window?

SCREENING ONLY (VALIDATION split, not walk-forward, not TRAIN-refit per
ratio) -- explicitly a signal-generation exercise for what might deserve a
disciplined follow-up, not itself a validated finding. Spearman
correlation is used throughout (monotonic, not just linear), but every
correlation reported here MUST be read as a hint on a small, confounded,
non-independent trade population (adjacent trades share market regime),
not as proof.

Uses the SAME entries as window_ratio_sweep_validation.py's ratio=5
(current production baseline: horizon=10, 50min max hold) so this reuses
the identical model/filters/stop the deployed bundle uses, and asks a
narrower question about trades that hit the CURRENT time-exit: would MORE
bars (holding the SAME stop/leverage fixed, i.e., an apples-to-apples
per-trade counterfactual, unlike the ratio sweep's independently
recalibrated stop per ratio) have flipped the outcome, and does anything
observable AT ENTRY predict that.

Usage:
    python scripts/exit_pattern_mining.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

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
BASELINE_RATIO = 5       # the deployed default -- window_ratio_sweep's ratio=5 row
EXTENDED_RATIO = 15      # "if given a lot more time" counterfactual horizon for this screen
FIT_N = 100_000
N_ESTIMATORS = 50


def resolve_with_path_stats(entry_price, close_arr, i, lookahead, stop_distance, leverage):
    path = close_arr[i:i + lookahead + 1] / entry_price - 1.0
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, peak_off, activated = -np.inf, 0, False
    for off, x in enumerate(path):
        if x > peak:
            peak, peak_off = x, off
        if x <= -protective:
            return {"ret": -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2,
                    "exit_off": off, "reason": "stop", "peak": peak, "peak_off": peak_off}
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return {"ret": stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2,
                        "exit_off": off, "reason": "trailing", "peak": peak, "peak_off": peak_off}
    return {"ret": path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2,
            "exit_off": len(path) - 1, "reason": "time", "peak": peak, "peak_off": peak_off}


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

    # Per-symbol checkpointing: this environment can kill long-running
    # background jobs during idle periods (observed: this script has no
    # output at all, and therefore no saved progress, until BOTH symbols
    # finish -- a kill mid-run loses everything). Each symbol takes several
    # minutes (dense per-bar scan + a Python-level path walk per filtered
    # entry), so checkpoint at that granularity: skip a symbol already
    # present in the output CSV, and save after each symbol completes.
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "exit_pattern_mining_trades.csv")
    all_records = []
    done_symbols = set()
    if os.path.exists(out_path):
        prev = pd.read_csv(out_path)
        all_records = prev.to_dict("records")
        done_symbols = set(prev["symbol"].unique())
        print(f"Resuming: {done_symbols} already done, {len(all_records)} rows loaded")

    for symbol in ["BTCUSDT", "ETHUSDT"]:
        if symbol in done_symbols:
            print(f"{symbol}: already done, skipping")
            continue
        train_feats = train_feats_all[symbol]
        train_proba = model.predict_proba(train_feats)
        train_selected = train_proba > THRESHOLD
        range_pos_cut = float(train_feats.loc[train_selected, "range_pos_60"].median())
        vol_cut = float(train_feats.loc[train_selected, "realized_vol_30"].median())
        train_df = load_split(symbol, "train", verbose=False)
        train_close = train_df["close"].to_numpy()
        lookahead_baseline = BASELINE_RATIO * HORIZON
        train_filtered = (
            train_selected
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        n_train = len(train_close)
        idxs = np.where(train_filtered)[0]
        idxs = idxs[idxs < n_train - lookahead_baseline - 1]
        maes = [float((train_close[i:i + lookahead_baseline + 1] / train_close[i] - 1.0).min()) for i in idxs]
        stop_distance = float(np.percentile(np.abs(maes), STOP_PCT_PERCENTILE))
        leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
        print(f"{symbol}: TRAIN-calibrated stop={stop_distance*100:.2f}% leverage={leverage:.2f}x "
              f"(fixed for this screen's counterfactual, from ratio={BASELINE_RATIO} baseline)")

        # load_split's VALIDATION tail is a fixed 80th percentile of the full
        # (post-HOLDOUT-inclusive) CSV, which lands a few hours past each
        # symbol's registered HOLDOUT boundary (found while sanity-checking
        # this script: BTCUSDT ~3.5h, ETHUSDT ~1.5h past holdout_start).
        # pre_holdout() clips that defensively -- belt-and-suspenders on top
        # of the shared loader, scoped to just this script.
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
        lookahead_ext = EXTENDED_RATIO * HORIZON

        i = 0
        n_entries_this_symbol = 0
        while i < n_val - lookahead_ext - 1:
            if not val_filtered[i]:
                i += 1
                continue
            n_entries_this_symbol += 1
            if n_entries_this_symbol % 500 == 0:
                print(f"  {symbol}: {n_entries_this_symbol} entries processed "
                      f"({i}/{n_val} bars scanned)")
            base = resolve_with_path_stats(val_close[i], val_close, i, lookahead_baseline, stop_distance, leverage)
            ext = resolve_with_path_stats(val_close[i], val_close, i, lookahead_ext, stop_distance, leverage)
            all_records.append({
                "symbol": symbol, "entry_idx": i,
                "entry_realized_vol_30": float(val_feats["realized_vol_30"].iloc[i]),
                "entry_range_pos_60": float(val_feats["range_pos_60"].iloc[i]),
                "entry_rel_volume_20": float(val_feats["rel_volume_20"].iloc[i])
                    if "rel_volume_20" in val_feats.columns else np.nan,
                "base_ret": base["ret"], "base_reason": base["reason"], "base_exit_off": base["exit_off"],
                "peak_off": base["peak_off"], "peak": base["peak"],
                "ext_ret": ext["ret"], "ext_reason": ext["reason"], "ext_exit_off": ext["exit_off"],
            })
            i += HORIZON

        pd.DataFrame(all_records).to_csv(out_path, index=False)
        print(f"{symbol}: done, checkpoint saved ({len(all_records)} rows so far)")

    trades = pd.DataFrame(all_records)
    print(f"\n{len(trades)} total trades (both symbols) -> {out_path}")

    # --- Piste 3a: does bars-to-peak (speed) predict base_ret? ---
    print("\n=== bars-to-peak ('speed') vs realized return ===")
    for symbol, grp in trades.groupby("symbol"):
        rho, p = spearmanr(grp["peak_off"], grp["base_ret"])
        print(f"{symbol}: n={len(grp)} spearman(peak_off, base_ret)={rho:+.3f} (p={p:.4f})")

    # --- Piste 3b: entry realized_vol / rel_volume vs realized return ---
    print("\n=== entry realized_vol_30 vs realized return ===")
    for symbol, grp in trades.groupby("symbol"):
        rho, p = spearmanr(grp["entry_realized_vol_30"], grp["base_ret"])
        print(f"{symbol}: spearman(entry_realized_vol_30, base_ret)={rho:+.3f} (p={p:.4f})")
    print("\n=== entry rel_volume_20 vs realized return ===")
    for symbol, grp in trades.groupby("symbol"):
        if grp["entry_rel_volume_20"].isna().all():
            print(f"{symbol}: rel_volume_20 unavailable")
            continue
        rho, p = spearmanr(grp["entry_rel_volume_20"], grp["base_ret"])
        print(f"{symbol}: spearman(entry_rel_volume_20, base_ret)={rho:+.3f} (p={p:.4f})")

    # --- Piste 2: counterfactual on CURRENT time-exits specifically ---
    print(f"\n=== counterfactual: trades that hit the CURRENT ({BASELINE_RATIO}x/{BASELINE_RATIO*HORIZON}min) "
          f"time-exit, given {EXTENDED_RATIO}x/{EXTENDED_RATIO*HORIZON}min instead ===")
    for symbol, grp in trades.groupby("symbol"):
        time_exits = grp[grp["base_reason"] == "time"]
        if len(time_exits) == 0:
            print(f"{symbol}: no time-exits in this window")
            continue
        would_win = (time_exits["ext_ret"] > 0).mean() * 100
        currently_win = (time_exits["base_ret"] > 0).mean() * 100
        flipped_to_win = ((time_exits["base_ret"] <= 0) & (time_exits["ext_ret"] > 0)).mean() * 100
        flipped_to_loss = ((time_exits["base_ret"] > 0) & (time_exits["ext_ret"] <= 0)).mean() * 100
        unaffected = (time_exits["ext_reason"] == "time").mean() * 100
        print(f"{symbol}: n_time_exits={len(time_exits)} currently_win%={currently_win:.1f} "
              f"win%_with_more_time={would_win:.1f} flipped_loss->win%={flipped_to_win:.1f} "
              f"flipped_win->loss%={flipped_to_loss:.1f} still_time_exit_at_{EXTENDED_RATIO}x%={unaffected:.1f}")

    # --- non-time-exits: are they unaffected by the window, as expected? ---
    print(f"\n=== trades NOT hitting the current time-exit (stop/trailing) -- should be window-invariant ===")
    for symbol, grp in trades.groupby("symbol"):
        non_time = grp[grp["base_reason"] != "time"]
        changed = (non_time["ext_reason"] != non_time["base_reason"]).mean() * 100 if len(non_time) else None
        print(f"{symbol}: n={len(non_time)} exit_reason_changed_by_window%={changed}")


if __name__ == "__main__":
    main()
