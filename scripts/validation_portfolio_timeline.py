"""Build the minute-level shared-account exposure timeline, pre-HOLDOUT only."""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quant_bot.config import RISK_PROFILES, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.risk import ExecutionCosts, RiskLimits, build_minute_exposure_timeline, simulate_portfolio


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--risk-profile", choices=sorted(RISK_PROFILES), default="normal")
    parser.add_argument("--data", type=Path, default=ROOT / "docs" / "multi_crypto_portfolio_trades.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "validation_portfolio_timeline.csv")
    args = parser.parse_args()

    trades = pd.read_csv(args.data, parse_dates=["entry_time", "exit_time"])
    profile = RISK_PROFILES[args.risk_profile]
    limits = RiskLimits(
        risk_pct=profile["risk_pct"],
        max_portfolio_open_risk=profile["max_portfolio_open_risk"],
        max_gross_exposure=profile["max_gross_exposure"],
        hard_leverage_ceiling=profile["hard_leverage_ceiling"],
    )
    costs = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
    log, _, metrics = simulate_portfolio(trades, limits, costs)
    timeline = build_minute_exposure_timeline(log, trades, hard_leverage_ceiling=limits.hard_leverage_ceiling)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    timeline.to_csv(args.out, index=False)
    summary = {
        "profile": args.risk_profile,
        "minutes": len(timeline),
        "minimum_mtm_equity": float(timeline.equity_mtm.min()),
        "minimum_available_margin": float(timeline.available_margin.min()),
        "peak_gross_exposure_mtm": float(timeline.gross_exposure.max()),
        "peak_open_risk_mtm": float(timeline.open_risk_fraction.max()),
        "max_open_positions": int(timeline.open_positions.max()),
        "max_simultaneous_losing_positions": int(timeline.losing_positions.max()),
        **metrics,
    }
    print(pd.Series(summary).to_string())
    print(f"timeline -> {args.out}")


if __name__ == "__main__":
    main()
