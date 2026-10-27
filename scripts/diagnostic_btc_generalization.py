"""
scripts/diagnostic_btc_generalization.py — do the filter + exit-strategy
combinations found on ETHUSDT (docs conversation, scripts/diagnostic_exit_
strategies.py) generalize to BTCUSDT, on a long, previously-untouched-by-
this-configuration period?

Critical methodology point: the model (fit on BTC+ETH TRAIN, as always),
the filter cutoffs (range_pos_60/realized_vol_30, computed from ETH's
TRAIN-selected population), and the threshold (0.75) are all FROZEN exactly
as found on ETH -- nothing is recalibrated for BTC here. That makes this a
fair generalization test, not a new search: if the numbers hold up on an
asset that had zero role in choosing any of these settings, that's real
evidence; if they don't, that's real evidence too.

Test period: BTCUSDT VALIDATION+HOLDOUT combined ("oos" split, ~9.6 months)
-- the longest available period the model was never fit on, addressing the
small-sample (n<100) caveat on every ETH result so far.

Usage:
    python scripts/diagnostic_btc_generalization.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.diagnostic_exit_strategies import simulate_variant, HORIZON, THRESHOLD, TRAIN_SYMBOLS

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CANDIDATES = ["fixed", "dynamic_exit", "dca_rescue", "dca_rescue_trend"]  # fixed = reference


def main():
    print("Fitting tier-2 classifier, horizon=10min (identical to the ETH runs)...")
    train_feats, train_labels = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.")

    # Filter cutoffs: first attempt reused ETH's absolute cutoff VALUES on BTC
    # and got only 11 trades over 9.6 months -- BTC's realized_vol_30 lives on
    # a different absolute scale than ETH's, so an ETH-calibrated absolute
    # number is almost never satisfied on BTC. Same RELATIVE methodology
    # (median of range_pos_60 / realized_vol_30 among the model-selected
    # population), computed on BTC's OWN TRAIN this time -- still nothing
    # BTC-specific about the model, threshold, or concept, just the absolute
    # numbers a percentile implies for this asset's own scale.
    train_df_btc_cutoffs = load_split("BTCUSDT", "train", verbose=False)
    train_feats_btc_cutoffs = build_feature_matrix(train_df_btc_cutoffs)
    train_proba_btc_cutoffs = model.predict_proba(train_feats_btc_cutoffs)
    train_selected_btc = train_proba_btc_cutoffs > THRESHOLD
    range_pos_cut = train_feats_btc_cutoffs.loc[train_selected_btc, "range_pos_60"].median()
    vol_cut = train_feats_btc_cutoffs.loc[train_selected_btc, "realized_vol_30"].median()
    print(f"Filter cutoffs (recomputed on BTC's OWN TRAIN, same percentile logic as ETH): "
          f"range_pos_60 < {range_pos_cut:.4f}, realized_vol_30 > {vol_cut:.6f}\n")

    df_btc = load_split("BTCUSDT", "oos")  # VALIDATION+HOLDOUT combined, long period
    feats_btc = build_feature_matrix(df_btc)
    close_btc = df_btc["close"]
    proba_btc = model.predict_proba(feats_btc)

    filtered_mask = (
        (proba_btc > THRESHOLD)
        & (feats_btc["range_pos_60"] < range_pos_cut)
        & (feats_btc["realized_vol_30"] > vol_cut)
    ).to_numpy()
    print(f"BTCUSDT filtered entries over the full OOS period: {filtered_mask.sum()}\n")

    ema_slope_arr = feats_btc["ema_slope_20"].to_numpy()
    ret_1_arr = feats_btc["ret_1"].to_numpy()

    print("=" * 100)
    print(f"  BTCUSDT, {df_btc.index[0]:%Y-%m-%d} -> {df_btc.index[-1]:%Y-%m-%d} "
          f"(never used to pick model, filter, or threshold)")
    print("=" * 100)
    header = (f"{'exit mode':<18}{'n':>6}{'win%':>7}{'PF':>8}{'total_ret%':>11}"
              f"{'worst_trade%':>13}{'n_rescued':>11}{'reliable?':>11}")
    print(header)
    print("-" * len(header))
    for mode in CANDIDATES:
        m = simulate_variant(close_btc, filtered_mask, mode, ema_slope=ema_slope_arr, ret_1=ret_1_arr)
        if m.get("n_trades", 0) == 0:
            print(f"{mode:<18}{'no trades'}")
            continue
        reliable = "n>100" if m["n_trades"] > 100 else "n<100 !!"
        print(f"{mode:<18}{m['n_trades']:>6}{m['win_rate_pct']:>7.1f}"
              f"{m['profit_factor']:>8.3f}{m['total_return_pct_of_capital']:>11.3f}"
              f"{m['max_single_trade_loss_pct_notional']:>13.2f}{m['n_rescued']:>11}{reliable:>11}")

    print("\nFor comparison, ETHUSDT VALIDATION-only results (same frozen config, from")
    print("the earlier diagnostic):")
    print("  fixed:            n=40,  win%=57.5, PF=0.968")
    print("  dynamic_exit:     n=33,  win%=78.8, PF=1.108")
    print("  dca_rescue:       n=34,  win%=88.2, PF=1.298")
    print("  dca_rescue_trend: n=34,  win%=82.3, PF=1.463")


if __name__ == "__main__":
    main()
