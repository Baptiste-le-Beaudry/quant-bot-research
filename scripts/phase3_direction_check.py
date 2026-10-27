"""
scripts/phase3_direction_check.py — is B2's apparent edge (phase3_followup.py)
real timing skill, or just long-side market beta picked up during a +96%
bull TRAIN window? Splits LONG-only vs SHORT-only performance: if this is
beta, longs will look great and shorts terrible; if it's a real (if modest)
timing effect, both sides should show *some* edge over their own direction's
null.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np

from quant_bot.backtest.simple_engine import evaluate_signal
from scripts.phase3_baseline import load_train_slice
from scripts.phase3_followup import regime_filtered_mean_reversion

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def directional_null(close: pd.Series, direction: int, n_signals: int, horizon_min: int, seed: int = 7) -> dict:
    """Random entries but ALL in the given direction — the fair comparison
    for a long-only or short-only slice (not the mixed-direction null)."""
    rng = np.random.default_rng(seed)
    valid_idx = close.index[:-horizon_min] if horizon_min > 0 else close.index
    n_signals = min(n_signals, len(valid_idx))
    chosen = rng.choice(valid_idx, size=n_signals, replace=False)
    signal = pd.Series(0, index=close.index)
    signal.loc[chosen] = direction
    return evaluate_signal(close, signal, horizon_min)


def main():
    df = load_train_slice("BTCUSDT")
    sig = regime_filtered_mean_reversion(df)
    longs, shorts = sig[sig == 1], sig[sig == -1]
    print(f"B2_meanrev_regime_filtered: {len(longs)} long signals, {len(shorts)} short signals\n")

    header = f"{'side':<8}{'horizon':>8}{'n_trades':>10}{'win%':>8}{'PF':>8}{'expectancy%':>13}"
    print(header)
    print("-" * len(header))
    for horizon in [30, 60, 120, 240]:
        for label, sub in [("LONG", longs), ("SHORT", shorts)]:
            sub_signal = pd.Series(0, index=df.index)
            sub_signal.loc[sub.index] = sub
            m = evaluate_signal(df["close"], sub_signal, horizon)
            if m.get("n_trades", 0) == 0:
                continue
            print(f"{label:<8}{horizon:>8}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
                  f"{m['profit_factor']:>8.3f}{m['expectancy_pct']:>13.5f}")
            direction = 1 if label == "LONG" else -1
            null_m = directional_null(df["close"], direction, len(sub), horizon)
            if null_m.get("n_trades", 0) > 0:
                print(f"{'  null':<8}{horizon:>8}{null_m['n_trades']:>10}{null_m['win_rate_pct']:>8.1f}"
                      f"{null_m['profit_factor']:>8.3f}{null_m['expectancy_pct']:>13.5f}")
        print()


if __name__ == "__main__":
    main()
