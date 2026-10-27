from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .store import ForwardStateStore


def build_profile_report(store: ForwardStateStore) -> pd.DataFrame:
    frames = store.report_frames()
    bars = pd.read_sql_query("SELECT * FROM bars", store.connection)
    events = frames["data_events"]
    common_signals = len(frames["signals"])
    if not bars.empty:
        close_times = pd.to_datetime(bars["close_time"], utc=True)
        receive_times = pd.to_datetime(bars["receive_timestamp"], utc=True)
        days_observed = float((close_times.max() - close_times.min()).total_seconds() / 86400)
        data_latency_ms = float(((receive_times - close_times).dt.total_seconds() * 1000).mean())
    else:
        days_observed, data_latency_ms = 0.0, np.nan
    rows = []
    for account in frames["accounts"].to_dict("records"):
        profile = account["profile"]
        executions = frames["executions"]
        executions = executions[executions["profile"] == profile]
        closed = executions[executions["paper_pnl"].notna()]
        decisions = frames["decisions"]
        decisions = decisions[decisions["profile"] == profile]
        snapshots = frames["snapshots"]
        snapshots = snapshots[snapshots["profile"] == profile]
        pnl = closed["paper_pnl"].astype(float) if not closed.empty else pd.Series(dtype=float)
        expected = closed["expected_pnl"].astype(float) if not closed.empty else pd.Series(dtype=float)
        comparable = closed[closed["expected_exit_reason"].notna()]
        exit_mismatches = int((comparable["exit_reason"] != comparable["expected_exit_reason"]).sum())
        stop_mismatches = int((comparable["paper_stop"].astype(float)
                               != comparable["expected_stop"].astype(float)).sum())
        gross_profit = float(pnl[pnl > 0].sum())
        gross_loss = float(-pnl[pnl < 0].sum())
        wins, losses = pnl[pnl > 0], pnl[pnl < 0]
        exit_reasons = closed["exit_reason"].fillna("") if not closed.empty else pd.Series(dtype=str)
        spreads = pd.to_numeric(executions["spread_bps"], errors="coerce")
        slippage = pd.to_numeric(executions["slippage_bps"], errors="coerce")
        signal_latency = pd.to_numeric(executions["signal_latency_ms"], errors="coerce")
        processing_latency = pd.to_numeric(executions["processing_latency_ms"], errors="coerce")
        rejected = decisions[decisions["status"] == "REJECTED"]
        data_rejected = rejected[rejected["reason"] == "DATA_GUARD_TRIGGERED"]
        portfolio_rejected = rejected[rejected["reason"].isin(
            ["PORTFOLIO_CAP", "POSITION_ALREADY_OPEN", "ACCOUNT_HALTED",
             "KILL_SWITCH_MIN_EQUITY", "KILL_SWITCH_DAILY_LOSS"]
        )]
        external_rejected = rejected[~rejected.index.isin(portfolio_rejected.index)]
        latest = snapshots.sort_values("timestamp").tail(1)
        state = latest.iloc[0].to_dict() if not latest.empty else {}
        rows.append({
            "profile": profile,
            "days_observed": days_observed,
            "signals": len(decisions),
            "trades": len(closed),
            "signal_match_rate": len(decisions) / common_signals if common_signals else 1.0,
            "opened": int((decisions["status"] == "OPENED").sum()),
            "closed": len(closed),
            "open_positions": int(state.get("open_positions", 0)),
            "realized_equity": float(account["realized_equity"]),
            "mtm_equity": float(state.get("mtm_equity", account["realized_equity"])),
            "open_risk": float(state.get("open_risk", 0.0)),
            "gross_exposure": float(state.get("gross_exposure", 0.0)),
            "pf": gross_profit / gross_loss if gross_loss else (np.inf if gross_profit else np.nan),
            "expectancy": float(pnl.mean()) if len(pnl) else np.nan,
            "win_rate": float((pnl > 0).mean()) if len(pnl) else np.nan,
            "avg_win": float(wins.mean()) if len(wins) else np.nan,
            "avg_loss": float(losses.mean()) if len(losses) else np.nan,
            "protective_stop_rate": float((exit_reasons == "stop").mean()) if len(exit_reasons) else 0.0,
            "trailing_stop_rate": float((exit_reasons == "trailing").mean()) if len(exit_reasons) else 0.0,
            "max_drawdown": float(snapshots["drawdown"].min()) if not snapshots.empty else 0.0,
            "execution_drag": float((pnl - expected).sum()) if len(pnl) else 0.0,
            "edge_retention": float(pnl.mean() / expected.mean()) if len(pnl) and expected.mean() else np.nan,
            "exit_mismatch_rate": exit_mismatches / len(comparable) if len(comparable) else 0.0,
            "stop_mismatch_rate": stop_mismatches / len(comparable) if len(comparable) else 0.0,
            "external_miss_rate": len(external_rejected) / len(decisions) if len(decisions) else 0.0,
            "signal_miss_rate": len(external_rejected) / len(decisions) if len(decisions) else 0.0,
            "avg_signal_latency_ms": float(signal_latency.mean()) if signal_latency.notna().any() else np.nan,
            "avg_processing_latency_ms": float(processing_latency.mean()) if processing_latency.notna().any() else np.nan,
            "avg_data_latency_ms": data_latency_ms,
            "avg_spread_bps": float(spreads.mean()) if spreads.notna().any() else np.nan,
            "avg_simulated_slippage_bps": float(slippage.mean()) if slippage.notna().any() else np.nan,
            "portfolio_rejection_rate": len(portfolio_rejected) / len(decisions) if len(decisions) else 0.0,
            "total_rejection_rate": len(rejected) / len(decisions) if len(decisions) else 0.0,
            "data_error_rate": len(data_rejected) / len(decisions) if len(decisions) else 0.0,
            "anomalies": int(len(events)),
        })
    return pd.DataFrame(rows).sort_values("profile").reset_index(drop=True)


def write_report(store: ForwardStateStore, output: str | Path) -> pd.DataFrame:
    report = build_profile_report(store)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    report.to_csv(temporary, index=False)
    temporary.replace(output)
    return report
