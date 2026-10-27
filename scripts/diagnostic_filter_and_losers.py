"""
scripts/diagnostic_filter_and_losers.py — two follow-ups from the pattern
analysis (docs conversation): (1) does an explicit "near recent low + higher
volatility" filter on top of the model's signal actually improve results,
and (2) what does the price path look like DURING and AFTER losing trades —
does it keep falling past the fixed-horizon exit (exit was near the right
spot), or does it recover afterward (exit was near a local bottom, a
tighter/no exit would have hurt, a later exit would have helped)?

Same h=10min, threshold=0.75 configuration as diagnostic_patterns.py.
Exploratory/in-sample on VALIDATION -- a real test of any filter found
promising here still needs its own out-of-sample check before being
trusted, same discipline as everything else in this project.

Usage:
    python scripts/diagnostic_filter_and_losers.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOL = "ETHUSDT"
TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST


def _pf(returns: np.ndarray) -> float:
    wins, losses = returns[returns > 0], returns[returns <= 0]
    gl = -losses.sum()
    return float(wins.sum() / gl) if gl > 0 else float("inf")


def test_filter_posthoc(feats: pd.DataFrame, entry_times: list, returns: np.ndarray) -> None:
    """NOTE: an earlier version of this re-ran simulate() with a modified
    signal and got IDENTICAL n_trades at every cutoff -- a real bug, not a
    real result. simulate()'s one-trade-at-a-time logic jumps forward by
    horizon_min bars on any qualifying bar; thinning WHICH bar in an
    already-qualifying cluster still passes doesn't remove the trade, it
    just shifts which bar in the cluster gets used as entry, since most
    clusters had at least one bar surviving even a stricter filter. Correct
    approach: split the ALREADY-EXECUTED baseline trades by their own entry
    features directly -- no re-simulation, no clustering artifact."""
    entry_feats = feats.loc[feats.index.isin(entry_times)].reindex(entry_times)
    range_pos_med = entry_feats["range_pos_60"].median()
    vol_med = entry_feats["realized_vol_30"].median()

    meets_both = (entry_feats["range_pos_60"] < range_pos_med) & (entry_feats["realized_vol_30"] > vol_med)
    meets_both = meets_both.to_numpy()

    for label, mask in [("Meets BOTH criteria (low range_pos, high vol)", meets_both),
                         ("Does NOT meet both", ~meets_both)]:
        sub = returns[mask]
        if len(sub) == 0:
            continue
        win_rate = (sub > 0).mean() * 100
        print(f"  {label}: n={len(sub)}, win_rate={win_rate:.1f}%, PF={_pf(sub):.3f}, "
              f"mean_return={sub.mean()*100:.4f}%")


def losing_trade_paths(close: pd.Series, entry_times: list, returns: np.ndarray,
                        horizon_min: int, extended_bars: int = 40) -> None:
    losers = [t for t, r in zip(entry_times, returns) if r <= 0]
    close_arr = close.to_numpy()
    n = len(close_arr)
    pos = {t: i for i, t in enumerate(close.index)}

    mae_list, worst_at_exit, recovered_list, recovery_bars = [], [], [], []
    for t in losers:
        i = pos.get(t)
        if i is None or i + extended_bars >= n:
            continue
        entry_price = close_arr[i]
        path_ret = close_arr[i:i + extended_bars + 1] / entry_price - 1.0

        hold_path = path_ret[:horizon_min + 1]
        mae = hold_path.min()  # worst point DURING the actual hold
        exit_ret = path_ret[horizon_min]
        # was the exit point the worst point of the hold, or had it already
        # started recovering from something worse?
        worst_at_exit.append(np.isclose(exit_ret, mae))

        post_exit = path_ret[horizon_min:]
        recovers = bool((post_exit > 0).any())
        recovered_list.append(recovers)
        if recovers:
            recovery_bars.append(int(np.argmax(post_exit > 0)))
        mae_list.append(mae * 100)

    n_analyzed = len(mae_list)
    print(f"Losing trades analyzed: {n_analyzed}")
    print(f"Average max adverse excursion during hold: {np.mean(mae_list):.4f}%")
    print(f"Trades where the horizon-exit point WAS the worst point of the hold "
          f"(price kept falling right up to exit): {np.mean(worst_at_exit)*100:.1f}%")
    print(f"Trades that recover to breakeven-or-better within {extended_bars}min AFTER "
          f"the exit: {np.mean(recovered_list)*100:.1f}%")
    if recovery_bars:
        print(f"  Of those that recover: median {np.median(recovery_bars):.0f} extra minutes needed")


def main():
    print("Fitting tier-2 classifier, horizon=10min...")
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

    df_val = load_split(SYMBOL, "validation", verbose=False)
    feats_val = build_feature_matrix(df_val)
    close_val = df_val["close"]
    proba = model.predict_proba(feats_val)

    print("=" * 70)
    print("  PART 1: explicit 'near recent low + elevated volatility' filter")
    print("=" * 70)
    baseline = simulate(close_val, proba, HORIZON, THRESHOLD, capital=10_000.0, risk_pct=0.01, cost_pct=COST_PCT)
    print(f"Baseline (model signal only, threshold={THRESHOLD}): "
          f"n={baseline['n_trades']}, win%={baseline['win_rate_pct']}, PF={baseline['profit_factor']}")

    test_filter_posthoc(feats_val, baseline["trade_entry_times"], baseline["trade_returns"])

    print("\n" + "=" * 70)
    print("  PART 2: what happens DURING and AFTER losing trades")
    print("=" * 70)
    losing_trade_paths(close_val, baseline["trade_entry_times"], baseline["trade_returns"], HORIZON)


if __name__ == "__main__":
    main()
