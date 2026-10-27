"""
scripts/step10b_tight_stop_gap_check.py — quick follow-up to Étape 10:
p70's protective stop (ETH 1.97%/19.0x, BTC 1.82%/20.6x) strictly dominated
the registered p90 choice frictionlessly (better PF, better return, still
0 forced liquidations). But a tighter stop is mechanically more exposed to
a FIXED-SIZE fill gap (Experiment 1's main stress finding) -- a 0.25% gap
is 12.7% of a 1.97% stop vs 8.1% of a 3.09% stop. This checks whether p70's
frictionless win survives the same gap stress that broke V1/V2.

Usage:
    python scripts/step10b_tight_stop_gap_check.py
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
from scripts.step1_stress_test import (
    TRAIN_SYMBOLS, HORIZON, get_setup, get_sequential_trades, simulate_stressed, load_funding,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# From step10's TRAIN-calibrated sweep (docs/step10_stop_sweep_raw.csv)
CONFIGS = {
    "ETHUSDT": {"p90 (registered)": (0.0309, 12.1), "p70 (challenger)": (0.0197, 19.0)},
    "BTCUSDT": {"p90 (registered)": (0.0380, 9.9), "p70 (challenger)": (0.0182, 20.6)},
}


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min...")
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
    print(f"{len(kept)} features kept.\n")

    for symbol in ["ETHUSDT", "BTCUSDT"]:
        df_val, filtered_mask, ema_slope_arr, ret_1_arr = get_setup(symbol, model)
        funding = load_funding(symbol)
        close_arr = df_val["close"].to_numpy()
        timestamps = df_val.index
        trades = get_sequential_trades(df_val, filtered_mask, ema_slope_arr, ret_1_arr)

        print("=" * 100)
        print(f"  {symbol} — p90 (registered) vs p70 (challenger) under gap stress")
        print("=" * 100)
        print(f"  {'config':<20}{'gap':>8}{'n':>5}{'PF':>9}{'ret%':>9}{'DD%':>9}")
        for label, (stop_distance, leverage) in CONFIGS[symbol].items():
            for gap in [0.0, 0.0025, 0.0050]:
                r = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage, gap_extra=gap)
                print(f"  {label:<20}{gap*100:>7.2f}%{r.get('n_trades',0):>5}"
                      f"{r.get('profit_factor',float('nan')):>9.3f}{r.get('total_return_pct',float('nan')):>+9.3f}"
                      f"{r.get('max_dd_pct',float('nan')):>+9.3f}")
            worst = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage,
                                       slip_mult_entry=2, slip_mult_trailing=2, slip_mult_stop=2,
                                       slip_mult_time=2, gap_extra=0.0025, funding_mult=2, entry_delay=1)
            print(f"  {label:<20}{'WORST':>8}{worst.get('n_trades',0):>5}"
                  f"{worst.get('profit_factor',float('nan')):>9.3f}{worst.get('total_return_pct',float('nan')):>+9.3f}"
                  f"{worst.get('max_dd_pct',float('nan')):>+9.3f}")
        print()


if __name__ == "__main__":
    main()
