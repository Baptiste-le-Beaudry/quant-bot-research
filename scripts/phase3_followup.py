"""
scripts/phase3_followup.py — Phase 3 continuation, directly motivated by
phase3_baseline.py's own results on BTCUSDT TRAIN:

1. Profit factor rose monotonically with horizon (5->30min) for every rule
   AND the null baseline. Extend the horizon range further (60/120/240min)
   to see whether that trend actually crosses PF=1, or plateaus below it.
2. Rolling return-autocorrelation cleanly separated forward returns (bigger
   positive autocorrelation -> bigger positive forward return, monotonic
   across horizons). B_mean_reversion was the best of the three rule
   families — test it gated by the OPPOSITE regime (autocorr < -0.05, i.e.
   only take mean-reversion trades when the market is actually behaving
   like a mean-reverting process, not fighting a momentum regime).

Same TRAIN-slice-only discipline as phase3_baseline.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import DATA_DIR, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.backtest.simple_engine import evaluate_signal, null_baseline
from scripts.phase3_baseline import (
    load_train_slice, signal_momentum_breakout, signal_mean_reversion,
    signal_trend_pullback, rising_edge, rolling_vwap,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EXTENDED_HORIZONS = [30, 60, 120, 240]


def regime_filtered_mean_reversion(df: pd.DataFrame, window: int = 60, z_thresh: float = 2.0,
                                    autocorr_thresh: float = -0.05) -> pd.Series:
    """Same entry as signal_mean_reversion, gated to only fire when the
    market is locally mean-reverting (negative return autocorrelation) —
    the premise of a snap-back-to-VWAP trade should hold better there than
    while fighting a momentum regime."""
    vwap = rolling_vwap(df, window)
    dist = df["close"] - vwap
    z = dist / dist.rolling(window).std()

    ret = df["close"].pct_change()
    lag1 = ret.shift(1)
    autocorr = (ret.rolling(window).cov(lag1) / lag1.rolling(window).var()).clip(-1, 1)
    mean_reverting_regime = autocorr < autocorr_thresh

    bull_confirm = df["close"] > df["open"]
    bear_confirm = df["close"] < df["open"]

    long_cond = rising_edge((z < -z_thresh) & bull_confirm & mean_reverting_regime)
    short_cond = rising_edge((z > z_thresh) & bear_confirm & mean_reverting_regime)

    signal = pd.Series(0, index=df.index)
    signal[long_cond] = 1
    signal[short_cond] = -1
    return signal


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    df = load_train_slice(args.symbol)

    print(f"Round-trip cost assumed per trade: {(ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST)*100:.3f}%\n")

    strategies = {
        "A_momentum_breakout": signal_momentum_breakout(df),
        "B_mean_reversion": signal_mean_reversion(df),
        "C_trend_pullback": signal_trend_pullback(df),
        "B2_meanrev_regime_filtered": regime_filtered_mean_reversion(df),
    }
    for name, sig in strategies.items():
        n_long, n_short = int((sig == 1).sum()), int((sig == -1).sum())
        print(f"{name}: {n_long} long, {n_short} short signals")
    print()

    header = (f"{'strategy':<28}{'horizon':>8}{'n_trades':>10}{'win%':>8}"
              f"{'PF':>8}{'expectancy%':>13}{'naive_ret%':>12}")
    print(header)
    print("-" * len(header))

    for horizon in EXTENDED_HORIZONS:
        for name, sig in strategies.items():
            m = evaluate_signal(df["close"], sig, horizon)
            if m.get("n_trades", 0) == 0:
                print(f"{name:<28}{horizon:>8}{'(no trades)':>10}")
                continue
            print(f"{name:<28}{horizon:>8}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
                  f"{m['profit_factor']:>8.3f}{m['expectancy_pct']:>13.5f}"
                  f"{m['total_naive_return_pct']:>12.2f}")
        busiest_n = max((sig != 0).sum() for sig in strategies.values())
        null = null_baseline(df["close"], int(busiest_n), horizon)
        if null.get("n_trades", 0) > 0:
            print(f"{'NULL(random)':<28}{horizon:>8}{null['n_trades']:>10}{null['win_rate_pct']:>8.1f}"
                  f"{null['profit_factor']:>8.3f}{null['expectancy_pct']:>13.5f}"
                  f"{null['total_naive_return_pct']:>12.2f}")
        print()


if __name__ == "__main__":
    main()
