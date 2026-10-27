"""Reproducible validation tables for the post-label-fix Strategy A candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant_bot.backtest.execution_simulator import ExecutionScenario, simulate_execution
from quant_bot.config import SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio


TAGS = ("BTCETH", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
        "LINKUSDT", "LTCUSDT", "SOLUSDT_TRANSFER")
NORMAL = RiskLimits(0.015, 0.135, 3.0, 30.0, True, 0.01)
BASE_COSTS = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)


def load_candidate(source: Path) -> pd.DataFrame:
    frames = [pd.read_csv(source / f"{tag}_trades.csv") for tag in TAGS]
    out = pd.concat(frames, ignore_index=True)
    out["entry_time"] = pd.to_datetime(out.entry_time, utc=True)
    out["exit_time"] = pd.to_datetime(out.exit_time, utc=True)
    return out.sort_values(["entry_time", "exit_time", "symbol", "fold"]).reset_index(drop=True)


def extra_metrics(log: pd.DataFrame, metrics: dict) -> dict:
    wins, losses = log.loc[log.pnl > 0, "pnl"].sum(), -log.loc[log.pnl < 0, "pnl"].sum()
    return {**metrics, "profit_factor": float(wins / losses) if losses else None,
            "win_rate_pct": float((log.pnl > 0).mean() * 100),
            "total_pnl": float(log.pnl.sum()),
            "fees": float((log.notional * 2 * TAKER_FEE_PCT).sum()),
            "slippage": float((log.notional * SLIPPAGE_PCT_EST).sum()), "funding": 0.0}


def annual(log: pd.DataFrame, coverage_start: pd.Timestamp, coverage_end: pd.Timestamp) -> pd.DataFrame:
    rows, capital = [], 100_000.0
    for year in range(coverage_start.year, coverage_end.year + 1):
        start = max(coverage_start, pd.Timestamp(f"{year}-01-01", tz="UTC"))
        end = min(coverage_end, pd.Timestamp(f"{year}-12-31 23:59:59.999999999", tz="UTC"))
        group = log[(log.exit_time >= start) & (log.exit_time <= end)].copy()
        begin = capital
        pnl = float(group.pnl.sum())
        capital += pnl
        path = np.concatenate([[begin], begin + group.sort_values(["exit_time", "sequence"]).pnl.cumsum().to_numpy(float)])
        peaks = np.maximum.accumulate(path)
        max_dd = float(((path - peaks) / peaks).min() * 100)
        gp, gl = group.loc[group.pnl > 0, "pnl"].sum(), -group.loc[group.pnl < 0, "pnl"].sum()
        contributors = group.groupby("symbol").pnl.sum().sort_values()
        days = (end - start).total_seconds() / 86400
        ret = (capital / begin - 1) * 100
        partial = start > pd.Timestamp(f"{year}-01-01", tz="UTC") or end < pd.Timestamp(f"{year}-12-31 23:59:59", tz="UTC")
        annualized = ((capital / begin) ** (365.25 / days) - 1) * 100 if partial and days > 0 and capital > 0 else None
        rows.append({"year": year, "status": "PARTIAL YEAR" if partial else "FULL YEAR",
                     "coverage_start": start, "coverage_end": end, "days": days,
                     "starting_capital": begin, "ending_capital": capital,
                     "return_pct": ret, "annualized_return_pct_informational": annualized,
                     "executed_trades": int(len(group)), "net_pnl": pnl, "max_dd_pct": max_dd,
                     "profit_factor": float(gp / gl) if gl else None,
                     "win_rate_pct": float((group.pnl > 0).mean() * 100) if len(group) else None,
                     "fees": float((group.notional * 2 * TAKER_FEE_PCT).sum()),
                     "slippage": float((group.notional * SLIPPAGE_PCT_EST).sum()), "funding": 0.0,
                     "best_symbol": contributors.index[-1] if len(contributors) else None,
                     "best_symbol_pnl": float(contributors.iloc[-1]) if len(contributors) else None,
                     "worst_symbol": contributors.index[0] if len(contributors) else None,
                     "worst_symbol_pnl": float(contributors.iloc[0]) if len(contributors) else None})
    return pd.DataFrame(rows)


def stress_portfolio(trades: pd.DataFrame, name: str, scenario: ExecutionScenario) -> dict:
    executions = simulate_execution(trades, scenario)
    filled = executions[executions.status.eq("FILLED")].copy()
    stressed = trades.reset_index(names="sequence").merge(
        filled[["sequence", "net_return", "simulated_exit", "fill_ratio"]], on="sequence", how="inner")
    stressed["entry_time"] = stressed.entry_time + pd.Timedelta(seconds=scenario.latency_seconds)
    stressed["exit_time"] = pd.to_datetime(stressed.simulated_exit, utc=True)
    stressed["raw_return"] = stressed.net_return
    log, _, metrics = simulate_portfolio(stressed, NORMAL, ExecutionCosts(0.0, 0.0))
    gp, gl = log.loc[log.pnl > 0, "pnl"].sum(), -log.loc[log.pnl < 0, "pnl"].sum()
    return {"scenario": name, "signals": len(trades), "filled_paths": len(filled),
            "executed_trades": len(log), "cagr_pct": metrics["cagr_pct"],
            "max_dd_pct": metrics["max_dd_pct"], "calmar": metrics["calmar"],
            "profit_factor": float(gp / gl) if gl else None,
            "win_rate_pct": float((log.pnl > 0).mean() * 100),
            "ending_equity": metrics["ending_equity"], "total_pnl": float(log.pnl.sum()),
            "rejected_signals": metrics["rejected_signals"] + len(trades) - len(filled)}


def longest_streak(signs: list[bool], wanted: bool) -> int:
    best = current = 0
    for value in signs:
        current = current + 1 if value == wanted else 0
        best = max(best, current)
    return best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    trades = load_candidate(args.source)
    trades.to_csv(args.out_dir / "fixed_candidate_trades.csv", index=False)
    log, _, metrics = simulate_portfolio(trades, NORMAL, BASE_COSTS)
    log.to_csv(args.out_dir / "fixed_normal_executed.csv", index=False)
    normal = extra_metrics(log, metrics)
    (args.out_dir / "fixed_normal_metrics.json").write_text(json.dumps(normal, indent=2), encoding="utf-8")

    coverage_start, coverage_end = trades.entry_time.min(), trades.exit_time.max()
    yearly = annual(log, coverage_start, coverage_end)
    yearly.to_csv(args.out_dir / "fixed_normal_calendar_years.csv", index=False)
    year_symbol = log.assign(year=log.exit_time.dt.year).groupby(["year", "symbol"], as_index=False).agg(
        executed_trades=("pnl", "size"), pnl=("pnl", "sum"),
        wins=("pnl", lambda x: int((x > 0).sum())),
        fees=("notional", lambda x: float(x.sum() * 2 * TAKER_FEE_PCT)),
        slippage=("notional", lambda x: float(x.sum() * SLIPPAGE_PCT_EST)))
    year_symbol["pnl_share_of_year_pct"] = year_symbol.pnl / year_symbol.groupby("year").pnl.transform("sum") * 100
    year_symbol.to_csv(args.out_dir / "fixed_normal_year_symbol_contribution.csv", index=False)
    full = yearly[yearly.status.eq("FULL YEAR")]
    pnl_ranked = yearly.sort_values("net_pnl", ascending=False)
    returns = full.return_pct.to_numpy(float)
    total_pnl = float(yearly.net_pnl.sum())
    temporal = {
        "coverage_start": str(coverage_start), "coverage_end": str(coverage_end),
        "best_year_by_return": int(yearly.loc[yearly.return_pct.idxmax(), "year"]),
        "worst_year_by_return": int(yearly.loc[yearly.return_pct.idxmin(), "year"]),
        "positive_years": int((yearly.return_pct > 0).sum()), "negative_years": int((yearly.return_pct < 0).sum()),
        "full_year_arithmetic_mean_return_pct": float(returns.mean()),
        "full_year_median_return_pct": float(np.median(returns)),
        "full_year_return_volatility_pct": float(returns.std(ddof=1)),
        "whole_period_cagr_pct": metrics["cagr_pct"],
        "worst_calendar_return_pct": float(yearly.return_pct.min()),
        "longest_positive_streak_all_covered_years": longest_streak((yearly.return_pct > 0).tolist(), True),
        "longest_negative_streak_all_covered_years": longest_streak((yearly.return_pct > 0).tolist(), False),
        "best_year_pnl_share_pct": float(pnl_ranked.iloc[0].net_pnl / total_pnl * 100),
        "top_two_year_pnl_share_pct": float(pnl_ranked.iloc[:2].net_pnl.sum() / total_pnl * 100),
        "total_pnl_without_best_year": float(total_pnl - pnl_ranked.iloc[0].net_pnl),
        "profitable_without_best_year": bool(total_pnl - pnl_ranked.iloc[0].net_pnl > 0),
        "cagr_without_best_year": None,
        "cagr_without_best_year_note": "Not methodologically valid: removing a calendar year breaks the observed compounding chronology.",
    }
    (args.out_dir / "fixed_temporal_summary.json").write_text(json.dumps(temporal, indent=2), encoding="utf-8")

    sym = log.groupby("symbol").agg(executed_trades=("pnl", "size"), pnl=("pnl", "sum"),
                                     gross_profit=("pnl", lambda x: x[x > 0].sum()),
                                     gross_loss=("pnl", lambda x: -x[x < 0].sum()),
                                     win_rate_pct=("pnl", lambda x: (x > 0).mean() * 100),
                                     notional=("notional", "sum")).reset_index()
    sym["profit_factor"] = sym.gross_profit / sym.gross_loss
    sym["pnl_share_pct"] = sym.pnl / sym.pnl.sum() * 100
    sym["fees"] = sym.notional * 2 * TAKER_FEE_PCT
    sym["slippage"] = sym.notional * SLIPPAGE_PCT_EST
    sym.to_csv(args.out_dir / "fixed_normal_symbol_concentration.csv", index=False)
    concentration = {"top_symbol": sym.loc[sym.pnl.idxmax(), "symbol"],
                     "top_symbol_pnl_share_pct": float(sym.pnl.max() / sym.pnl.sum() * 100),
                     "top_two_symbol_pnl_share_pct": float(sym.nlargest(2, "pnl").pnl.sum() / sym.pnl.sum() * 100),
                     "positive_pnl_hhi": float(((sym.pnl.clip(lower=0) / sym.pnl.clip(lower=0).sum()) ** 2).sum())}
    (args.out_dir / "fixed_symbol_concentration.json").write_text(json.dumps(concentration, indent=2), encoding="utf-8")

    scenarios = [
        ("BASE_PATH_REPLAY", ExecutionScenario(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)),
        ("SLIPPAGE_2X", ExecutionScenario(TAKER_FEE_PCT, SLIPPAGE_PCT_EST)),
        ("SLIPPAGE_3X", ExecutionScenario(TAKER_FEE_PCT, SLIPPAGE_PCT_EST * 1.5)),
        ("LATENCY_1M", ExecutionScenario(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2, latency_seconds=60)),
        ("LATENCY_2M", ExecutionScenario(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2, latency_seconds=120)),
        ("COMBINED_3X_1M_STOPGAP25BP", ExecutionScenario(TAKER_FEE_PCT, SLIPPAGE_PCT_EST * 1.5,
                                                         latency_seconds=60, stop_slippage_fraction=0.0025)),
    ]
    pd.DataFrame([stress_portfolio(trades, name, scenario) for name, scenario in scenarios]).to_csv(
        args.out_dir / "fixed_normal_execution_stress.csv", index=False)
    print(json.dumps({"normal": normal, "temporal": temporal, "concentration": concentration}, indent=2))


if __name__ == "__main__":
    main()
