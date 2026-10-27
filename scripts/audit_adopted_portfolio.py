"""Independent audit of the currently adopted Experiment 33 portfolio.

This script does not fit a model, optimize a parameter, or read market data.
It audits only the registered pre-HOLDOUT walk-forward trade exports. It first
reproduces the historical risk-sweep calculation, then independently rebuilds
an exit-time-ordered equity curve with registered fees and slippage.

Usage:
    python scripts/audit_adopted_portfolio.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quant_bot.config import ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
import scripts.walk_forward_risk_sweep as registered


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PORTFOLIO = DOCS / "multi_crypto_portfolio_trades.csv"
BTC_ETH = DOCS / "walk_forward_v3_trades_export.csv"
NEW_SYMBOLS = ["BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT"]
ADOPTED_SYMBOLS = ["BTCUSDT", "ETHUSDT", *NEW_SYMBOLS]
RISK_PCT = 0.03
INITIAL_EQUITY = 100_000.0
EXPECTED = {"n": 1262, "cagr_pct": 125.0, "max_dd_pct": -22.72, "profit_factor": 1.778, "calmar": 5.501}
HOLDOUT_START = {
    "BTCUSDT": "2025-03-28", "ETHUSDT": "2025-04-13",
    "XRPUSDT": "2025-04-23", "LTCUSDT": "2025-04-24",
    "LINKUSDT": "2025-04-25", "ADAUSDT": "2025-04-28",
    "BNBUSDT": "2025-04-30", "DOGEUSDT": "2025-05-30",
}
DYNAMIC_LEVERAGE_NUMERATOR = 0.75 * 0.5
LEVERAGE_CAP = 30.0
MAX_EXIT_MINUTES = 50


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["entry_time", "exit_time"])


def component_paths() -> list[Path]:
    return [BTC_ETH, *(DOCS / f"multi_crypto_wf_{symbol}_trades.csv" for symbol in NEW_SYMBOLS)]


def metrics_from_exit_equity(events: pd.DataFrame) -> dict:
    equity = np.concatenate([[INITIAL_EQUITY], events["equity_after_exit"].to_numpy(float)])
    running_max = np.maximum.accumulate(equity)
    drawdown = (equity - running_max) / running_max
    pnls = events["pnl"].to_numpy(float)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else math.inf
    years = max((events["exit_time"].iloc[-1] - events["entry_time"].min()).total_seconds() / (365.25 * 86400), 1 / 365.25)
    cagr = ((equity[-1] / INITIAL_EQUITY) ** (1 / years) - 1) * 100
    max_dd = float(drawdown.min() * 100)
    return {
        "n_trades": int(len(events)),
        "ending_equity": float(equity[-1]),
        "total_return_pct": float((equity[-1] / INITIAL_EQUITY - 1) * 100),
        "cagr_pct": float(cagr),
        "max_dd_pct": max_dd,
        "profit_factor": pf,
        "calmar": float(cagr / abs(max_dd)) if max_dd else math.inf,
    }


def chronological_simulation(trades: pd.DataFrame, include_costs: bool) -> tuple[pd.DataFrame, dict]:
    """Size at entry using only realized equity; realize P&L at exit time.

    Open trades retain the notional fixed when they entered. At equal timestamps,
    exits are processed before entries so released capital is observable.
    """
    ordered = trades.sort_values(["entry_time", "exit_time", "symbol", "fold"]).reset_index(drop=True)
    equity = INITIAL_EQUITY
    pending_exits: list[dict] = []
    completed: list[dict] = []
    cost = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST if include_costs else 0.0

    def realize_until(timestamp: pd.Timestamp) -> None:
        nonlocal equity, pending_exits
        due = sorted((p for p in pending_exits if p["exit_time"] <= timestamp), key=lambda p: (p["exit_time"], p["seq"]))
        pending_exits = [p for p in pending_exits if p["exit_time"] > timestamp]
        for position in due:
            equity += position["pnl"]
            position["equity_after_exit"] = equity
            completed.append(position)

    for seq, trade in ordered.iterrows():
        realize_until(trade["entry_time"])
        stop_distance = float(trade["stop_distance"])
        safe_leverage = float(trade["leverage_safe"])
        requested_leverage = RISK_PCT / stop_distance
        leverage = min(requested_leverage, safe_leverage)
        notional = equity * leverage
        pnl = notional * (float(trade["raw_return"]) - cost)
        pending_exits.append({
            "seq": int(seq), "symbol": trade["symbol"], "fold": int(trade["fold"]),
            "entry_time": trade["entry_time"], "exit_time": trade["exit_time"],
            "entry_equity": equity, "notional": notional, "leverage_used": leverage, "pnl": pnl,
        })

    realize_until(pd.Timestamp.max.tz_localize("UTC"))
    events = pd.DataFrame(completed).sort_values(["exit_time", "seq"]).reset_index(drop=True)
    return events, metrics_from_exit_equity(events)


def concurrency_stats(trades: pd.DataFrame) -> dict:
    events = []
    for row in trades.itertuples():
        events.append((row.entry_time, 1, row.symbol))
        events.append((row.exit_time, -1, row.symbol))
    # exits (-1) before entries (+1) at an identical timestamp
    events.sort(key=lambda item: (item[0], item[1]))
    active = Counter()
    max_positions = 0
    max_same_symbol = 0
    overlapping_entries = 0
    for _, delta, symbol in events:
        if delta > 0:
            if sum(active.values()) > 0:
                overlapping_entries += 1
            active[symbol] += 1
            max_positions = max(max_positions, sum(active.values()))
            max_same_symbol = max(max_same_symbol, active[symbol])
        else:
            active[symbol] -= 1
    return {
        "entries_while_other_positions_open": overlapping_entries,
        "max_simultaneous_positions": max_positions,
        "max_simultaneous_same_symbol": max_same_symbol,
    }


def enforce_one_position_per_symbol(trades: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Keep the first chronological signal while its symbol has no open trade."""
    kept_parts = []
    removed = Counter()
    for symbol, symbol_trades in trades.groupby("symbol", sort=False):
        available_at = None
        kept_indices = []
        ordered = symbol_trades.sort_values(["entry_time", "exit_time", "fold"])
        for index, trade in ordered.iterrows():
            if available_at is not None and trade["entry_time"] < available_at:
                removed[symbol] += 1
                continue
            kept_indices.append(index)
            available_at = trade["exit_time"]
        kept_parts.append(trades.loc[kept_indices])
    kept = pd.concat(kept_parts, ignore_index=True).sort_values(["entry_time", "exit_time", "symbol"]).reset_index(drop=True)
    return kept, {"removed_total": int(sum(removed.values())), "removed_by_symbol": dict(sorted(removed.items()))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", type=Path, help="optional task-specific JSON report")
    args = parser.parse_args()

    missing = [str(path) for path in [PORTFOLIO, *component_paths()] if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing registered inputs: {missing}")

    trades = load(PORTFOLIO)
    components = pd.concat([load(path) for path in component_paths()], ignore_index=True)
    columns = ["symbol", "fold", "entry_time", "exit_time", "raw_return", "stop_distance", "leverage_safe", "was_stopped", "close_path"]
    canonical_portfolio = trades[columns].sort_values(columns[:4]).reset_index(drop=True)
    canonical_components = components[columns].sort_values(columns[:4]).reset_index(drop=True)

    exact_duplicate_mask = trades.duplicated(subset=columns, keep=False)
    identity_columns = ["symbol", "fold", "entry_time", "exit_time"]
    identity_duplicate_mask = trades.duplicated(subset=identity_columns, keep=False)
    durations = (trades["exit_time"] - trades["entry_time"]).dt.total_seconds() / 60
    expected_leverage = np.minimum(DYNAMIC_LEVERAGE_NUMERATOR / trades["stop_distance"], LEVERAGE_CAP)
    leverage_error = np.abs(expected_leverage - trades["leverage_safe"])
    holdout_violations = {}
    for symbol, boundary in HOLDOUT_START.items():
        symbol_rows = trades[trades["symbol"] == symbol]
        boundary_ts = pd.Timestamp(boundary, tz="UTC")
        holdout_violations[symbol] = int((symbol_rows["exit_time"] >= boundary_ts).sum())

    registered.DATA_PATH = str(PORTFOLIO)
    registered_log, registered_curve = registered.simulate_compounding(trades.sort_values("entry_time"), RISK_PCT)
    registered_metrics = registered.compute_metrics(registered_log, registered_curve)
    gross_events, gross_metrics = chronological_simulation(trades, include_costs=False)
    net_events, net_metrics = chronological_simulation(trades, include_costs=True)
    sequential_trades, sequential_removals = enforce_one_position_per_symbol(trades)
    sequential_net_events, sequential_net_metrics = chronological_simulation(sequential_trades, include_costs=True)
    registered_times = [timestamp for timestamp, _ in registered_curve]

    report = {
        "audit_id": "C-AUDIT-001",
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in [PORTFOLIO, *component_paths()]},
        "registered_expected": EXPECTED,
        "portfolio": {
            "rows": int(len(trades)),
            "symbols": trades["symbol"].value_counts().sort_index().to_dict(),
            "component_rebuild_exact_match": bool(canonical_portfolio.equals(canonical_components)),
            "exact_duplicate_rows": int(exact_duplicate_mask.sum()),
            "duplicate_trade_identities": int(identity_duplicate_mask.sum()),
            "negative_duration_rows": int((durations < 0).sum()),
            "duration_over_50min_rows": int((durations > MAX_EXIT_MINUTES).sum()),
            "max_duration_minutes": float(durations.max()),
            "max_dynamic_leverage_abs_error": float(leverage_error.max()),
            "holdout_boundary_violations": holdout_violations,
            **concurrency_stats(trades),
        },
        "registered_algorithm": {
            **registered_metrics,
            "non_monotonic_equity_timestamps": int(sum(b < a for a, b in zip(registered_times, registered_times[1:]))),
            "uses_raw_return_without_registered_costs": True,
        },
        "chronological_gross": gross_metrics,
        "chronological_net_registered_costs": {
            **net_metrics,
            "round_trip_cost_fraction": float(ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST),
        },
        "chronological_net_one_position_per_symbol": {
            **sequential_net_metrics,
            **sequential_removals,
            "round_trip_cost_fraction": float(ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST),
        },
    }

    audit_failures = []
    if report["registered_algorithm"]["non_monotonic_equity_timestamps"]:
        audit_failures.append("registered equity curve is not chronological")
    if report["registered_algorithm"]["uses_raw_return_without_registered_costs"]:
        audit_failures.append("registered risk sweep omits fees and slippage from raw_return")
    if report["portfolio"]["max_simultaneous_same_symbol"] > 1:
        audit_failures.append("exported trailing trades overlap within the same symbol")
    report["audit_verdict"] = "FAIL" if audit_failures else "PASS"
    report["audit_failures"] = audit_failures

    print(json.dumps(report, indent=2, default=str, sort_keys=True))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")

    hard_failures = [
        len(trades) != EXPECTED["n"],
        set(trades["symbol"]) != set(ADOPTED_SYMBOLS),
        not canonical_portfolio.equals(canonical_components),
        exact_duplicate_mask.any(), identity_duplicate_mask.any(),
        (durations < 0).any(), (durations > MAX_EXIT_MINUTES).any(),
        leverage_error.max() > 1e-9,
        any(holdout_violations.values()),
        bool(audit_failures),
    ]
    return 1 if any(hard_failures) else 0


if __name__ == "__main__":
    raise SystemExit(main())
