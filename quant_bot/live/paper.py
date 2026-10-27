"""Multi-profile paper replay using the shared portfolio risk engine."""
import pandas as pd

from quant_bot.backtest.execution_simulator import ExecutionScenario, simulate_execution
from quant_bot.config import RISK_PROFILES
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio
from quant_bot.monitoring.execution_log import normalize_execution_log


def risk_limits(profile_name: str) -> RiskLimits:
    profile = RISK_PROFILES[profile_name]
    return RiskLimits(profile["risk_pct"], profile["max_portfolio_open_risk"],
                      profile["max_gross_exposure"], profile["hard_leverage_ceiling"], True)


def replay_profiles(trades: pd.DataFrame, scenario: ExecutionScenario,
                    profile_names=("normal", "aggressive", "max-risk")):
    """Send one immutable signal stream to multiple virtual risk accounts."""
    executions = simulate_execution(trades, scenario)
    source = trades.reset_index(drop=True).reset_index(names="sequence")
    executable = source.merge(executions, on=["sequence", "symbol"])
    executable = executable[executable.status == "FILLED"].copy()
    executable["backtest_expected_return"] = executable["raw_return"]
    executable["backtest_expected_exit"] = executable["exit_time"]
    executable["exit_time"] = pd.to_datetime(executable["simulated_exit"], utc=True)
    executable["raw_return"] = executable["net_return"]  # execution drag already applied
    logs, summaries = [], {}
    for name in profile_names:
        log, _, metrics = simulate_portfolio(executable, risk_limits(name), ExecutionCosts(0.0, 0.0))
        log["risk_profile"] = name
        logs.append(log)
        summaries[name] = metrics
    combined = pd.concat(logs, ignore_index=True)
    combined.attrs["profile_names"] = tuple(profile_names)
    return combined, summaries


def comparison_log(trades: pd.DataFrame, paper_log: pd.DataFrame) -> pd.DataFrame:
    expected = trades.copy()
    keys = ["symbol", "fold", "entry_time"]
    profiles = paper_log.attrs.get("profile_names", tuple(paper_log.get("risk_profile", pd.Series(dtype=str)).dropna().unique()))
    if paper_log.empty:
        empty = {key: expected[key].iloc[:0] for key in keys}
        empty["exit_time"] = expected["exit_time"].iloc[:0]
        for column in ("raw_return", "notional", "requested_notional", "pnl", "risk_dollar", "net_return"):
            empty[column] = pd.Series(dtype=float)
        empty["risk_profile"] = pd.Series(dtype=str)
        paper_log = pd.DataFrame(empty)
    expected_lookup = expected[keys + ["exit_time", "raw_return", "was_stopped"]].rename(
        columns={"exit_time": "expected_exit_time", "raw_return": "raw_return_expected"})
    merged = paper_log.merge(expected_lookup, on=keys, how="left")
    if merged.empty:
        mapped = normalize_execution_log(pd.DataFrame()).iloc[:0]
    else:
        merged["signal_id"] = merged.apply(lambda r: f"{r.symbol}:{r.fold}:{r.entry_time.isoformat()}", axis=1)
        merged["expected_pnl"] = merged.notional * merged.raw_return_expected
        merged["paper_pnl"] = merged.pnl
        merged["execution_drag"] = merged.paper_pnl - merged.expected_pnl
        expected_stopped = merged.was_stopped.astype(str).str.lower().eq("true")
        merged["expected_exit_reason"] = expected_stopped.map({True: "stop", False: "non_stop"})
        merged["exit_mismatch"] = merged.expected_exit_time != merged.exit_time
        merged["stop_mismatch"] = expected_stopped != (merged.exit_reason == "stop")
        grouped = merged.groupby("risk_profile").agg(expected=("raw_return_expected", "mean"), observed=("net_return", "mean"))
        merged["edge_retention"] = merged.risk_profile.map((grouped.observed / grouped.expected).to_dict())
        mapped = pd.DataFrame({
            "signal_id": merged.signal_id, "signal_status": "MATCHED", "symbol": merged.symbol, "timestamp_signal": merged.entry_time,
            "side": "LONG", "probability": pd.NA, "risk_profile": merged.risk_profile,
            "expected_entry": pd.NA, "observed_market_price": pd.NA,
            "expected_notional": merged.requested_notional, "actual_simulated_notional": merged.notional,
            "expected_stop": merged.risk_dollar / merged.notional,
            "signal_generation_latency_ms": pd.NA, "order_submission_latency_ms": pd.NA,
            "fill_latency_ms": merged.get("fill_latency_ms", pd.NA),
            "spread_bps": merged.get("spread_bps", 0.0), "slippage_bps": merged.get("slippage_bps", pd.NA),
            "fees": merged.notional * merged.get("fee_fraction", 0.0), "funding": 0.0,
            "expected_exit": merged.expected_exit_time,
            "simulated_exit": merged.exit_time, "expected_pnl": merged.expected_pnl,
            "paper_pnl": merged.paper_pnl, "expected_exit_reason": merged.expected_exit_reason,
            "exit_reason": merged.get("exit_reason", pd.NA), "exit_mismatch": merged.exit_mismatch,
            "stop_mismatch": merged.stop_mismatch,
            "execution_drag": merged.execution_drag, "edge_retention": merged.edge_retention,
            "data_resolution": "1m", "subminute_validated": False,
        })
    # Preserve the complete immutable signal stream for every virtual account.
    # Signals absent from a profile's funded log were rejected by execution or
    # portfolio constraints; retaining them makes missed-trade rates explicit.
    missing_rows = []
    expected_ids = expected.apply(lambda r: f"{r.symbol}:{r.fold}:{r.entry_time.isoformat()}", axis=1)
    for profile in profiles:
        seen = set(mapped.loc[mapped.risk_profile == profile, "signal_id"])
        for signal_id, (_, row) in zip(expected_ids, expected.iterrows()):
            if signal_id not in seen:
                missing_rows.append({
                    "signal_id": signal_id, "signal_status": "NOT_EXECUTED", "symbol": row.symbol,
                    "timestamp_signal": row.entry_time, "side": "LONG", "risk_profile": profile,
                    "expected_exit": row.exit_time, "paper_pnl": 0.0,
                    "exit_reason": "execution_or_portfolio_rejection", "data_resolution": "1m",
                    "subminute_validated": False,
                })
    if missing_rows:
        mapped = pd.concat([mapped, pd.DataFrame(missing_rows)], ignore_index=True)
    return normalize_execution_log(mapped).sort_values(["risk_profile", "timestamp_signal", "symbol"]).reset_index(drop=True)
