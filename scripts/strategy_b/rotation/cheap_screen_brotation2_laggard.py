"""scripts/strategy_b/rotation/cheap_screen_brotation2_laggard.py —
STRATEGY_ID = B_ROTATION, Experiment BR2: cross-sectional MEAN-REVERSION
(hold the bottom-2 trailing-7-day performers instead of the top-2). See
docs/strategy_b/rotation/STRATEGY_B_ROTATION_SPEC.md REVISION 1. Same
universe/lookback/K/costs as BR1 -- only the selection DIRECTION flips
(ranks <= TOP_K on ascending rank instead of descending).

Usage:
    python scripts/strategy_b/rotation/cheap_screen_brotation2_laggard.py
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
VALIDATION_FRACTION = 0.30


def load_daily_close(symbol: str) -> pd.Series:
    pattern = os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")
    files = sorted(glob.glob(pattern))
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df["close"].resample("1D").last().dropna()


def main():
    print("=" * 100)
    print("  STRATEGY B_ROTATION -- Experiment BR2: cross-sectional mean-reversion (laggard) cheap screen")
    print(f"  universe={UNIVERSE}")
    print(f"  params: lookback={LOOKBACK_DAYS}d bottom_k={TOP_K} (frozen a priori, no grid search)")
    print("=" * 100)

    closes = {sym: load_daily_close(sym) for sym in UNIVERSE}
    price = pd.DataFrame(closes)
    price = price[(price.index >= DATA_START) & (price.index <= SAFE_END)].dropna()
    print(f"  Common range: {price.index[0].date()} -> {price.index[-1].date()}  ({len(price)} bars)")

    trailing_ret = price / price.shift(LOOKBACK_DAYS) - 1.0
    daily_ret = price.pct_change()
    # ONLY DIFFERENCE FROM BR1: ascending=True (rank 1 = WORST performer -> bottom_k selected)
    ranks = trailing_ret.rank(axis=1, ascending=True, method="first")
    selected = ranks <= TOP_K

    split_idx = int(len(price) * (1 - VALIDATION_FRACTION))
    split_date = price.index[split_idx]
    print(f"  VALIDATION: {split_date.date()} -> {price.index[-1].date()}")

    portfolio_daily_ret, n_rebalance_events = [], 0
    prev_selected = None
    dates = price.index
    for i in range(LOOKBACK_DAYS, len(dates) - 1):
        t, t1 = dates[i], dates[i + 1]
        sel = selected.loc[t]
        chosen = sel[sel].index.tolist()
        if not chosen:
            portfolio_daily_ret.append((t1, 0.0))
            continue
        gross = float(daily_ret.loc[t1, chosen].mean())
        cost = 0.0
        if prev_selected is not None:
            entered = set(chosen) - prev_selected
            n_rebalance_events += len(entered)
            cost = ROUND_TRIP_COST * (len(entered) / max(1, len(chosen)))
        prev_selected = set(chosen)
        portfolio_daily_ret.append((t1, gross - cost))

    ret_df = pd.DataFrame(portfolio_daily_ret, columns=["date", "ret"]).set_index("date")
    val_ret = ret_df[ret_df.index >= split_date]["ret"]

    total_return_pct = float(((1 + val_ret).prod() - 1) * 100)
    wins, losses = val_ret[val_ret > 0], val_ret[val_ret <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    win_rate = float((val_ret > 0).mean() * 100)
    eq = (1 + val_ret).cumprod()
    max_dd_pct = float(((eq - eq.cummax()) / eq.cummax()).min() * 100)
    print(f"\n  VALIDATION results: n_days={len(val_ret)}  total_return={total_return_pct:+.2f}%  "
          f"PF={pf:.3f}  win_rate={win_rate:.1f}%  MaxDD={max_dd_pct:.2f}%  n_rebalance_entries={n_rebalance_events}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "strategy_b", "rotation", "brotation2_laggard_daily_returns.csv")
    ret_df.to_csv(out_path)
    print(f"\nSaved -> {out_path}")

    # Baseline comparison (equal-weight-9, computed inline here since BR1's null
    # baseline used the same price/window -- avoid a second heavy reload).
    ew_ret = daily_ret[daily_ret.index >= split_date][UNIVERSE].mean(axis=1)
    ew_eq = (1 + ew_ret).cumprod()
    ew_total = float((ew_eq.iloc[-1] - 1) * 100)
    ew_dd = float(((ew_eq - ew_eq.cummax()) / ew_eq.cummax()).min() * 100)
    print(f"\n  BASELINE (equal-weight all-9, same window): total_return={ew_total:+.2f}%  MaxDD={ew_dd:.2f}%")

    print("\n" + "=" * 100)
    print("  PRE-REGISTERED REJECTION CHECK (STRATEGY_B_ROTATION_SPEC.md REVISION 1)")
    print("=" * 100)
    dominated = (total_return_pct < ew_total) and (max_dd_pct < ew_dd)
    if total_return_pct < 0 or pf <= 1.0:
        print("  VERDICT: REJECT per binary criterion (negative return or PF<=1).")
    elif dominated:
        print(f"  VERDICT: REJECT -- dominated by equal-weight baseline on both return ({total_return_pct:+.2f}% "
              f"< {ew_total:+.2f}%) and MaxDD ({max_dd_pct:.2f}% < {ew_dd:.2f}%).")
    else:
        print("  VERDICT: does NOT trigger REJECT (binary or baseline-dominance) -- proceed to further validation.")


if __name__ == "__main__":
    main()
