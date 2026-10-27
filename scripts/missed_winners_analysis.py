"""
scripts/missed_winners_analysis.py — Missed Winners Analysis (user's plan,
2026-08-18), Étapes ①+②: on TRAIN ONLY, for every bar with RF probability
> 0.60 (not just the currently-traded proba>0.75 + range/vol-filter
population), resolve the SAME exit logic (trailing 0.63%/0.80%,
protective stop at the CURRENTLY-established p90 MAE distance, 50min
time-exit, same fees/slippage) as if a position had been opened there.
Buckets results by probability range (0.60-0.65, 0.65-0.675, 0.675-0.70,
0.70-0.725, 0.725-0.75, 0.75+) and reports n/win_rate/avg_return/PF/
avg_MFE/avg_MAE/expectancy/total_potential_return per bucket, further
split by whether each bar also passes the existing range_pos_60/
realized_vol_30 filter.

NOT a trading simulation (bars are evaluated independently, not one-
position-at-a-time) -- this is deliberately exploratory, per the plan's
own framing: the question is "what distinguishes a good outcome from a
bad one at this probability level," not "what would a real backtest of
this population return." No lookahead: every feature/bucket used is
computed strictly from information available AT the entry bar.

Usage:
    python scripts/missed_winners_analysis.py
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
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
EXTENSION_CAP = 40
LOOKAHEAD = HORIZON + EXTENSION_CAP
THRESHOLD = 0.75          # the CURRENT, established threshold -- unchanged
MIN_PROBA_TO_SCAN = 0.60  # per the plan: start at "near-accepted" signals, not every bar
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0

BUCKETS = [(0.60, 0.65), (0.65, 0.675), (0.675, 0.70), (0.70, 0.725), (0.725, 0.75), (0.75, 1.01)]

FEATURE_COLS = ["realized_vol_30", "atr_norm", "dist_ema20_atr", "ema_slope_20",
                "rel_volume_20", "volume_accel", "range_pos_60", "ret_1", "ret_5", "ret_60"]


def resolve_with_mfe_mae(entry_price: float, close_arr: np.ndarray, i: int, stop_distance: float):
    path = close_arr[i:i + LOOKAHEAD + 1] / entry_price - 1.0
    mae = float(path.min())
    mfe = float(path.max())
    peak, activated = -np.inf, False
    for x in path:
        if x <= -stop_distance:
            return -stop_distance - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, mfe, mae
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, mfe, mae
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, mfe, mae


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

    all_bars = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df = load_split(symbol, "train", verbose=False)
        train_feats = build_feature_matrix(train_df)
        train_proba = model.predict_proba(train_feats)
        train_close = train_df["close"].to_numpy()
        n = len(train_close)

        # The CURRENTLY-established filter + stop, for reference/comparison (unchanged).
        train_selected_current = train_proba > THRESHOLD
        range_pos_cut = train_feats.loc[train_selected_current, "range_pos_60"].median()
        vol_cut = train_feats.loc[train_selected_current, "realized_vol_30"].median()
        train_ema_slope = train_feats["ema_slope_20"].to_numpy()
        train_ret_1 = train_feats["ret_1"].to_numpy()
        current_filtered = (
            train_selected_current
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        current_trades = build_trades_with_mae_mfe(train_close, current_filtered, train_ema_slope, train_ret_1)
        stop_distance = float(np.percentile(np.abs([t["mae"] for t in current_trades]), STOP_PCT_PERCENTILE))
        print(f"{symbol}: currently-established stop_distance={stop_distance*100:.2f}% "
              f"(from {len(current_trades)} currently-traded TRAIN entries)")

        proba_arr = train_proba.to_numpy()
        valid = np.where((proba_arr > MIN_PROBA_TO_SCAN) & (np.arange(n) < n - LOOKAHEAD - 1))[0]
        print(f"{symbol}: scanning {len(valid)} bars with proba>{MIN_PROBA_TO_SCAN} (out of {n:,} total TRAIN bars)")

        range_pos_arr = train_feats["range_pos_60"].to_numpy()
        vol_arr = train_feats["realized_vol_30"].to_numpy()
        passes_filter_arr = (range_pos_arr < range_pos_cut) & (vol_arr > vol_cut)
        feat_arr = train_feats[FEATURE_COLS].to_numpy()

        for i in valid:
            entry_price = train_close[i]
            ret, mfe, mae = resolve_with_mfe_mae(entry_price, train_close, i, stop_distance)
            all_bars.append({
                "symbol": symbol, "idx": i, "proba": proba_arr[i],
                "passes_current_filter": bool(passes_filter_arr[i]),
                "net_return": ret, "mfe": mfe, "mae": mae,
                **{f: feat_arr[i, j] for j, f in enumerate(FEATURE_COLS)},
            })

    df = pd.DataFrame(all_bars)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "missed_winners_raw.csv")
    df.to_csv(out_path, index=False)
    print(f"\n{len(df)} total scanned bars saved -> {out_path}\n")

    for symbol in ["ETHUSDT", "BTCUSDT"]:
        sub_sym = df[df["symbol"] == symbol]
        print("=" * 120)
        print(f"  {symbol} — probability bucket breakdown (TRAIN, exploratory, non-sequential)")
        print("=" * 120)
        print(f"  {'bucket':<14}{'filter':<10}{'n':>7}{'win%':>7}{'avg_ret%':>10}{'PF':>8}"
              f"{'avg_MFE%':>10}{'avg_MAE%':>10}{'total_pot_ret%':>15}")
        for lo, hi in BUCKETS:
            bucket_label = f"{lo:.3f}-{hi:.3f}" if hi <= 1.0 else f"{lo:.3f}+"
            bucket_df = sub_sym[(sub_sym["proba"] >= lo) & (sub_sym["proba"] < hi)]
            for filt_label, filt_val in [("any", None), ("passes", True), ("fails", False)]:
                b = bucket_df if filt_val is None else bucket_df[bucket_df["passes_current_filter"] == filt_val]
                n = len(b)
                if n == 0:
                    continue
                win = (b["net_return"] > 0).mean() * 100
                avg_ret = b["net_return"].mean() * 100
                wins, losses = b.loc[b["net_return"] > 0, "net_return"], b.loc[b["net_return"] <= 0, "net_return"]
                pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
                avg_mfe = b["mfe"].mean() * 100
                avg_mae = b["mae"].mean() * 100
                total_pot = avg_ret * n
                print(f"  {bucket_label:<14}{filt_label:<10}{n:>7}{win:>7.1f}{avg_ret:>10.4f}{pf:>8.3f}"
                      f"{avg_mfe:>10.4f}{avg_mae:>10.4f}{total_pot:>15.2f}")
        print()


if __name__ == "__main__":
    main()
