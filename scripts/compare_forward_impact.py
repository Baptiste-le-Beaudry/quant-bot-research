"""Compare post-fix fold reconstruction to frozen pre-fix exports.

This is an operational impact audit only. It never reads HOLDOUT data and
never writes to any historical export.
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


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REFERENCES = {
    "BTCETH": DOCS / "walk_forward_v3_trades_export.csv",
    "BNBUSDT": DOCS / "multi_crypto_wf_BNBUSDT_trades.csv",
    "XRPUSDT": DOCS / "multi_crypto_wf_XRPUSDT_stop80_trades.csv",
    "DOGEUSDT": DOCS / "multi_crypto_wf_DOGEUSDT_trades.csv",
    "ADAUSDT": DOCS / "multi_crypto_wf_ADAUSDT_trades.csv",
    "LINKUSDT": DOCS / "multi_crypto_wf_LINKUSDT_stop95_trades.csv",
    "LTCUSDT": DOCS / "multi_crypto_wf_LTCUSDT_trades.csv",
    "SOLUSDT_TRANSFER": DOCS / "multi_crypto_wf_SOLUSDT_transfer_trades.csv",
}
KEYS = ["symbol", "fold", "entry_time", "exit_time"]


def compare_one(tag: str, actual_path: Path) -> dict:
    reference = pd.read_csv(REFERENCES[tag]).sort_values(KEYS).reset_index(drop=True)
    actual = pd.read_csv(actual_path).sort_values(KEYS).reset_index(drop=True)
    row = {"tag": tag, "old_trades": len(reference), "fixed_trades": len(actual)}
    if len(reference) != len(actual):
        row.update(status="DIVERGED", timestamp_matches=False,
                   mismatch_reason="trade_count")
        return row
    row["timestamp_matches"] = bool(reference[KEYS].equals(actual[KEYS]))
    mismatches = {}
    for column in reference.columns.intersection(actual.columns):
        left, right = reference[column], actual[column]
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            bad = ~np.isclose(left.to_numpy(float), right.to_numpy(float),
                              rtol=1e-10, atol=1e-12, equal_nan=True)
        else:
            bad = (left.fillna("<NA>").astype(str).to_numpy()
                   != right.fillna("<NA>").astype(str).to_numpy())
        if bad.any():
            mismatches[column] = int(bad.sum())
    row["field_mismatches"] = mismatches
    row["status"] = "MATCH" if not mismatches else "DIVERGED"
    return row


def portfolio_metrics(trades: pd.DataFrame) -> dict:
    limits = RiskLimits(risk_pct=0.015, max_portfolio_open_risk=0.135,
                        max_gross_exposure=3.0, hard_leverage_ceiling=30.0,
                        one_position_per_symbol=True, min_equity_fraction=0.01)
    costs = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
    log, _, metrics = simulate_portfolio(trades, limits, costs)
    pnl = log["pnl"]
    gross_profit, gross_loss = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return {
        "trade_count": int(len(trades)),
        "executed_count": int(len(log)),
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else None,
        "total_return_pct": float(metrics["total_return_pct"]),
        "cagr_pct": float(metrics["cagr_pct"]),
        "max_dd_pct": float(metrics["max_dd_pct"]),
        "calmar": float(metrics["calmar"]),
        "forced_liquidations": int(metrics["forced_liquidations"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repro-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    comparisons, fixed_frames, old_frames = [], [], []
    for tag, reference in REFERENCES.items():
        actual = args.repro_dir / f"{tag}_trades.csv"
        if not actual.exists():
            comparisons.append({"tag": tag, "status": "MISSING"})
            continue
        comparisons.append(compare_one(tag, actual))
        fixed_frames.append(pd.read_csv(actual))
        old_frames.append(pd.read_csv(reference))
    complete = len(fixed_frames) == len(REFERENCES)
    report = {"complete": complete, "comparisons": comparisons}
    if complete:
        report["old_portfolio"] = portfolio_metrics(pd.concat(old_frames, ignore_index=True))
        report["fixed_portfolio"] = portfolio_metrics(pd.concat(fixed_frames, ignore_index=True))
        report["conclusion"] = ("NO MATERIAL IMPACT" if all(
            row["status"] == "MATCH" for row in comparisons) else "DIVERGENCE")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
