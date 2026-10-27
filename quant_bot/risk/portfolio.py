"""Shared event-driven portfolio risk engine for research, paper, and live."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskLimits:
    risk_pct: float
    max_portfolio_open_risk: float | None = None
    max_gross_exposure: float | None = None
    hard_leverage_ceiling: float = 30.0
    one_position_per_symbol: bool = True
    min_equity_fraction: float = 0.25

    def __post_init__(self) -> None:
        if not 0 < self.risk_pct < 1:
            raise ValueError("risk_pct must be between 0 and 1")
        for name in ("max_portfolio_open_risk", "max_gross_exposure"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.hard_leverage_ceiling <= 0:
            raise ValueError("hard_leverage_ceiling must be positive")
        if not 0 < self.min_equity_fraction < 1:
            raise ValueError("min_equity_fraction must be between 0 and 1")


@dataclass(frozen=True)
class ExecutionCosts:
    fee_per_side: float
    slippage_per_side: float
    fixed_slippage_bps_per_side: float = 0.0
    stop_slippage_fraction: float = 0.0

    @property
    def round_trip_fraction(self) -> float:
        return 2 * (self.fee_per_side + self.slippage_per_side + self.fixed_slippage_bps_per_side / 10_000)


REQUIRED_COLUMNS = {"symbol", "fold", "entry_time", "exit_time", "raw_return", "stop_distance", "leverage_safe", "was_stopped"}


def validate_trade_frame(trades: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(trades.columns)
    if missing:
        raise ValueError(f"missing trade columns: {sorted(missing)}")
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True)
    out["exit_time"] = pd.to_datetime(out["exit_time"], utc=True)
    if out[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("trade frame contains NaN in required columns")
    if (out["exit_time"] < out["entry_time"]).any():
        raise ValueError("trade exits before entry")
    if (out["stop_distance"] <= 0).any() or (out["leverage_safe"] <= 0).any():
        raise ValueError("stop_distance and leverage_safe must be positive")
    if "fill_ratio" in out and (~out["fill_ratio"].between(0, 1) | out["fill_ratio"].isna()).any():
        raise ValueError("fill_ratio must be in [0,1]")
    if out.duplicated(["symbol", "fold", "entry_time", "exit_time"]).any():
        raise ValueError("duplicate trade identity")
    return out.sort_values(["entry_time", "exit_time", "symbol", "fold"]).reset_index(drop=True)


def _metrics(log: pd.DataFrame, curve: pd.DataFrame, initial: float, rejected: int) -> dict:
    if log.empty:
        return {"n_trades": 0, "rejected_signals": rejected}
    values = np.concatenate([[initial], curve["equity"].to_numpy(float)])
    peaks = np.maximum.accumulate(values)
    dd = (values - peaks) / peaks
    pnls = log["pnl"].to_numpy(float)
    fractions = pnls / log["entry_equity"].to_numpy(float)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    years = max((log["exit_time"].max() - log["entry_time"].min()).total_seconds() / (365.25 * 86400), 1 / 365.25)
    cagr = ((values[-1] / initial) ** (1 / years) - 1) * 100 if values[-1] > 0 else -100.0
    max_dd = float(dd.min() * 100)
    downside = fractions[fractions < 0]
    std = fractions.std(ddof=1) if len(fractions) > 1 else 0.0
    down_std = downside.std(ddof=1) if len(downside) > 1 else 0.0
    streak = current = 0
    for loss in pnls <= 0:
        current = current + 1 if loss else 0
        streak = max(streak, current)
    trough = int(np.argmin(dd))
    recovery_days = None
    if 0 < trough < len(values) - 1:
        recovered = np.flatnonzero(values[trough + 1:] >= peaks[trough])
        if len(recovered):
            trough_time = curve.iloc[trough - 1]["timestamp"]
            recovery_time = curve.iloc[trough + int(recovered[0])]["timestamp"]
            recovery_days = float((recovery_time - trough_time).total_seconds() / 86400)
    return {
        "n_trades": int(len(log)), "ending_equity": float(values[-1]),
        "total_return_pct": float((values[-1] / initial - 1) * 100), "cagr_pct": float(cagr),
        "max_dd_pct": max_dd, "calmar": float(cagr / abs(max_dd)) if max_dd else float("inf"),
        "profit_factor": pf, "sharpe_like": float(fractions.mean() / std) if std else 0.0,
        "sortino_like": float(fractions.mean() / down_std) if down_std else 0.0,
        "worst_trade_pct": float(fractions.min() * 100), "worst_losing_streak": int(streak),
        "minimum_equity": float(values.min()), "recovery_days": recovery_days,
        "forced_liquidations": int(log["forced_liquidation"].sum()),
        "average_leverage": float(log["position_leverage"].mean()), "peak_leverage": float(log["position_leverage"].max()),
        "average_gross_exposure": float(log["gross_exposure_after_entry"].mean()),
        "peak_gross_exposure": float(log["gross_exposure_after_entry"].max()),
        "average_open_risk": float(log["open_risk_after_entry"].mean()),
        "peak_open_risk": float(log["open_risk_after_entry"].max()),
        "max_simultaneous_positions": int(log["open_positions_after_entry"].max()),
        "rejected_signals": int(rejected),
    }


def simulate_portfolio(trades: pd.DataFrame, limits: RiskLimits, costs: ExecutionCosts,
                       initial_equity: float = 100_000.0) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Realize exits before equal-time entries and share one account equity."""
    ordered = validate_trade_frame(trades)
    equity = float(initial_equity)
    open_positions, completed, curve_rows = [], [], []
    rejected, halted = 0, False

    def realize(timestamp: pd.Timestamp) -> None:
        nonlocal equity, open_positions, halted
        due = sorted((p for p in open_positions if p["exit_time"] <= timestamp), key=lambda p: (p["exit_time"], p["sequence"]))
        open_positions = [p for p in open_positions if p["exit_time"] > timestamp]
        for position in due:
            equity += position["pnl"]
            position["equity_after_exit"] = equity
            completed.append(position)
            curve_rows.append({"timestamp": position["exit_time"], "equity": equity})
        halted = halted or equity <= initial_equity * limits.min_equity_fraction

    for sequence, trade in ordered.iterrows():
        realize(trade["entry_time"])
        if halted or (limits.one_position_per_symbol and any(p["symbol"] == trade["symbol"] for p in open_positions)):
            rejected += 1
            continue
        open_risk = sum(p["risk_dollar"] for p in open_positions)
        gross = sum(p["notional"] for p in open_positions)
        desired_risk = equity * limits.risk_pct
        if limits.max_portfolio_open_risk is not None:
            desired_risk = min(desired_risk, max(0.0, equity * limits.max_portfolio_open_risk - open_risk))
        leverage = min(desired_risk / (equity * float(trade["stop_distance"])), float(trade["leverage_safe"]), limits.hard_leverage_ceiling)
        if limits.max_gross_exposure is not None:
            leverage = min(leverage, max(0.0, equity * limits.max_gross_exposure - gross) / equity)
        requested_leverage = leverage
        fill_ratio = float(trade.get("fill_ratio", 1.0))
        leverage *= fill_ratio
        if leverage <= 0:
            rejected += 1
            continue
        notional = equity * leverage
        risk_dollar = notional * float(trade["stop_distance"])
        cost = costs.round_trip_fraction + (costs.stop_slippage_fraction if bool(trade["was_stopped"]) else 0.0)
        pnl = notional * (float(trade["raw_return"]) - cost)
        liquidation_move = 0.5 / leverage
        position = {
            "sequence": int(sequence), "symbol": trade["symbol"], "fold": int(trade["fold"]),
            "entry_time": trade["entry_time"], "exit_time": trade["exit_time"], "entry_equity": equity,
            "requested_notional": equity * requested_leverage, "notional": notional,
            "fill_ratio": fill_ratio, "risk_dollar": risk_dollar, "position_leverage": leverage,
            "raw_return": float(trade["raw_return"]), "net_return": float(trade["raw_return"]) - cost,
            "pnl": pnl, "forced_liquidation": bool(trade["was_stopped"]) and liquidation_move <= float(trade["stop_distance"]),
            "open_positions_after_entry": len(open_positions) + 1,
            "open_risk_after_entry": (open_risk + risk_dollar) / equity,
            "gross_exposure_after_entry": (gross + notional) / equity,
        }
        for column in ("exit_reason", "fee_fraction", "slippage_fraction", "spread_fraction",
                       "fill_latency_ms", "slippage_bps", "spread_bps", "backtest_expected_exit"):
            if column in trade:
                position[column] = trade[column]
        open_positions.append(position)
    realize(pd.Timestamp.max.tz_localize("UTC"))
    log = pd.DataFrame(completed)
    if not log.empty:
        log = log.sort_values(["exit_time", "sequence"]).reset_index(drop=True)
    curve = pd.DataFrame(curve_rows)
    if not curve.empty:
        curve = curve.sort_values("timestamp").reset_index(drop=True)
    return log, curve, _metrics(log, curve, initial_equity, rejected)


def bootstrap_drawdowns(trade_fractions: Iterable[float], n_simulations: int = 10_000,
                        seed: int = 42, block_size: int = 1) -> dict:
    """IID bootstrap at block_size=1; circular block bootstrap otherwise."""
    x = np.asarray(list(trade_fractions), dtype=float)
    if len(x) < 2:
        return {}
    rng, n = np.random.default_rng(seed), len(x)
    dds, minima = np.empty(n_simulations), np.empty(n_simulations)
    for simulation in range(n_simulations):
        if block_size <= 1:
            sample = rng.choice(x, size=n, replace=True)
        else:
            blocks = []
            while len(blocks) * block_size < n:
                start = int(rng.integers(0, n))
                blocks.append(x[(np.arange(start, start + block_size) % n).astype(int)])
            sample = np.concatenate(blocks)[:n]
        equity = np.concatenate([[1.0], np.cumprod(1 + sample)])
        dds[simulation] = ((equity - np.maximum.accumulate(equity)) / np.maximum.accumulate(equity)).min() * 100
        minima[simulation] = equity.min()
    return {
        "median_max_dd_pct": float(np.median(dds)), "p90_max_dd_pct": float(np.percentile(dds, 10)),
        "p95_max_dd_pct": float(np.percentile(dds, 5)), "p99_max_dd_pct": float(np.percentile(dds, 1)),
        **{f"p_dd_gt_{v}": float((dds < -v).mean()) for v in (20, 30, 40, 50, 70)},
        "p_equity_below_50pct": float((minima < 0.50).mean()), "p_equity_below_25pct": float((minima < 0.25).mean()),
        "risk_of_ruin": float((minima <= 0).mean()), "n_simulations": n_simulations, "seed": seed, "block_size": block_size,
    }


def build_minute_exposure_timeline(trade_log: pd.DataFrame, source_trades: pd.DataFrame,
                                   initial_equity: float = 100_000.0,
                                   hard_leverage_ceiling: float = 30.0) -> pd.DataFrame:
    """Reconstruct minute-level portfolio MTM from registered close paths.

    Equity combines P&L already realized at prior exits with gross unrealized
    path P&L for positions currently open. Required minimum margin uses the
    hard leverage ceiling; it is a research approximation until a legal venue's
    exact cross-margin rules are known.
    """
    if trade_log.empty:
        return pd.DataFrame()
    keys = ["symbol", "fold", "entry_time", "exit_time"]
    source = source_trades.copy()
    source["entry_time"] = pd.to_datetime(source["entry_time"], utc=True)
    source["exit_time"] = pd.to_datetime(source["exit_time"], utc=True)
    joined = trade_log.merge(source[keys + ["close_path"]], on=keys, how="left", validate="one_to_one")
    if joined.close_path.isna().any():
        raise ValueError("missing close_path for accepted trade")

    position_rows = []
    for trade in joined.itertuples():
        path = np.asarray([float(value) for value in str(trade.close_path).split(";")])
        duration = int((trade.exit_time - trade.entry_time).total_seconds() // 60)
        path = path[:duration + 1]
        for offset, raw_mtm in enumerate(path):
            position_rows.append({
                "timestamp": trade.entry_time + pd.Timedelta(minutes=offset),
                "symbol": trade.symbol, "notional": trade.notional,
                "risk_dollar": trade.risk_dollar, "unrealized_pnl": trade.notional * raw_mtm,
                "is_losing": raw_mtm < 0, "is_exit": offset == duration,
            })
    positions = pd.DataFrame(position_rows)

    # At an exit timestamp, final net P&L is realized and that position is no
    # longer open for exposure reporting after the timestamp event.
    exits = trade_log.groupby("exit_time", as_index=False).pnl.sum().sort_values("exit_time")
    all_times = pd.date_range(positions.timestamp.min(), positions.timestamp.max(), freq="min", tz="UTC")
    realized = exits.set_index("exit_time").pnl.reindex(all_times, fill_value=0.0).cumsum()
    open_rows = positions[~positions.is_exit]
    grouped = open_rows.groupby("timestamp").agg(
        gross_notional=("notional", "sum"), open_risk_dollar=("risk_dollar", "sum"),
        unrealized_pnl=("unrealized_pnl", "sum"), open_positions=("symbol", "size"),
        losing_positions=("is_losing", "sum"),
    ).reindex(all_times, fill_value=0.0)
    timeline = grouped.copy()
    timeline.index.name = "timestamp"
    timeline["realized_equity"] = initial_equity + realized.values
    timeline["equity_mtm"] = timeline.realized_equity + timeline.unrealized_pnl
    timeline["gross_exposure"] = timeline.gross_notional / timeline.equity_mtm.replace(0, np.nan)
    timeline["open_risk_fraction"] = timeline.open_risk_dollar / timeline.equity_mtm.replace(0, np.nan)
    timeline["minimum_margin"] = timeline.gross_notional / hard_leverage_ceiling
    timeline["available_margin"] = timeline.equity_mtm - timeline.minimum_margin
    return timeline.reset_index()
