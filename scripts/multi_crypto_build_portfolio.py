"""
scripts/multi_crypto_build_portfolio.py — multi-crypto expansion plan,
Etape 12: concatenate BTC/ETH's V3 trade export
(docs/walk_forward_v3_trades_export.csv) with each walk-forward-validated
new symbol's export (docs/multi_crypto_wf_{SYMBOL}_trades.csv, produced by
scripts/multi_crypto_walkforward.py) into one combined trade population,
same schema, sorted by entry_time -- ready for
scripts/multi_crypto_risk_sweep.py.

Only symbols the researcher has actually decided to include (survived
screen -> walk-forward -> stress -> correlation, per Experiment 33's own
criteria) should be passed -- this script does no filtering itself, it's
deliberately a dumb concatenation step so the inclusion decision stays
explicit and visible in the command line / docs, not buried in a script.

Usage:
    python scripts/multi_crypto_build_portfolio.py --symbols SOLUSDT,BNBUSDT --out docs/multi_crypto_portfolio_trades.csv

A symbol entry may carry an optional ":tag" suffix (e.g. "SOLUSDT:transfer") to pick
docs/multi_crypto_wf_{SYMBOL}_{tag}_trades.csv instead of the untagged file -- needed for
SOLUSDT specifically, whose CONFIRMED result came from the transfer-mode walk-forward
(multi_crypto_transfer_walkforward.py), not the own-mode one that produced the untagged file
(that own-mode file is a separate, REJECTED, degenerate-sample result -- must not be confused
with the transfer-mode one just because the symbol name matches).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
BTC_ETH_PATH = os.path.join(DOCS, "walk_forward_v3_trades_export.csv")
COLUMNS = ["symbol", "fold", "entry_time", "exit_time", "raw_return", "stop_distance",
           "leverage_safe", "was_stopped", "close_path"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="comma-separated NEW symbols to add to BTC+ETH")
    parser.add_argument("--out", default=os.path.join(DOCS, "multi_crypto_portfolio_trades.csv"))
    args = parser.parse_args()
    new_symbols = args.symbols.split(",")

    parts = [pd.read_csv(BTC_ETH_PATH, parse_dates=["entry_time", "exit_time"])[COLUMNS]]
    print(f"BTCUSDT+ETHUSDT: {len(parts[0])} trades from {BTC_ETH_PATH}")
    for entry in new_symbols:
        s, _, tag = entry.partition(":")
        fname = f"multi_crypto_wf_{s}_{tag}_trades.csv" if tag else f"multi_crypto_wf_{s}_trades.csv"
        path = os.path.join(DOCS, fname)
        if not os.path.exists(path):
            print(f"WARNING: no walk-forward export for {entry} at {path} -- skipping")
            continue
        df = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])[COLUMNS]
        df["symbol"] = s  # normalize (transfer-mode export already uses target symbol name)
        print(f"{entry}: {len(df)} trades from {path}")
        parts.append(df)

    combined = pd.concat(parts, ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    combined.to_csv(args.out, index=False)
    print(f"\nCombined portfolio: {len(combined)} trades -> {args.out}")
    print(combined["symbol"].value_counts().to_string())


if __name__ == "__main__":
    main()
