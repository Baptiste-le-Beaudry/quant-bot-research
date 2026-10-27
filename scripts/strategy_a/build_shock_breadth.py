"""scripts/strategy_a/build_shock_breadth.py — STRATEGY_ID = A,
Experiment 41, Step 1: build a causal cross-symbol "shock breadth"
1-minute time series. SHADOW/ANALYTICAL infrastructure only.

Definition: for each symbol in the 9-symbol baseline universe, compute
return_15m(t) = close[t]/close[t-15] - 1 (causal). Each symbol's own
"acute decline" threshold is its OWN 10th percentile of return_15m
over its PRE-2024-01-01 history (TRAIN-only in the sense of "learn from
earlier, apply to later" -- see Step 2 script for the population-choice
discussion). shock_breadth(t) = fraction of symbols ACTIVE at time t
(not yet past their own HOLDOUT_START, and with enough history to have
a valid return_15m) whose return_15m(t) is below their own threshold.

HOLDOUT DISCIPLINE: each symbol's price series is truncated at its own
HOLDOUT_START before any computation, exactly as in
scripts/strategy_a/build_regime_context.py.

Usage:
    python scripts/strategy_a/build_shock_breadth.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR
from quant_bot.data.splits import HOLDOUT_START as _HOLDOUT_START_RAW

HOLDOUT_START = {k: pd.Timestamp(v, tz="UTC") for k, v in _HOLDOUT_START_RAW.items()}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT"]
RET_WINDOW_MIN = 15
CALIBRATION_CUTOFF = pd.Timestamp("2024-01-01", tz="UTC")  # "learn from earlier, apply to later"
DECLINE_PERCENTILE = 10  # per-symbol "acute decline" = bottom 10% of its own PRE-2024 return_15m


def load_1min_close(symbol: str) -> pd.Series:
    files = sorted(glob.glob(os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")))
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    close = df["close"]
    close = close[close.index < HOLDOUT_START[symbol]]  # never read at/after this symbol's own lock
    return close


def main():
    print("=" * 100)
    print("  STRATEGY A -- Experiment 41 Step 1: build shock_breadth 1-min time series")
    print("=" * 100)

    closes, thresholds = {}, {}
    for sym in UNIVERSE:
        c = load_1min_close(sym)
        closes[sym] = c
        ret15 = c.pct_change(RET_WINDOW_MIN)
        pre_cal = ret15[ret15.index < CALIBRATION_CUTOFF].dropna()
        thr = float(np.percentile(pre_cal, DECLINE_PERCENTILE))
        thresholds[sym] = thr
        print(f"  {sym}: {len(c):,} bars, {c.index[0]} -> {c.index[-1]}  "
              f"(HOLDOUT_START={HOLDOUT_START[sym].date()})  "
              f"PRE-2024 p{DECLINE_PERCENTILE} of {RET_WINDOW_MIN}min return = {thr*100:.3f}% (n_cal={len(pre_cal):,})")

    print("\n  Aligning all 9 symbols onto a common 1-min index (union, forward-fill NOT used -- NaN where a "
          "symbol has no data yet or has been truncated at its own HOLDOUT)...")
    price = pd.DataFrame(closes)
    ret15_df = price.pct_change(RET_WINDOW_MIN)

    is_shock = pd.DataFrame(index=ret15_df.index, columns=UNIVERSE, dtype="boolean")
    for sym in UNIVERSE:
        # BUG GUARD: plain `ret15_df[sym] < thresholds[sym]` silently evaluates NaN < x as False
        # (numpy comparison semantics), which would wrongly count a not-yet-listed symbol as
        # "active and not shocked" instead of correctly excluding it. Mask explicitly.
        valid = ret15_df[sym].notna()
        col = pd.Series(pd.NA, index=ret15_df.index, dtype="boolean")
        col[valid] = ret15_df.loc[valid, sym] < thresholds[sym]
        is_shock[sym] = col

    n_active = is_shock.notna().sum(axis=1)
    n_shocked = is_shock.sum(axis=1)
    shock_breadth = (n_shocked / n_active.replace(0, np.nan))

    # Regression test: n_active must vary over time (fewer symbols active before all 9 are listed),
    # not be stuck at a constant -- this is exactly the bug found and fixed above.
    n_active_unique = n_active.dropna().unique()
    early_window = n_active[n_active.index < pd.Timestamp("2020-02-10", tz="UTC")]  # before BNB (latest of the 9) starts
    assert len(n_active_unique) > 1, "REGRESSION: n_active_symbols is constant -- the NaN-masking bug is back."
    assert early_window.dropna().max() < 9, (
        "REGRESSION: symbols appear 'active' before they were actually listed -- NaN-masking bug is back.")
    print(f"\n  Regression test PASS: n_active_symbols varies over time (values observed: "
          f"{sorted(n_active_unique)}), and pre-2020-02-10 window never shows all 9 as active "
          f"(max={early_window.dropna().max()}).")

    out = pd.DataFrame({"shock_breadth": shock_breadth, "n_active_symbols": n_active, "n_shocked_symbols": n_shocked})
    out = out.dropna(subset=["shock_breadth"])
    print(f"\n  shock_breadth series: {len(out):,} minutes, {out.index[0]} -> {out.index[-1]}")
    print(f"  n_active_symbols distribution:\n{out['n_active_symbols'].value_counts().sort_index().to_string()}")
    print(f"\n  shock_breadth distribution (all minutes):\n{out['shock_breadth'].describe().to_string()}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "strategy_a", "shock_breadth_1min.csv")
    out.to_csv(out_path)
    print(f"\nSaved -> {out_path}")

    thr_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "strategy_a", "shock_breadth_per_symbol_thresholds.csv")
    pd.Series(thresholds, name="decline_threshold_15min_return").to_csv(thr_path)
    print(f"Saved -> {thr_path}")


if __name__ == "__main__":
    main()
