"""Compare FIXED XRP/LINK stop choices against freshly rebuilt controls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant_bot.config import SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.risk import ExecutionCosts, RiskLimits, bootstrap_drawdowns, simulate_portfolio


COSTS = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
RISKS = (0.01, 0.015, 0.02, 0.025, 0.03)


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["entry_time", "exit_time"])


def replace(base: pd.DataFrame, symbol: str, variant: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([base[base.symbol.ne(symbol)], variant], ignore_index=True)


def score(label: str, trades: pd.DataFrame) -> list[dict]:
    rows = []
    for risk in RISKS:
        limits = RiskLimits(risk, 0.135, 3.0, 30.0, True, 0.01)
        log, _, metrics = simulate_portfolio(trades, limits, COSTS)
        fractions = log.pnl / log.entry_equity
        block = bootstrap_drawdowns(fractions, 10_000, 42, 20)
        rows.append({"portfolio": label, "risk_pct": risk, **metrics,
                     "profit_factor": float(log.loc[log.pnl > 0, "pnl"].sum() / -log.loc[log.pnl < 0, "pnl"].sum()),
                     "win_rate_pct": float((log.pnl > 0).mean() * 100),
                     **{f"block_{key}": value for key, value in block.items()}})
    return rows


def solo(label: str, trades: pd.DataFrame) -> dict:
    limits = RiskLimits(0.015, None, None, 30.0, True, 0.01)
    log, _, metrics = simulate_portfolio(trades, limits, COSTS)
    per_fold = log.groupby("fold").apply(
        lambda x: x.loc[x.pnl > 0, "pnl"].sum() / -x.loc[x.pnl < 0, "pnl"].sum()
        if (x.pnl < 0).any() else float("inf"), include_groups=False)
    return {"variant": label, "signals": int(len(trades)), "executed_trades": int(len(log)),
            "profit_factor": metrics["profit_factor"], "win_rate_pct": float((log.pnl > 0).mean() * 100),
            "cagr_pct": metrics["cagr_pct"], "max_dd_pct": metrics["max_dd_pct"],
            "median_fold_pf_finite": float(per_fold[per_fold < float("inf")].median()),
            "folds_pf_above_1_pct": float((per_fold > 1).mean() * 100)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--xrp-p90", type=Path, required=True)
    parser.add_argument("--link-p90", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    base, xrp90, link90 = read(args.base), read(args.xrp_p90), read(args.link_p90)
    xrp80, link95 = base[base.symbol.eq("XRPUSDT")], base[base.symbol.eq("LINKUSDT")]
    portfolios = {"ADOPTED_XRP80_LINK95": base,
                  "CONTROL_XRP90_LINK95": replace(base, "XRPUSDT", xrp90),
                  "CONTROL_XRP80_LINK90": replace(base, "LINKUSDT", link90)}
    grid = pd.DataFrame([row for label, data in portfolios.items() for row in score(label, data)])
    grid.to_csv(args.out_dir / "fixed_stop_variant_portfolio_grid.csv", index=False)
    solos = pd.DataFrame([solo("XRP_P80", xrp80), solo("XRP_P90", xrp90),
                          solo("LINK_P95", link95), solo("LINK_P90", link90)])
    solos.to_csv(args.out_dir / "fixed_stop_variant_symbol_metrics.csv", index=False)
    at_normal = grid[grid.risk_pct.eq(0.015)].set_index("portfolio")
    report = {"normal_risk_comparison": at_normal.to_dict("index"),
              "symbol_comparison": solos.set_index("variant").to_dict("index"),
              "method": "All four stop exports were rebuilt under FIXED; portfolio controls change one symbol only."}
    (args.out_dir / "fixed_stop_variant_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
