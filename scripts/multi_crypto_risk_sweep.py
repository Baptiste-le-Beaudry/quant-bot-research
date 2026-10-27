"""
scripts/multi_crypto_risk_sweep.py — multi-crypto expansion plan, Etape 13:
re-run Experiment 26/31's full compounding risk-per-trade sweep + Monte
Carlo (scripts/walk_forward_risk_sweep.py, its simulate_compounding /
compute_metrics / monte_carlo_dd / print_sweep_table / eliminate_and_recommend
helpers reused UNCHANGED) on the COMBINED multi-crypto trade population
(BTC+ETH+validated new-symbol survivors), instead of that script's own
hardcoded main() which only knows about BTC/ETH solo/combined. Does NOT
assume the BTC+ETH-only 4.0% risk_pct figure (Experiment 31) still applies
-- the combined population's loss distribution is likely different.

Usage:
    python scripts/multi_crypto_risk_sweep.py --data docs/multi_crypto_portfolio_trades.csv --symbols BTCUSDT,ETHUSDT,SOLUSDT
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

import scripts.walk_forward_risk_sweep as rs

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--symbols", required=True, help="comma-separated, e.g. BTCUSDT,ETHUSDT,SOLUSDT")
    args = parser.parse_args()
    rs.DATA_PATH = args.data
    symbols = args.symbols.split(",")

    all_trades = rs.load_trades()
    print(f"Loaded {len(all_trades)} total walk-forward trades "
          f"({all_trades['symbol'].value_counts().to_dict()})\n")

    labels = [(f"{s} solo", [s]) for s in symbols]
    labels.append((f"PORTFOLIO ({'+'.join(symbols)} combined)", symbols))

    for label, syms in labels:
        trades = rs.load_trades(syms)
        if len(trades) == 0:
            print(f"\n{label}: no trades, skipping")
            continue
        rows, mc_rows = [], {}
        for risk_pct in rs.COARSE_GRID + rs.EXTENDED_GRID:
            trade_log, equity_curve = rs.simulate_compounding(trades, risk_pct)
            m = rs.compute_metrics(trade_log, equity_curve)
            m["risk_pct"] = risk_pct
            rows.append(m)
            if m.get("n_trades", 0) >= 5:
                mc_rows[risk_pct] = rs.monte_carlo_dd(trade_log)
        rs.print_sweep_table(rows, label)
        rs.eliminate_and_recommend(rows, mc_rows)


if __name__ == "__main__":
    main()
