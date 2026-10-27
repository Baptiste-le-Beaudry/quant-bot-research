"""Execution margin and cross-asset clustering audit for a portfolio export."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quant_bot.config import SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.backtest.execution_simulator import ExecutionScenario, return_metrics, simulate_execution


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "multi_crypto_portfolio_trades.csv"


def metrics(trades, scenario):
    return return_metrics(simulate_execution(trades, scenario))


def break_even_slippage(trades):
    low, high = SLIPPAGE_PCT_EST / 2, 0.02
    base = metrics(trades, ExecutionScenario(fee_per_side=TAKER_FEE_PCT, slippage_per_side=low))
    high_pf = metrics(trades, ExecutionScenario(fee_per_side=TAKER_FEE_PCT, slippage_per_side=high))["profit_factor"]
    if high_pf > 1:
        return base, None
    for _ in range(30):
        mid = (low + high) / 2
        if metrics(trades, ExecutionScenario(fee_per_side=TAKER_FEE_PCT, slippage_per_side=mid))["profit_factor"] > 1:
            low = mid
        else:
            high = mid
    return base, high * 10_000


def break_even_latency(trades):
    last_survived = 0
    for minutes in range(0, 16):
        result = metrics(trades, ExecutionScenario(fee_per_side=TAKER_FEE_PCT,
                                                   slippage_per_side=SLIPPAGE_PCT_EST / 2,
                                                   latency_seconds=minutes * 60))
        if result.get("profit_factor", 0) < 1 or result.get("expectancy", -1) < 0:
            return minutes, last_survived
        last_survived = minutes
    return None, last_survived


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--prefix", default="validation_execution")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    trades = pd.read_csv(args.data, parse_dates=["entry_time", "exit_time"])
    symbols = list(dict.fromkeys(trades["symbol"].astype(str)))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for symbol in symbols:
        subset = trades[trades.symbol == symbol].copy()
        base, slip_bps = break_even_slippage(subset)
        latency_break, worst_latency = break_even_latency(subset)
        stress = metrics(subset, ExecutionScenario(fee_per_side=TAKER_FEE_PCT,
                                                    slippage_per_side=SLIPPAGE_PCT_EST * 1.5,
                                                    latency_seconds=60, stop_slippage_fraction=0.0025))
        rows.append({"symbol": symbol, "n": len(subset), "base_pf": base["profit_factor"],
                     "base_expectancy_pct": base["expectancy"] * 100,
                     "break_even_slippage_bps_per_side": slip_bps,
                     "break_even_latency_minutes": latency_break,
                     "worst_latency_survived_minutes": worst_latency,
                     "combined_stress_pf": stress.get("profit_factor"),
                     "execution_margin_bps_per_side": None if slip_bps is None else slip_bps - SLIPPAGE_PCT_EST / 2 * 10_000})
    pd.DataFrame(rows).to_csv(args.out_dir / f"{args.prefix}_break_even.csv", index=False)

    base_exec = simulate_execution(trades, ExecutionScenario(fee_per_side=TAKER_FEE_PCT,
                                                              slippage_per_side=SLIPPAGE_PCT_EST / 2))
    merged = trades.reset_index(drop=True).reset_index(names="sequence").merge(base_exec, on=["sequence", "symbol"])
    merged["weighted_pnl"] = merged.net_return * merged.leverage_safe
    daily = merged.pivot_table(index=merged.entry_time.dt.floor("D"), columns="symbol", values="weighted_pnl", aggfunc="sum").fillna(0)
    daily.reindex(columns=symbols).corr().to_csv(args.out_dir / f"{args.prefix}_trade_pnl_correlation.csv")

    losing = merged[merged.net_return < 0].sort_values("entry_time")
    cluster_rows = []
    for row in losing.itertuples():
        overlap = losing[(losing.entry_time < row.exit_time) & (losing.exit_time > row.entry_time)]
        cluster_rows.append({"entry_time": row.entry_time, "symbol": row.symbol,
                             "simultaneous_losing_positions": int(len(overlap)),
                             "cluster_symbols": ",".join(sorted(overlap.symbol.unique()))})
    pd.DataFrame(cluster_rows).to_csv(args.out_dir / f"{args.prefix}_losing_clusters.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"max simultaneous losing positions={max((r['simultaneous_losing_positions'] for r in cluster_rows), default=0)}")


if __name__ == "__main__":
    main()
