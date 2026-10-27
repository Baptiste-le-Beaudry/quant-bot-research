"""Canonical backtest-versus-paper decision log schema."""
from __future__ import annotations

import uuid

import pandas as pd


COLUMNS = [
    "signal_id", "signal_status", "symbol", "timestamp_signal", "side", "probability", "risk_profile",
    "expected_entry", "observed_market_price", "expected_notional", "actual_simulated_notional",
    "expected_stop", "signal_generation_latency_ms", "order_submission_latency_ms", "fill_latency_ms",
    "spread_bps", "slippage_bps", "fees", "funding", "expected_exit", "simulated_exit",
    "expected_pnl", "paper_pnl", "expected_exit_reason", "exit_reason",
    "exit_mismatch", "stop_mismatch", "execution_drag", "edge_retention",
    "data_resolution", "subminute_validated",
]


def normalize_execution_log(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "signal_id" not in out:
        out["signal_id"] = [str(uuid.uuid4()) for _ in range(len(out))]
    for column in COLUMNS:
        if column not in out:
            out[column] = pd.NA
    out["data_resolution"] = out["data_resolution"].fillna("1m")
    out["subminute_validated"] = out["subminute_validated"].fillna(False).astype(bool)
    return out[COLUMNS]


def execution_summary(frame: pd.DataFrame) -> pd.DataFrame:
    data = normalize_execution_log(frame)
    rows = []
    for profile, group in data.groupby("risk_profile", dropna=False):
        matched = group[group.signal_status == "MATCHED"].copy()
        expected = pd.to_numeric(matched.expected_pnl, errors="coerce").dropna()
        paper = pd.to_numeric(matched.paper_pnl, errors="coerce").dropna()

        def pf(values):
            wins, losses = values[values > 0], values[values < 0]
            return float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")

        rows.append({
            "risk_profile": profile, "signals": int(group.signal_id.nunique()),
            "matched_signals": int(len(matched)), "missed_signals": int((group.signal_status != "MATCHED").sum()),
            "missed_signal_rate": float((group.signal_status != "MATCHED").mean()),
            "expected_pf_matched": pf(expected), "paper_pf_matched": pf(paper),
            "pf_degradation": pf(paper) - pf(expected),
            "expected_average_trade": float(expected.mean()), "paper_average_trade": float(paper.mean()),
            "average_trade_degradation": float(paper.mean() - expected.mean()),
            "expected_pnl": float(expected.sum()), "paper_pnl": float(paper.sum()),
            "execution_drag": float(pd.to_numeric(matched.execution_drag, errors="coerce").sum()),
            "edge_retention": float(pd.to_numeric(matched.edge_retention, errors="coerce").mean()),
            "exit_mismatches": int(matched.exit_mismatch.fillna(False).astype(bool).sum()),
            "stop_mismatches": int(matched.stop_mismatch.fillna(False).astype(bool).sum()),
            "avg_slippage_bps": float(pd.to_numeric(matched.slippage_bps, errors="coerce").mean()),
            "avg_fill_latency_ms": float(pd.to_numeric(matched.fill_latency_ms, errors="coerce").mean()),
        })
    return pd.DataFrame(rows)
