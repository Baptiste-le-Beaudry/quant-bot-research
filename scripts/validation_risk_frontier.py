"""Corrected Experiment 33 risk frontier on the locked pre-HOLDOUT exports."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quant_bot.config import SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.risk import ExecutionCosts, RiskLimits, bootstrap_drawdowns, simulate_portfolio


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "docs" / "multi_crypto_portfolio_trades.csv"
RISK_GRID = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.40]
MATRIX_RISKS = [0.04, 0.06, 0.08, 0.10, 0.12]
MATRIX_CAPS = [0.08, 0.12, 0.16, 0.20, 0.24]


def run_case(trades, risk_pct, portfolio_cap=None, gross_cap=None):
    costs = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
    limits = RiskLimits(risk_pct=risk_pct, max_portfolio_open_risk=portfolio_cap,
                        max_gross_exposure=gross_cap,
                        hard_leverage_ceiling=30.0, one_position_per_symbol=True,
                        min_equity_fraction=0.01)
    log, _, metrics = simulate_portfolio(trades, limits, costs)
    fractions = log["pnl"] / log["entry_equity"]
    iid = bootstrap_drawdowns(fractions, n_simulations=10_000, seed=42, block_size=1)
    block = bootstrap_drawdowns(fractions, n_simulations=10_000, seed=42, block_size=20)
    return log, {"risk_pct": risk_pct, "portfolio_cap": portfolio_cap, **metrics,
                 **{f"iid_{k}": v for k, v in iid.items()}, **{f"block_{k}": v for k, v in block.items()}}


def select_profile_parameters(frontier: pd.DataFrame, matrix: pd.DataFrame) -> dict:
    """Select plateaus through explicit joint return/risk constraints."""
    viable = frontier[(frontier.forced_liquidations == 0) & (frontier.ending_equity > 0)].copy()
    normal = viable[(viable.max_dd_pct >= -25) & (viable.block_p_dd_gt_30 <= 0.05)]
    if normal.empty:
        normal = viable.nlargest(1, "calmar")
    else:
        normal = normal[normal.calmar >= normal.calmar.max() * 0.95].sort_values("risk_pct").tail(1)
    normal_row = normal.iloc[0]

    aggressive = matrix[
        (matrix.risk_pct > float(normal_row.risk_pct))
        & (matrix.max_dd_pct >= -35)
        & (matrix.block_p_dd_gt_50 <= 0.10)
        & (matrix.block_p_equity_below_50pct <= 0.01)
        & (matrix.block_risk_of_ruin == 0)
    ].nlargest(1, "cagr_pct")
    if aggressive.empty:
        raise RuntimeError("no matrix point satisfies AGGRESSIVE constraints")

    extreme = matrix[
        (matrix.ending_equity > 0)
        & (matrix.max_dd_pct >= -70)
        & (matrix.block_p_equity_below_25pct <= 0.01)
        & (matrix.block_risk_of_ruin == 0)
    ].nlargest(1, "cagr_pct")
    if extreme.empty:
        raise RuntimeError("no matrix point satisfies MAX_RISK survival constraints")

    aggressive_row, extreme_row = aggressive.iloc[0], extreme.iloc[0]
    return {
        "normal": (float(normal_row.risk_pct),
                   float(normal_row.risk_pct) * int(normal_row.max_simultaneous_positions),
                   math.ceil(float(normal_row.peak_gross_exposure))),
        "aggressive": (float(aggressive_row.risk_pct), float(aggressive_row.portfolio_cap),
                       math.ceil(float(aggressive_row.peak_gross_exposure))),
        "max-risk": (float(extreme_row.risk_pct), float(extreme_row.portfolio_cap),
                     math.ceil(float(extreme_row.peak_gross_exposure))),
    }


def derive_profiles(trades: pd.DataFrame, frontier: pd.DataFrame, matrix: pd.DataFrame) -> dict:
    records = {}
    for name, (risk, cap, gross_cap) in select_profile_parameters(frontier, matrix).items():
        _, row = run_case(trades, risk, cap, gross_cap)
        records[name] = {
            "name": name, "risk_pct": risk, "portfolio_risk_cap": cap,
            "max_gross_exposure": gross_cap,
            "historical_cagr_pct": float(row["cagr_pct"]),
            "historical_max_dd_pct": float(row["max_dd_pct"]), "calmar": float(row["calmar"]),
            "block_p95_dd_pct": float(row["block_p95_max_dd_pct"]),
            "block_p_dd_gt_50": float(row["block_p_dd_gt_50"]),
            "block_p_equity_below_50pct": float(row["block_p_equity_below_50pct"]),
            "block_p_equity_below_25pct": float(row["block_p_equity_below_25pct"]),
            "block_risk_of_ruin": float(row["block_risk_of_ruin"]),
            "research_validated": True, "live_enabled": False,
        }
    records["selection_note"] = (
        "NORMAL: DD<=25%, block P(DD>30)<=5%, within 95% of best eligible Calmar. "
        "AGGRESSIVE: maximum CAGR with DD<=35%, block P(DD>50)<=10%, P(equity<50)<=1%. "
        "MAX_RISK: maximum CAGR with DD<=70%, block P(equity<25)<=1%, zero simulated ruin. "
        "Gross caps are the next integer above observed peak exposure; all profiles remain paper-only."
    )
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs")
    parser.add_argument("--profiles-only", action="store_true",
                        help="regenerate selected-profile metrics from existing frontier/matrix")
    parser.add_argument("--prefix", default="validation_risk")
    parser.add_argument("--risk-grid", default=",".join(map(str, RISK_GRID)))
    parser.add_argument("--matrix-risks", default=",".join(map(str, MATRIX_RISKS)))
    parser.add_argument("--matrix-caps", default=",".join(map(str, MATRIX_CAPS)))
    args = parser.parse_args()
    trades = pd.read_csv(args.data, parse_dates=["entry_time", "exit_time"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    risk_grid = [float(value) for value in args.risk_grid.split(",")]
    matrix_risks = [float(value) for value in args.matrix_risks.split(",")]
    matrix_caps = [float(value) for value in args.matrix_caps.split(",")]
    frontier_path = args.out_dir / f"{args.prefix}_frontier.csv"
    matrix_path = args.out_dir / f"{args.prefix}_cap_matrix.csv"
    profiles_path = args.out_dir / f"{args.prefix}_profiles.json"
    if args.profiles_only:
        frontier = pd.read_csv(frontier_path)
        matrix = pd.read_csv(matrix_path)
        profiles = derive_profiles(trades, frontier, matrix)
        profiles_path.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(profiles, indent=2))
        return

    rows = []
    for risk in risk_grid:
        print(f"frontier risk={risk:.2%}", flush=True)
        _, row = run_case(trades, risk)
        rows.append(row)
    frontier = pd.DataFrame(rows).sort_values("risk_pct")
    frontier["marginal_cagr_per_risk"] = frontier.cagr_pct.diff() / frontier.risk_pct.diff()
    frontier["marginal_dd_per_risk"] = frontier.max_dd_pct.abs().diff() / frontier.risk_pct.diff()
    frontier.to_csv(frontier_path, index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(frontier.max_dd_pct.abs(), frontier.cagr_pct, marker="o")
        for row in frontier.itertuples():
            ax.annotate(f"{row.risk_pct:.0%}", (abs(row.max_dd_pct), row.cagr_pct), fontsize=8)
        ax.set(xlabel="Historical MaxDD (%)", ylabel="CAGR (%)", title="Corrected pre-HOLDOUT risk frontier")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(args.out_dir / f"{args.prefix}_frontier.png", dpi=150)
        plt.close(fig)
    except Exception as exc:
        print(f"matplotlib unavailable: CSV frontier produced without PNG ({exc})")

    matrix_rows = []
    for risk in matrix_risks:
        for cap in matrix_caps:
            print(f"matrix risk={risk:.2%} cap={cap:.2%}", flush=True)
            _, row = run_case(trades, risk, cap)
            matrix_rows.append(row)
    matrix = pd.DataFrame(matrix_rows)
    matrix.to_csv(matrix_path, index=False)

    profiles = derive_profiles(trades, frontier, matrix)
    profiles_path.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")
    print(frontier[["risk_pct", "cagr_pct", "max_dd_pct", "calmar", "block_p95_max_dd_pct", "block_p_dd_gt_50", "block_risk_of_ruin"]].to_string(index=False))
    print(json.dumps(profiles, indent=2))


if __name__ == "__main__":
    main()
