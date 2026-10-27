"""Replay one pre-HOLDOUT signal stream through all research profiles."""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quant_bot.backtest.execution_simulator import ExecutionScenario
from quant_bot.config import SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.live.paper import comparison_log, replay_profiles
from quant_bot.monitoring.execution_log import execution_summary

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--risk-profile", choices=["normal", "aggressive", "max-risk", "all"], default="all")
    parser.add_argument("--data", type=Path, default=ROOT / "docs" / "multi_crypto_portfolio_trades.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "validation_paper_replay.csv")
    parser.add_argument("--summary-out", type=Path,
                        default=ROOT / "docs" / "validation_paper_replay_summary.csv")
    args = parser.parse_args()
    trades = pd.read_csv(args.data, parse_dates=["entry_time", "exit_time"])
    names = ("normal", "aggressive", "max-risk") if args.risk_profile == "all" else (args.risk_profile,)
    paper, summaries = replay_profiles(trades, ExecutionScenario(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2), names)
    comparison = comparison_log(trades, paper)
    comparison.to_csv(args.out, index=False)
    execution_summary(comparison).to_csv(args.summary_out, index=False)
    print(pd.DataFrame(summaries).T.to_string())
    print(f"comparison log -> {args.out}")
    print(f"comparison summary -> {args.summary_out}")


if __name__ == "__main__":
    main()
