"""scripts/reconcile_9symbol_portfolio.py — Experiment 34 follow-up: re-score the
9-symbol portfolio (BTC+ETH+BNB+XRP+DOGE+ADA+LINK+LTC+SOLUSDT:transfer,
docs/multi_crypto_portfolio_9sym_trades.csv) through Codex's corrected shared
risk engine (quant_bot/risk/), not the old scripts/walk_forward_risk_sweep.py
that C-AUDIT-001 found to be materially wrong (non-chronological equity
accounting, missing registered costs, overlapping same-symbol positions).

Reuses quant_bot.risk.simulate_portfolio/RiskLimits/ExecutionCosts/
bootstrap_drawdowns UNCHANGED (read-only import, does not modify Codex's
owned files) with the exact same cost/limit construction as
scripts/validation_risk_frontier.py (ExecutionCosts(TAKER_FEE_PCT,
SLIPPAGE_PCT_EST/2), one_position_per_symbol=True, hard_leverage_ceiling=30.0,
no portfolio cap for this first curve) so the 8-symbol and 9-symbol results
are directly comparable apples-to-apples.

Usage:
    python scripts/reconcile_9symbol_portfolio.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import TAKER_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio, bootstrap_drawdowns

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
COSTS = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
RISK_PCTS = [0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.05, 0.06]


def score(data_path: str, label: str) -> pd.DataFrame:
    trades = pd.read_csv(data_path, parse_dates=["entry_time", "exit_time"])
    rows = []
    for risk_pct in RISK_PCTS:
        limits = RiskLimits(risk_pct=risk_pct, one_position_per_symbol=True, hard_leverage_ceiling=30.0)
        log, curve, metrics = simulate_portfolio(trades, limits, COSTS)
        row = {"portfolio": label, "risk_pct": risk_pct * 100, **metrics}
        if not log.empty:
            fractions = (log["pnl"] / log["entry_equity"]).to_numpy()
            mc = bootstrap_drawdowns(fractions, n_simulations=10_000, seed=42, block_size=1)
            mc_block = bootstrap_drawdowns(fractions, n_simulations=10_000, seed=42, block_size=20)
            row["mc_iid_p95_dd_pct"] = mc.get("p95_max_dd_pct")
            row["mc_iid_p_dd_gt_30"] = mc.get("p_dd_gt_30")
            row["mc_block20_p95_dd_pct"] = mc_block.get("p95_max_dd_pct")
            row["mc_block20_p_dd_gt_30"] = mc_block.get("p_dd_gt_30")
        rows.append(row)
        print(f"  [{label}] risk={risk_pct*100:.2f}%  n={row.get('n_trades')}  "
              f"CAGR={row.get('cagr_pct'):.2f}%  MaxDD={row.get('max_dd_pct'):.2f}%  "
              f"PF={row.get('profit_factor'):.3f}  Calmar={row.get('calmar'):.3f}  "
              f"forced_liq={row.get('forced_liquidations')}  "
              f"MC_block20_P(DD>30%)={row.get('mc_block20_p_dd_gt_30', float('nan'))*100:.1f}%")
    return pd.DataFrame(rows)


def main():
    print("=" * 110)
    print("  8-SYMBOL PORTFOLIO (registered adopted population, corrected engine)")
    print("=" * 110)
    df8 = score(os.path.join(DOCS, "multi_crypto_portfolio_trades.csv"), "8-symbol")

    print("\n" + "=" * 110)
    print("  9-SYMBOL PORTFOLIO (+SOLUSDT transfer-mode, corrected engine)")
    print("=" * 110)
    df9 = score(os.path.join(DOCS, "multi_crypto_portfolio_9sym_trades.csv"), "9-symbol")

    out = pd.concat([df8, df9], ignore_index=True)
    out_path = os.path.join(DOCS, "reconciled_portfolio_risk_frontier.csv")
    out.to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    # Robust-zone pick: max Calmar among candidates with 0 forced liquidations,
    # MaxDD magnitude < 25%, and MC block-bootstrap P(DD>30%) < 5% -- same
    # elimination discipline used throughout this project.
    for label, df in (("8-symbol", df8), ("9-symbol", df9)):
        ok = df[(df["forced_liquidations"] == 0) & (df["max_dd_pct"].abs() < 25.0) & (df["mc_block20_p_dd_gt_30"] < 0.05)]
        if len(ok):
            best = ok.loc[ok["calmar"].idxmax()]
            print(f"\n{label} ROBUST OPTIMUM: risk={best['risk_pct']:.2f}%  CAGR={best['cagr_pct']:.2f}%  "
                  f"MaxDD={best['max_dd_pct']:.2f}%  Calmar={best['calmar']:.3f}  PF={best['profit_factor']:.3f}  n={int(best['n_trades'])}")
        else:
            print(f"\n{label}: no risk level cleared the robust-zone bar")


if __name__ == "__main__":
    main()
