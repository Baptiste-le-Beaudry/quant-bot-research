"""
scripts/multi_crypto_correlation.py — multi-crypto expansion plan, Etape 11:
correlation / simultaneous-trade analysis between each walk-forward-
validated new symbol and BTC/ETH, using the trade exports (BTC/ETH:
docs/walk_forward_v3_trades_export.csv; new symbols:
docs/multi_crypto_wf_{SYMBOL}_trades.csv, produced by
scripts/multi_crypto_walkforward.py). A high-PF but highly-correlated
addition is worth less than a lower-PF, uncorrelated one -- this script
exists to make that trade-off visible before Etape 12 picks the portfolio.

Two measures, both intentionally simple/robust to very different trade
counts per symbol:
  1. Daily P&L correlation: resample each symbol's per-trade raw_return*
     (implied $ pnl at a fixed notional, since leverage/stop differs per
     symbol/fold) into a daily sum, align on date, Pearson-correlate pairs.
  2. Simultaneous-trade overlap: for each pair, fraction of symbol A's
     trades whose [entry_time, exit_time) window overlaps at least one
     symbol B trade -- a high-PF pair that never fires together is a much
     more useful diversifier than the raw P&L correlation alone might
     suggest (or refute).

Usage:
    python scripts/multi_crypto_correlation.py --symbols SOLUSDT,BNBUSDT
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
BTC_ETH_PATH = os.path.join(DOCS, "walk_forward_v3_trades_export.csv")


def load_trades(symbol: str, tag: str = "") -> pd.DataFrame:
    if symbol in ("BTCUSDT", "ETHUSDT"):
        df = pd.read_csv(BTC_ETH_PATH, parse_dates=["entry_time", "exit_time"])
        return df[df["symbol"] == symbol].copy()
    fname = f"multi_crypto_wf_{symbol}_{tag}_trades.csv" if tag else f"multi_crypto_wf_{symbol}_trades.csv"
    path = os.path.join(DOCS, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No walk-forward trade export for {symbol} (tag={tag!r}) at {path}")
    return pd.read_csv(path, parse_dates=["entry_time", "exit_time"])


def daily_pnl_series(df: pd.DataFrame) -> pd.Series:
    """Implied $ pnl at fixed notional=CAPITAL*RISK_PCT (matches walk_forward_engine's own
    convention) summed by exit date -- comparable ACROSS symbols since leverage/stop already
    absorbed into raw_return's dollar-equivalent scaling is NOT what we want here (that would
    make a thin-stop symbol dominate); use raw_return directly (pre-leverage, pre-notional) so
    every symbol contributes on the same %-return footing."""
    s = df.set_index(pd.to_datetime(df["exit_time"]))["raw_return"]
    return s.groupby(s.index.date).sum()


def overlap_fraction(a: pd.DataFrame, b: pd.DataFrame) -> float:
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    b_sorted = b.sort_values("entry_time")
    b_starts = b_sorted["entry_time"].to_numpy()
    b_ends = b_sorted["exit_time"].to_numpy()
    n_overlap = 0
    for _, t in a.iterrows():
        idx = np.searchsorted(b_starts, t["exit_time"])
        candidates = range(max(0, idx - 5), min(len(b_sorted), idx + 5))
        if any(b_starts[j] < t["exit_time"] and b_ends[j] > t["entry_time"] for j in candidates):
            n_overlap += 1
    return n_overlap / len(a)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="comma-separated NEW symbols (BTC/ETH always included)")
    args = parser.parse_args()
    entries = args.symbols.split(",")
    parsed = [(e.partition(":")[0], e.partition(":")[2]) for e in entries]
    all_entries = [("BTCUSDT", ""), ("ETHUSDT", "")] + parsed
    all_symbols = [s for s, _ in all_entries]  # display/index labels (tag stripped)

    trades = {s: load_trades(s, tag) for s, tag in all_entries}
    for s in all_symbols:
        print(f"{s}: {len(trades[s])} trades")

    print("\n" + "=" * 90)
    print("  DAILY P&L CORRELATION (Pearson, raw_return summed by exit date)")
    print("=" * 90)
    series = {s: daily_pnl_series(trades[s]) for s in all_symbols}
    combined = pd.DataFrame(series).fillna(0.0)
    corr = combined.corr()
    print(corr.round(3).to_string())

    print("\n" + "=" * 90)
    print("  SIMULTANEOUS-TRADE OVERLAP (fraction of row-symbol's trades overlapping col-symbol)")
    print("=" * 90)
    header = "".join(f"{s[:8]:>10}" for s in all_symbols)
    print(" " * 10 + header)
    for a in all_symbols:
        vals = []
        for b in all_symbols:
            if a == b:
                vals.append("--")
                continue
            f = overlap_fraction(trades[a], trades[b])
            vals.append(f"{f:.2f}" if f == f else "n/a")
        print(f"{a[:10]:<10}" + "".join(f"{v:>10}" for v in vals))

    print("\nInterpretation: LOW correlation + LOW overlap with BOTH BTC and ETH = genuine "
          "diversifier, worth including even at a lower standalone PF (per the plan's Etape 11 "
          "explicit instruction not to rank survivors by PF alone).")


if __name__ == "__main__":
    main()
