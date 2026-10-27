"""Produce a reproducible, trade-level OLD-vs-FIXED impact audit.

This reads only the frozen pre-HOLDOUT exports and the isolated fixed
reconstruction.  It does not alter either input set.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant_bot.config import SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio
from scripts.compare_forward_impact import REFERENCES


SIGNAL_KEY = ["symbol", "fold", "entry_time"]
FIELDS = ["exit_time", "raw_return", "stop_distance", "leverage_safe", "was_stopped", "close_path"]


def load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["entry_time"] = pd.to_datetime(frame["entry_time"], utc=True)
    frame["exit_time"] = pd.to_datetime(frame["exit_time"], utc=True)
    return frame


def portfolio(frames: list[pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    limits = RiskLimits(0.015, 0.135, 3.0, 30.0, True, 0.01)
    costs = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
    log, _, metrics = simulate_portfolio(pd.concat(frames, ignore_index=True), limits, costs)
    gross_profit = float(log.loc[log.pnl > 0, "pnl"].sum())
    gross_loss = float(-log.loc[log.pnl < 0, "pnl"].sum())
    fee = float((log.notional * (2 * TAKER_FEE_PCT)).sum())
    slippage = float((log.notional * SLIPPAGE_PCT_EST).sum())
    summary = {
        "signals": int(sum(map(len, frames))), "executed_trades": int(len(log)),
        "rejected_signals": int(metrics["rejected_signals"]),
        "starting_capital": 100000.0, "ending_capital": float(metrics["ending_equity"]),
        "total_pnl": float(log.pnl.sum()), "total_return_pct": float(metrics["total_return_pct"]),
        "cagr_pct": float(metrics["cagr_pct"]), "max_dd_pct": float(metrics["max_dd_pct"]),
        "calmar": float(metrics["calmar"]),
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "win_rate_pct": float((log.pnl > 0).mean() * 100),
        "fees": fee, "slippage": slippage, "funding": 0.0,
        "funding_treatment": "not modeled by the adopted historical portfolio engine",
    }
    return log, summary


def symbol_stats(log: pd.DataFrame) -> list[dict]:
    rows = []
    for symbol, group in log.groupby("symbol", sort=True):
        wins = group.loc[group.pnl > 0, "pnl"].sum()
        losses = -group.loc[group.pnl < 0, "pnl"].sum()
        rows.append({
            "symbol": symbol, "executed_trades": int(len(group)),
            "pnl": float(group.pnl.sum()), "profit_factor": float(wins / losses) if losses else None,
            "win_rate_pct": float((group.pnl > 0).mean() * 100),
            "fees": float((group.notional * (2 * TAKER_FEE_PCT)).sum()),
            "slippage": float((group.notional * SLIPPAGE_PCT_EST).sum()), "funding": 0.0,
        })
    return rows


def changed_mask(left: pd.Series, right: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
        return pd.Series(~np.isclose(left.to_numpy(float), right.to_numpy(float),
                                     rtol=1e-10, atol=1e-12, equal_nan=True), index=left.index)
    return left.fillna("<NA>").astype(str) != right.fillna("<NA>").astype(str)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repro-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    old_frames, fixed_frames, detail_rows, comparisons = [], [], [], []
    for tag, old_path in REFERENCES.items():
        old, fixed = load(old_path), load(args.repro_dir / f"{tag}_trades.csv")
        old_frames.append(old)
        fixed_frames.append(fixed)
        merged = old.merge(fixed, on=SIGNAL_KEY, how="outer", suffixes=("_old", "_fixed"), indicator=True)
        added = merged._merge.eq("right_only")
        removed = merged._merge.eq("left_only")
        common = merged._merge.eq("both")
        field_counts = {}
        any_changed = pd.Series(False, index=merged.index)
        for field in FIELDS:
            mask = pd.Series(False, index=merged.index)
            mask.loc[common] = changed_mask(merged.loc[common, f"{field}_old"], merged.loc[common, f"{field}_fixed"])
            merged[f"changed_{field}"] = mask
            field_counts[field] = int(mask.sum())
            any_changed |= mask
        merged["difference_type"] = np.select(
            [added, removed, common & any_changed], ["ADDED", "REMOVED", "MODIFIED"], default="UNCHANGED")
        divergent = merged[merged.difference_type.ne("UNCHANGED")].copy()
        divergent.insert(0, "tag", tag)
        detail_rows.append(divergent)
        comparisons.append({
            "tag": tag, "symbol_counts_old": old.symbol.value_counts().sort_index().to_dict(),
            "symbol_counts_fixed": fixed.symbol.value_counts().sort_index().to_dict(),
            "signals_old": int(len(old)), "signals_fixed": int(len(fixed)),
            "added_entries": int(added.sum()), "removed_entries": int(removed.sum()),
            "common_entries": int(common.sum()), "modified_common_entries": int((common & any_changed).sum()),
            "field_changes_on_common_entries": field_counts,
        })

    old_log, old_summary = portfolio(old_frames)
    fixed_log, fixed_summary = portfolio(fixed_frames)
    old_symbols = pd.DataFrame(symbol_stats(old_log)).set_index("symbol")
    fixed_symbols = pd.DataFrame(symbol_stats(fixed_log)).set_index("symbol")
    symbol_comparison = old_symbols.add_suffix("_old").join(fixed_symbols.add_suffix("_fixed"), how="outer")
    for name in old_symbols.columns:
        symbol_comparison[f"{name}_delta"] = symbol_comparison[f"{name}_fixed"] - symbol_comparison[f"{name}_old"]
    symbol_comparison.reset_index().to_csv(args.out_dir / "forward_impact_by_symbol.csv", index=False)
    pd.concat(detail_rows, ignore_index=True).to_csv(args.out_dir / "forward_impact_trade_differences.csv", index=False)
    old_log.to_csv(args.out_dir / "forward_impact_old_executed.csv", index=False)
    fixed_log.to_csv(args.out_dir / "forward_impact_fixed_executed.csv", index=False)
    report = {
        "scope": "pre-HOLDOUT only", "old": old_summary, "fixed": fixed_summary,
        "delta_fixed_minus_old": {key: fixed_summary[key] - old_summary[key]
                                  for key in old_summary if isinstance(old_summary[key], (int, float))},
        "trade_population_comparison": comparisons,
        "material": True,
        "cause": ("The corrected label builder excludes the final 10 unavailable future targets "
                  "from every expanding TRAIN slice instead of fitting them as class 0. This changes "
                  "each affected deterministic random forest, its probabilities and selected TRAIN "
                  "population; the latter also changes fold stop percentiles/leverage. Changed entries "
                  "and exits then alter portfolio-cap acceptance and compounding. The horizon remains "
                  "10 and its 50-bar exit path is unchanged, so the horizon plumbing fix contributes zero."),
    }
    (args.out_dir / "forward_impact_detailed.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
