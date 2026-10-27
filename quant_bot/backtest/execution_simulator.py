"""Parametric execution stress on registered one-minute trade paths."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


class UnsupportedResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ExecutionScenario:
    fee_per_side: float = 0.0005
    slippage_per_side: float = 0.0001
    spread_bps_round_trip: float = 0.0
    latency_seconds: int = 0
    partial_fill_ratio: float = 1.0
    rejection_probability: float = 0.0
    stop_slippage_fraction: float = 0.0
    volatility_slippage_multiplier: float = 0.0
    seed: int = 42

    def __post_init__(self):
        if self.latency_seconds < 0 or self.latency_seconds % 60 != 0:
            raise UnsupportedResolutionError("one-minute paths support latency only in whole-minute increments")
        if not 0 <= self.partial_fill_ratio <= 1:
            raise ValueError("partial_fill_ratio must be in [0,1]")
        if not 0 <= self.rejection_probability <= 1:
            raise ValueError("rejection_probability must be in [0,1]")


def parse_path(value) -> np.ndarray:
    if isinstance(value, str):
        return np.asarray([float(part) for part in value.split(";")], dtype=float)
    return np.asarray(value, dtype=float)


def resolve_path_details(path, protective_stop: float, scenario: ExecutionScenario,
                         activate_at: float = 0.0063, trail_distance: float = 0.0080) -> dict:
    returns = parse_path(path)
    delay = scenario.latency_seconds // 60
    if delay >= len(returns) - 1:
        return {"net_return": None, "exit_reason": "latency_missed", "exit_offset_minutes": None}
    if delay:
        delayed_entry = returns[delay]
        returns = (1 + returns[delay:]) / (1 + delayed_entry) - 1
    peak, activated = -np.inf, False
    raw, reason, local_offset = float(returns[-1]), "time", len(returns) - 1
    for offset, value in enumerate(returns):
        if value <= -protective_stop:
            raw, reason, local_offset = -protective_stop - scenario.stop_slippage_fraction, "stop", offset
            break
        peak = max(peak, value)
        activated = activated or peak >= activate_at
        if activated and value <= peak - trail_distance:
            raw, reason, local_offset = peak - trail_distance - scenario.stop_slippage_fraction, "trailing", offset
            break
    realized_vol = float(np.std(np.diff(returns))) if len(returns) > 2 else 0.0
    slip = 2 * scenario.slippage_per_side * (1 + scenario.volatility_slippage_multiplier * realized_vol)
    costs = 2 * scenario.fee_per_side + slip + scenario.spread_bps_round_trip / 10_000
    return {"net_return": raw - costs, "exit_reason": reason,
            "exit_offset_minutes": delay + local_offset,
            "fee_fraction": 2 * scenario.fee_per_side,
            "slippage_fraction": slip,
            "spread_fraction": scenario.spread_bps_round_trip / 10_000}


def resolve_path(path, protective_stop: float, scenario: ExecutionScenario,
                 activate_at: float = 0.0063, trail_distance: float = 0.0080) -> tuple[float | None, str]:
    details = resolve_path_details(path, protective_stop, scenario, activate_at, trail_distance)
    return details["net_return"], details["exit_reason"]


def simulate_execution(trades: pd.DataFrame, scenario: ExecutionScenario) -> pd.DataFrame:
    rng = np.random.default_rng(scenario.seed)
    rows = []
    for sequence, trade in trades.reset_index(drop=True).iterrows():
        if rng.random() < scenario.rejection_probability:
            rows.append({"sequence": sequence, "symbol": trade.symbol, "status": "REJECTED",
                         "net_return": np.nan, "fill_ratio": 0.0, "simulated_exit": pd.NaT,
                         "exit_reason": "order_rejected"})
            continue
        details = resolve_path_details(trade.close_path, float(trade.stop_distance), scenario)
        if details["net_return"] is None:
            rows.append({"sequence": sequence, "symbol": trade.symbol, "status": "MISSED",
                         "net_return": np.nan, "fill_ratio": 0.0, "simulated_exit": pd.NaT,
                         "exit_reason": "latency_missed"})
            continue
        entry_time = pd.to_datetime(trade.entry_time, utc=True) if "entry_time" in trades.columns else pd.NaT
        rows.append({"sequence": sequence, "symbol": trade.symbol, "status": "FILLED",
                     **details, "fill_ratio": scenario.partial_fill_ratio,
                     "simulated_exit": entry_time + pd.Timedelta(minutes=details["exit_offset_minutes"]),
                     "fill_latency_ms": scenario.latency_seconds * 1000,
                     "slippage_bps": details["slippage_fraction"] * 10_000,
                     "spread_bps": scenario.spread_bps_round_trip})
    return pd.DataFrame(rows)


def return_metrics(executions: pd.DataFrame) -> dict:
    filled = executions[executions.status == "FILLED"]
    values = filled.net_return.to_numpy(float)
    if not len(values):
        return {"n": 0}
    wins, losses = values[values > 0], values[values <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n": int(len(values)), "profit_factor": pf, "expectancy": float(values.mean()),
            "win_rate": float((values > 0).mean()), "fill_rate": float(len(filled) / len(executions))}
