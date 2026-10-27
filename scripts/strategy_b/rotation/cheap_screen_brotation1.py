"""scripts/strategy_b/rotation/cheap_screen_brotation1.py — STRATEGY_ID =
B_ROTATION, Experiment BR1: cross-sectional momentum rotation cheap
screen. See docs/strategy_b/rotation/STRATEGY_B_ROTATION_SPEC.md.
Daily bars, 9-symbol fixed universe, top-2 by trailing-7-day return,
long-only, daily rebalance, no leverage. Frozen a priori parameters
(K=2, lookback=7) -- no grid search.

Usage:
    python scripts/strategy_b/rotation/cheap_screen_brotation1.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UNIVERSE = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "TRXUSDT", "LTCUSDT", "ETCUSDT", "LINKUSDT", "ADAUSDT", "BNBUSDT"]
DATA_START = pd.Timestamp("2020-02-10", tz="UTC")
SAFE_END = pd.Timestamp("2025-03-28", tz="UTC")
LOOKBACK_DAYS = 7
TOP_K = 2
FEE_PER_SIDE = 0.0005
BASE_SLIP_PER_SIDE = 0.0001
ROUND_TRIP_COST = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
VALIDATION_FRACTION = 0.30  # last 30% of the common range = VALIDATION for the cheap-screen verdict


def load_daily_close(symbol: str) -> pd.Series:
    pattern = os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")
    files = sorted(glob.glob(pattern))
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    daily = df["close"].resample("1D").last().dropna()
    return daily


def main():
    print("=" * 100)
    print("  STRATEGY B_ROTATION -- Experiment BR1: cross-sectional momentum cheap screen")
    print(f"  universe={UNIVERSE}")
    print(f"  params: lookback={LOOKBACK_DAYS}d top_k={TOP_K} (frozen a priori, no grid search)")
    print("=" * 100)

    closes = {}
    for sym in UNIVERSE:
        s = load_daily_close(sym)
        closes[sym] = s
        print(f"  {sym}: {len(s)} daily bars, {s.index[0].date()} -> {s.index[-1].date()}")

    price = pd.DataFrame(closes)
    price = price[(price.index >= DATA_START) & (price.index <= SAFE_END)].dropna()
    print(f"\n  Common range after alignment: {price.index[0].date()} -> {price.index[-1].date()}  "
          f"({len(price)} common daily bars, all {len(UNIVERSE)} symbols present -- verified via .dropna())")

    # LOGIC AUDIT: trailing return at day t uses ONLY close[t] and close[t-LOOKBACK_DAYS], both
    # already known by day t's close -- no lookahead. Independent recheck below.
    trailing_ret = price / price.shift(LOOKBACK_DAYS) - 1.0
    sample_day = trailing_ret.index[LOOKBACK_DAYS + 5]
    manual = {}
    for sym in UNIVERSE:
        i = price.index.get_loc(sample_day)
        manual[sym] = price[sym].iloc[i] / price[sym].iloc[i - LOOKBACK_DAYS] - 1.0
    vectorized = trailing_ret.loc[sample_day]
    mismatch = any(abs(manual[s] - vectorized[s]) > 1e-9 for s in UNIVERSE)
    print(f"  LOGIC AUDIT sanity check @ {sample_day.date()}: independent manual recompute vs vectorized -> "
          f"{'MISMATCH!!' if mismatch else 'MATCH'}")

    # Portfolio construction: rank at day t (using trailing_ret[t], known by t's close), hold the
    # top-K for the return REALIZED from t's close to t+1's close (price.pct_change().shift(-1)
    # would leak -- instead we explicitly compute next-day return and align it to day t's ranking).
    daily_ret = price.pct_change()
    ranks = trailing_ret.rank(axis=1, ascending=False, method="first")
    selected = ranks <= TOP_K  # boolean frame: True where symbol is in the top-K as of day t

    split_idx = int(len(price) * (1 - VALIDATION_FRACTION))
    split_date = price.index[split_idx]
    print(f"  TRAIN (not used for calibration in this design, kept for reporting discipline only): "
          f"{price.index[0].date()} -> {split_date.date()}")
    print(f"  VALIDATION (used for the cheap-screen verdict): {split_date.date()} -> {price.index[-1].date()}")

    portfolio_daily_ret, turnover_cost, n_rebalance_events = [], [], 0
    prev_selected = None
    dates = price.index
    for i in range(LOOKBACK_DAYS, len(dates) - 1):
        t, t1 = dates[i], dates[i + 1]
        sel = selected.loc[t]
        chosen = sel[sel].index.tolist()
        if not chosen:
            portfolio_daily_ret.append((t1, 0.0))
            continue
        next_day_returns = daily_ret.loc[t1, chosen]
        gross = float(next_day_returns.mean())

        cost = 0.0
        if prev_selected is not None:
            entered = set(chosen) - prev_selected
            n_rebalance_events += len(entered)
            # cost charged proportionally: entering positions pay round-trip cost once, amortized
            # over this holding day (1/len(chosen) weight each, matching equal-weight construction)
            cost = ROUND_TRIP_COST * (len(entered) / max(1, len(chosen)))
        prev_selected = set(chosen)
        portfolio_daily_ret.append((t1, gross - cost))

    ret_df = pd.DataFrame(portfolio_daily_ret, columns=["date", "ret"]).set_index("date")
    val_ret = ret_df[ret_df.index >= split_date]["ret"]

    total_return_pct = float(((1 + val_ret).prod() - 1) * 100)
    wins, losses = val_ret[val_ret > 0], val_ret[val_ret <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    win_rate = float((val_ret > 0).mean() * 100)
    n_days = len(val_ret)
    eq = (1 + val_ret).cumprod()
    running_max = eq.cummax()
    max_dd_pct = float(((eq - running_max) / running_max).min() * 100)
    print(f"\n  VALIDATION results: n_days={n_days}  total_return={total_return_pct:+.2f}%  "
          f"PF={pf:.3f}  win_rate={win_rate:.1f}%  MaxDD={max_dd_pct:.2f}%  "
          f"n_rebalance_entries={n_rebalance_events}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "strategy_b", "rotation", "brotation1_daily_returns.csv")
    ret_df.to_csv(out_path)
    print(f"\nSaved -> {out_path}")

    print("\n" + "=" * 100)
    print("  PRE-REGISTERED REJECTION CHECK (STRATEGY_B_ROTATION_SPEC.md)")
    print("=" * 100)
    if total_return_pct < 0 or pf <= 1.0:
        print(f"  VERDICT: REJECT per pre-registered criterion (negative VALIDATION return or PF<=1).")
    else:
        print("  VERDICT: does NOT trigger the pre-registered REJECT criterion -- proceed to further validation.")


if __name__ == "__main__":
    main()
