"""Mandatory reconciliation test + platform table on the pre-HOLDOUT reference entries.

Reference: ``scripts/strategy_a/exit_realism_check.py`` mode ``intrabar`` on the
frozen 9-symbol baseline ledger (2,549 walk-forward TEST trades, 2021-11-30 ->
2025-04-07, pre-HOLDOUT): PF 0.951, mean net -0.025 %/trade at 0.14 % RT.

Usage (bars are read-only from the main checkout's git-ignored cache)::

    py -3 -m quant_bot.execution_harness.reconcile --cache-dir path/to/bar_cache

Writes only under ``docs/agents/harness/``.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import VERSION
from .costs import PLATFORMS, TABLE_PLATFORMS, USD_PER_CAD
from .data import REPO, load_bars
from .fills import ExitRule
from .harness import apply_costs, profit_factor, run_trades, simulate_account, summarize

LEDGER = REPO / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv"
REFERENCE_CSV = REPO / "docs" / "exit_realism_check.csv"
OUT = REPO / "docs" / "agents" / "harness"
REF_RULE = ExitRule(max_bars=50, trail_activation=0.0063, trail_distance=0.0080,
                    use_candidate_stop=True)  # stop per trade from the ledger
TIME50 = ExitRule(max_bars=50)  # deployed Jupiter exit, NO stop (v1.1: candidate stop ignored, review C1)
LATENCIES = (0, 1, 2)
EXPECTED = {"n": 2549, "pf": 0.951, "mean_net_pct": -0.025}


def candidates() -> pd.DataFrame:
    led = pd.read_csv(LEDGER, parse_dates=["entry_time"])
    return pd.DataFrame({"symbol": led.symbol, "signal_time": led.entry_time,
                         "stop_distance": led.stop_distance, "side": 1})


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--initial-cad", type=float, default=500.0)
    ap.add_argument("--usd-per-cad", type=float, default=USD_PER_CAD.value)
    args = ap.parse_args(argv)
    loader = lambda s: load_bars(s, args.cache_dir)  # noqa: E731
    cand = candidates()
    report: dict = {"harness_version": VERSION, "ledger": str(LEDGER.relative_to(REPO))}

    # 1) legacy convention (entry at signal close) must match the reference trade by trade
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # signal_close is intended here (reconciliation)
        legacy = run_trades(cand, REF_RULE, "research_0p14", loader, entry_mode="signal_close")
    ref = pd.read_csv(REFERENCE_CSV, parse_dates=["entry_time"])
    m = legacy.merge(ref[["symbol", "entry_time", "intrabar"]].rename(columns={"entry_time": "signal_time"}),
                     on=["symbol", "signal_time"], how="outer", indicator=True)
    both = m[m._merge == "both"]
    s_leg = summarize(legacy)
    report["legacy_signal_close"] = {
        **{k: s_leg[k] for k in ("n_trades", "n_skipped", "mean_gross_pct", "mean_net_ret_pct", "pf", "win_rate")},
        "matched_to_reference": int(len(both)), "unmatched": int((m._merge != "both").sum()),
        "max_abs_diff_vs_reference": float(np.abs(both.gross_ret - both.intrabar).max()),
        "reference_pf": profit_factor(ref.intrabar - 0.0014),
        "reference_mean_net_pct": 100 * float((ref.intrabar - 0.0014).mean()),
        "expected": EXPECTED}

    # 2) harness default: next-bar open entry
    nxt = run_trades(cand, REF_RULE, "research_0p14", loader, entry_mode="next_open")
    s_nxt = summarize(nxt)
    j = legacy[["cand_id", "entry_price", "gross_ret", "exit_reason", "exit_idx"]].merge(
        nxt[["cand_id", "entry_price", "gross_ret", "exit_reason", "exit_idx"]], on="cand_id",
        suffixes=("_legacy", "_next"))
    entry_gap = j.entry_price_next / j.entry_price_legacy - 1
    report["next_open"] = {
        **{k: s_nxt[k] for k in ("n_trades", "n_skipped", "mean_gross_pct", "mean_net_ret_pct", "pf",
                                 "win_rate", "exit_reasons", "n_gap_windows", "period")},
        "delta_mean_net_pct_vs_legacy": s_nxt["mean_net_ret_pct"] - s_leg["mean_net_ret_pct"],
        "entry_open_vs_signal_close_mean_pct": 100 * float(entry_gap.mean()),
        "entry_open_vs_signal_close_abs_mean_pct": 100 * float(entry_gap.abs().mean()),
        "entry_open_eq_signal_close_share": float((entry_gap == 0).mean()),
        "n_exit_reason_changed": int((j.exit_reason_legacy != j.exit_reason_next).sum()),
        "n_exit_bar_changed": int((j.exit_idx_legacy != j.exit_idx_next).sum()),
        "delta_gross_mean_pct": 100 * float((j.gross_ret_next - j.gross_ret_legacy).mean()),
    }
    # decomposition: price effect alone = rescale legacy exit price by the new entry price
    price_only = (1 + j.gross_ret_legacy) / (1 + entry_gap) - 1
    report["next_open"]["delta_from_entry_price_only_pct"] = 100 * float((price_only - j.gross_ret_legacy).mean())
    report["next_open"]["delta_from_path_changes_pct"] = 100 * float((j.gross_ret_next - price_only).mean())

    # 3) platform tables (in-sample, pre-HOLDOUT entries); fills simulated once per (rule, latency)
    rows, accts = [], []
    notional_33 = args.initial_cad * args.usd_per_cad * 0.33
    for rule_name, rule in (("REF_stop_trail_50", REF_RULE), ("TIME50_nostop", TIME50)):
        for lat in LATENCIES:
            sim = run_trades(cand, rule, "research_0p14", loader, entry_mode="next_open", latency_bars=lat)
            for name in TABLE_PLATFORMS:
                plat = PLATFORMS[name]
                t = apply_costs(sim, plat, notional_usd=notional_33)
                s = summarize(t)
                ok = t[t.status == "ok"]
                row = {"harness_version": VERSION, "rule": rule_name, "latency_bars": lat, "platform": name,
                       "n_trades": s["n_trades"], "n_unsupported": int((t.status == "unsupported_symbol").sum()),
                       "n_data_defects": int(t.status.isin(["nan_in_window", "gap_in_window", "end_of_data"]).sum()),
                       "exit_stop_or_trail": int(ok.exit_reason.isin(["stop", "trail"]).sum()),
                       "mean_gross_pct": s["mean_gross_pct"],
                       "cost_rt_mean_pct": 100 * float(ok.cost_rt.mean()) if len(ok) else np.nan,
                       "mean_net_pct": s["mean_net_ret_pct"], "pf_net": s["pf"],
                       "mean_net_at_33pct_of_500cad_pct": 100 * float(ok.net_ret_at_size.mean()) if len(ok) else np.nan}
                rows.append(row)
                print(rule_name, lat, name, {k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()
                                             if k in ("n_trades", "mean_net_pct", "pf_net")}, flush=True)
                if lat != 0 or not len(ok):
                    continue
                for frac in (0.10, 0.33):
                    a = simulate_account(t, plat, args.initial_cad, args.usd_per_cad, position_fraction=frac)
                    accts.append({"harness_version": VERSION, "rule": rule_name, "platform": name,
                                  "position_fraction": frac,
                                  **{k: v for k, v in a.items() if k not in ("ledger", "equity_minute", "skips")},
                                  **{f"skip_{k}": v for k, v in a["skips"].items()}})
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "T-006_platform_table.csv", index=False)
    pd.DataFrame(accts).to_csv(OUT / "T-006_account_table.csv", index=False)
    pd.DataFrame([r for p in PLATFORMS.values() for r in p.describe()]).to_csv(OUT / "cost_sources_v1.1.csv", index=False)
    (OUT / "T-006_reconciliation.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    main()
