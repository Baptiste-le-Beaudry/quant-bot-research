"""Chronological shared-capital engine for frozen A-Equity OOS candidates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PortfolioLimits:
    risk_pct: float
    open_risk_cap: float
    gross_cap: float
    initial_equity: float = 100_000.0
    round_trip_cost: float = 0.0002

    def __post_init__(self):
        if not (0 < self.risk_pct < 1 and 0 < self.open_risk_cap < 1):
            raise ValueError("risk_pct and open_risk_cap must be fractions in (0,1)")
        if self.gross_cap <= 0 or self.initial_equity <= 0 or self.round_trip_cost < 0:
            raise ValueError("caps/equity/cost invalid")


REQUIRED = {"symbol", "fold", "entry_time", "exit_time", "raw_return",
            "exec_return", "stop_distance", "entry_price"}


def validate_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"missing candidate columns: {sorted(missing)}")
    out = frame.copy()
    out["entry_time"] = pd.to_datetime(out.entry_time, utc=True)
    out["exit_time"] = pd.to_datetime(out.exit_time, utc=True)
    if out[list(REQUIRED)].isna().any().any():
        raise ValueError("NaN in required candidate columns")
    if (out.exit_time < out.entry_time).any():
        raise ValueError("exit before entry")
    if (out.stop_distance <= 0).any() or (out.entry_price <= 0).any():
        raise ValueError("non-positive stop distance or entry price")
    if not np.allclose(out.raw_return - out.exec_return, 0.0002, atol=1e-10):
        raise ValueError("candidate executable cost is not exactly 0.0002")
    identity = ["symbol", "fold", "entry_time", "exit_time"]
    if out.duplicated(identity).any():
        raise ValueError("duplicate candidate identity")
    return out.sort_values(["entry_time", "symbol", "fold", "exit_time"], kind="mergesort").reset_index(drop=True)


def simulate(candidates: pd.DataFrame, limits: PortfolioLimits,
             price_at: Callable[[str, pd.Timestamp], float]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Simulate one long-only account. Equal-time exits precede entries."""
    ordered = validate_candidates(candidates)
    cash = float(limits.initial_equity)
    positions: dict[str, dict] = {}
    ledger, rejections, states = [], [], []
    entry_cost_fraction = exit_cost_fraction = limits.round_trip_cost / 2

    def mark(ts: pd.Timestamp) -> tuple[float, float, float]:
        market = 0.0
        for pos in positions.values():
            pos["mark_price"] = float(price_at(pos["symbol"], ts))
            market += pos["shares"] * pos["mark_price"]
        equity = cash + market
        gross = market / equity if equity > 0 else np.inf
        open_risk = sum(p["risk_dollars"] for p in positions.values()) / equity if equity > 0 else np.inf
        return equity, gross, open_risk

    def snapshot(ts: pd.Timestamp, phase: str):
        equity, gross, open_risk = mark(ts)
        market = equity - cash
        states.append({"timestamp": ts, "phase": phase, "cash": cash,
                       "market_value": market, "equity": equity,
                       "net_exposure": gross, "gross_exposure": gross,
                       "open_risk": open_risk,
                       "available_buying_power": max(0.0, equity * limits.gross_cap - market),
                       "open_positions": len(positions)})
        return equity, gross, open_risk

    rows = list(ordered.itertuples(index=False))
    cursor = 0
    while cursor < len(rows):
        ts = rows[cursor].entry_time
        end = cursor + 1
        while end < len(rows) and rows[end].entry_time == ts:
            end += 1
        incoming = rows[cursor:end]
        due = sorted((p for p in positions.values() if p["exit_time"] <= ts),
                     key=lambda p: (p["exit_time"], p["symbol"], p["fold"]))
        for pos in due:
            exit_notional = pos["notional"] * (1 + pos["raw_return"])
            exit_cost = pos["notional"] * exit_cost_fraction
            cash += exit_notional - exit_cost
            pnl = pos["notional"] * (pos["raw_return"] - limits.round_trip_cost)
            pos.update({"exit_cost": exit_cost, "total_cost": pos["entry_cost"] + exit_cost,
                        "pnl": pnl, "net_return": pos["raw_return"] - limits.round_trip_cost})
            ledger.append(pos)
            del positions[pos["symbol"]]
        equity, gross, open_risk = snapshot(ts, "post_exit")
        for trade in incoming:
            reason = None
            if trade.symbol in positions:
                reason = "SAME_SYMBOL_OPEN"
            risk_dollars = equity * limits.risk_pct
            notional = risk_dollars / float(trade.stop_distance)
            current_market = sum(p["shares"] * p["mark_price"] for p in positions.values())
            current_risk = sum(p["risk_dollars"] for p in positions.values())
            if reason is None and current_risk + risk_dollars > equity * limits.open_risk_cap + 1e-8:
                reason = "OPEN_RISK_CAP"
            if reason is None and current_market + notional > equity * limits.gross_cap + 1e-8:
                reason = "GROSS_EXPOSURE_CAP"
            if reason:
                rejections.append({"symbol": trade.symbol, "fold": int(trade.fold),
                                   "entry_time": ts, "reason": reason,
                                   "equity": equity, "desired_notional": notional})
                continue
            entry_cost = notional * entry_cost_fraction
            shares = notional / float(trade.entry_price)
            cash -= notional + entry_cost
            positions[trade.symbol] = {
                "symbol": trade.symbol, "fold": int(trade.fold), "entry_time": ts,
                "exit_time": trade.exit_time, "entry_equity": equity,
                "entry_price": float(trade.entry_price), "mark_price": float(trade.entry_price),
                "shares": shares, "notional": notional, "risk_dollars": risk_dollars,
                "stop_distance": float(trade.stop_distance), "raw_return": float(trade.raw_return),
                "entry_cost": entry_cost,
            }
        snapshot(ts, "post_entry")
        cursor = end

    for pos in sorted(positions.values(), key=lambda p: (p["exit_time"], p["symbol"], p["fold"])):
        ts = pos["exit_time"]
        exit_notional = pos["notional"] * (1 + pos["raw_return"])
        exit_cost = pos["notional"] * exit_cost_fraction
        cash += exit_notional - exit_cost
        pnl = pos["notional"] * (pos["raw_return"] - limits.round_trip_cost)
        pos.update({"exit_cost": exit_cost, "total_cost": pos["entry_cost"] + exit_cost,
                    "pnl": pnl, "net_return": pos["raw_return"] - limits.round_trip_cost})
        ledger.append(pos)
        positions.pop(pos["symbol"], None)
        snapshot(ts, "post_exit")
    return pd.DataFrame(ledger), pd.DataFrame(states), pd.DataFrame(rejections)
