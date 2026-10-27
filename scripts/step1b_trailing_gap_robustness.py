"""
scripts/step1b_trailing_gap_robustness.py — follow-up to Experiment 1
(docs/research_plan_status.md): the stress test found BASELINE_CANDIDATE_V1
fails under a "combined worst case" (PF<1 on both symbols), and traced the
main cause to the trailing stop's tight 0.30% trail distance being smaller
than a realistic fill gap (0.25-0.50%). Per the plan's own decision rule,
this pulls Étape 9 ("trailing local robustness") forward, ahead of Étape 2,
to check one specific question: does a WIDER trail distance materially
improve gap-robustness, and if so, is there still a "plateau" (multiple
nearby configs behaving similarly, not a single overfit spike) rather than
a cliff?

Sweeps trail_dist locally around the frozen 0.30% point, holding
activate_at=0.63% fixed (this is a targeted follow-up, not the full
Étape 9 activation x distance grid -- that's still pending), and reports
for each: frictionless PF/return, PF/return at gap=0.25% and gap=0.50%,
and the full "combined worst case" from Experiment 1.

Usage:
    python scripts/step1b_trailing_gap_robustness.py
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
    TRAIN_SYMBOLS, HORIZON, LEVERAGE, ACTIVATE_AT,
    get_setup, get_sequential_trades, historical_mae_stop_distance,
    simulate_stressed, load_funding,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIL_DISTANCES = [0.0015, 0.0020, 0.0025, 0.0030, 0.0040, 0.0050, 0.0060, 0.0080, 0.0100, 0.0120, 0.0150]


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

    all_rows = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        df_val, filtered_mask, ema_slope_arr, ret_1_arr = get_setup(symbol, model)
        funding = load_funding(symbol)
        close_arr = df_val["close"].to_numpy()
        timestamps = df_val.index
        trades = get_sequential_trades(df_val, filtered_mask, ema_slope_arr, ret_1_arr)
        stop_distance = historical_mae_stop_distance(trades)
        leverage = LEVERAGE[symbol]

        print("=" * 100)
        print(f"  {symbol} — trail distance sweep (activate_at fixed at {ACTIVATE_AT*100:.2f}%), "
              f"n={len(trades)}, leverage={leverage}x, stop={stop_distance*100:.2f}%")
        print("=" * 100)
        print(f"  {'trail':>8}{'frictionless PF':>18}{'ret%':>9}  |{'gap.25 PF':>12}{'ret%':>9}"
              f"  |{'gap.50 PF':>12}{'ret%':>9}  |{'worst-case PF':>16}{'ret%':>9}")

        for trail in TRAIL_DISTANCES:
            base = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage,
                                      trail_dist=trail)
            g25 = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage,
                                     trail_dist=trail, gap_extra=0.0025)
            g50 = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage,
                                     trail_dist=trail, gap_extra=0.0050)
            worst = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage,
                                       trail_dist=trail, slip_mult_entry=2, slip_mult_trailing=2,
                                       slip_mult_stop=2, slip_mult_time=2, gap_extra=0.0025,
                                       funding_mult=2, entry_delay=1)
            marker = "  <-- FROZEN" if abs(trail - 0.0030) < 1e-9 else ""
            print(f"  {trail*100:>6.2f}%{base['profit_factor']:>18.3f}{base['total_return_pct']:>9.2f}"
                  f"  |{g25['profit_factor']:>12.3f}{g25['total_return_pct']:>9.2f}"
                  f"  |{g50['profit_factor']:>12.3f}{g50['total_return_pct']:>9.2f}"
                  f"  |{worst['profit_factor']:>16.3f}{worst['total_return_pct']:>9.2f}{marker}")
            all_rows.append({"symbol": symbol, "trail_dist": trail,
                              "pf_frictionless": base["profit_factor"], "ret_frictionless": base["total_return_pct"],
                              "pf_gap25": g25["profit_factor"], "ret_gap25": g25["total_return_pct"],
                              "pf_gap50": g50["profit_factor"], "ret_gap50": g50["total_return_pct"],
                              "pf_worst": worst["profit_factor"], "ret_worst": worst["total_return_pct"]})
        print()

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step1b_trailing_gap_robustness.csv")
    pd.DataFrame(all_rows).to_csv(out_path, index=False)
    print(f"Raw results saved -> {out_path}")


if __name__ == "__main__":
    main()
