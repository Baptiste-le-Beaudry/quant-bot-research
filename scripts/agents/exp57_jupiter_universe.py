"""Exp 57 (A-JUP-UNIVERSE-001) -- executed to the letter of docs/agents/hypotheses/Exp-57.md (commit 8eacbc6).

Rule: existing-model entries for SOL, BTC, ETH; time exit 50 bars, NO stop; entry at the next
bar's open; one position per symbol; 33 % of capital per position; 500 CAD account.
Costs: principal = jupiter_build (/build, ~0.02 % RT + 0.01 USD per swap); stress = jupiter_order
(/order: SOL 0.041 % RT measured, cbBTC/WETH 0.20 % RT) -- reported, not decisional.
Populations: P1 pre-HOLDOUT ledger; P2 Exp 50 entries (already-seen window). Both only reject.

Harness v1.1.0. Bars read-only from --cache-dir. Outputs under docs/agents/results/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.execution_harness import (VERSION, USD_PER_CAD, ExitRule, apply_costs, load_bars,  # noqa: E402
                                         profit_factor, run_trades, simulate_account)

SYMS = ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
POPS = {"P1": ROOT / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv",
        "P2": ROOT / "docs" / "experiment50_trades.csv"}
RULE = ExitRule(max_bars=50)  # no stop, candidate stops never applied (v1.1)
INITIAL_CAD, FRACTION = 500.0, 0.33
COSTS = {"principal_build": "jupiter_build", "stress_order": "jupiter_order"}
OUT = ROOT / "docs" / "agents" / "results"


def candidates(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["entry_time"])
    d = d[d.symbol.isin(SYMS)]
    # no stop_distance column passed: the rule has no stop
    return pd.DataFrame({"symbol": d.symbol.values, "signal_time": d.entry_time.values, "side": 1})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--date", default="2026-10-07")
    args = ap.parse_args(argv)
    loader = lambda s: load_bars(s, args.cache_dir)  # noqa: E731
    notional = INITIAL_CAD * USD_PER_CAD.value * FRACTION
    per_trade, accounts, status_rows = [], [], []
    for pop, path in POPS.items():
        cand = candidates(path)
        dup = int(cand.duplicated(["symbol", "signal_time"]).sum())
        sim = run_trades(cand, RULE, "research_0p14", loader, entry_mode="next_open")
        st = sim.groupby(["symbol", "status"]).size().rename("n").reset_index().assign(population=pop)
        status_rows.append(st)
        ok_all = sim[sim.status == "ok"]
        period = (ok_all.signal_time.min(), ok_all.exit_time.max())
        for cost_name, plat in COSTS.items():
            t = apply_costs(sim, plat, notional_usd=notional)
            ok = t[t.status == "ok"]
            for sym in SYMS:
                x = ok[ok.symbol == sym]
                per_trade.append({"population": pop, "cost": cost_name, "platform": plat, "symbol": sym,
                                  "n": len(x), "duplicates_in_input": dup,
                                  "mean_gross_pct": 100 * x.gross_ret.mean(),
                                  "mean_net_pct_proportional": 100 * x.net_ret.mean(),
                                  "mean_net_pct_at_size": 100 * x.net_ret_at_size.mean(),
                                  "pf_at_size": profit_factor(x.net_ret_at_size),
                                  "t_stat_at_size": float(x.net_ret_at_size.mean() / x.net_ret_at_size.std(ddof=1)
                                                          * np.sqrt(len(x))) if len(x) > 1 else np.nan,
                                  "first": str(x.signal_time.min()), "last": str(x.exit_time.max())})
            for acct_name, syms in (("SOL_only", ["SOLUSDT"]), ("SOL_BTC_ETH", SYMS)):
                tt = t.copy()
                tt.loc[~tt.symbol.isin(syms) & (tt.status == "ok"), "status"] = "excluded_universe"
                a = simulate_account(tt, plat, INITIAL_CAD, USD_PER_CAD.value, position_fraction=FRACTION,
                                     max_gross_exposure=1.0, one_position_per_symbol=True, period=period)
                led = a["ledger"]
                accounts.append({"population": pop, "cost": cost_name, "platform": plat, "account": acct_name,
                                 "period_start": str(period[0]), "period_end": str(period[1]),
                                 **{k: v for k, v in a.items() if k not in ("ledger", "equity_minute", "skips")},
                                 **{f"skip_{k}": v for k, v in a["skips"].items()},
                                 **{f"n_taken_{s[:3]}": int((led.symbol == s).sum()) for s in syms},
                                 **{f"mean_ret_on_notional_{s[:3]}_pct": 100 * float(led.loc[led.symbol == s,
                                                                                            "ret_on_notional"].mean())
                                    for s in syms}})
        print(pop, "done", flush=True)
    pt, ac = pd.DataFrame(per_trade), pd.DataFrame(accounts)
    st = pd.concat(status_rows)
    OUT.mkdir(parents=True, exist_ok=True)
    pt.to_csv(OUT / f"Exp-57_{args.date}_per_trade.csv", index=False)
    ac.to_csv(OUT / f"Exp-57_{args.date}_accounts.csv", index=False)
    st.to_csv(OUT / f"Exp-57_{args.date}_status.csv", index=False)

    # preregistered criteria (principal cost)
    crit = {}
    for pop in POPS:
        p = pt[(pt.population == pop) & (pt.cost == "principal_build")].set_index("symbol")
        a = ac[(ac.population == pop) & (ac.cost == "principal_build")].set_index("account")
        crit[pop] = {
            "a_BTC_net_at_size_pct": float(p.loc["BTCUSDT", "mean_net_pct_at_size"]),
            "a_ETH_net_at_size_pct": float(p.loc["ETHUSDT", "mean_net_pct_at_size"]),
            "a_BTC_pass": bool(p.loc["BTCUSDT", "mean_net_pct_at_size"] > 0),
            "a_ETH_pass": bool(p.loc["ETHUSDT", "mean_net_pct_at_size"] > 0),
            "b_cagr_combined_pct": float(a.loc["SOL_BTC_ETH", "cagr_cad_pct"]),
            "b_cagr_sol_only_pct": float(a.loc["SOL_only", "cagr_cad_pct"]),
            "b_pass": bool(a.loc["SOL_BTC_ETH", "cagr_cad_pct"] > a.loc["SOL_only", "cagr_cad_pct"]),
            "c_maxdd_combined_pct": float(a.loc["SOL_BTC_ETH", "max_dd_pct"]),
            "c_pass": bool(a.loc["SOL_BTC_ETH", "max_dd_pct"] >= -35.0),
        }
    all_pass = all(c["a_BTC_pass"] and c["a_ETH_pass"] and c["b_pass"] and c["c_pass"] for c in crit.values())
    reject_a = any((not c["a_BTC_pass"]) and (not c["a_ETH_pass"]) for c in crit.values())
    reject_b = all(not c["b_pass"] for c in crit.values())
    mech = "PASS" if all_pass else ("REJET" if (reject_a or reject_b) else "INCERTAIN")
    res = {"harness_version": VERSION, "notional_usd_at_33pct": notional, "usd_per_cad": USD_PER_CAD.value,
           "criteria": crit, "mechanical_reading": mech,
           "reject_by_a": reject_a, "reject_by_b": reject_b}
    (OUT / f"Exp-57_{args.date}_criteria.json").write_text(json.dumps(res, indent=2))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(pt.round(4).to_string())
    print(ac[["population", "cost", "account", "n_trades", "total_return_cad_pct", "cagr_cad_pct", "max_dd_pct",
              "worst_day_pct", "worst_day_date", "worst_intraday_pct", "worst_week_pct", "years",
              "skip_symbol_busy", "skip_exposure_cap"]].round(3).to_string())
    print(st.to_string())
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
