"""scripts/reconcile_experiment26.py — historical reconciliation: Experiment 26
("Full compounding risk-per-trade sweep with Monte Carlo") used
scripts/walk_forward_risk_sweep.py, the exact engine C-AUDIT-001 found to be
materially wrong (non-chronological equity realization, missing registered
costs applied in the compounding step, overlapping same-symbol positions).
This re-scores the SAME 55-trade population (docs/walk_forward_trades_export.csv,
36 ETH + 19 BTC) through Codex's corrected quant_bot/risk engine, changing
NOTHING else (same trades, same risk_pct grid points as the original including
the originally-adopted 7.5%, same elimination criteria the experiment itself
declared: forced_liq==0, MaxDD<=25%, MC P(DD>30%)<=5%) so the ONLY variable
isolated is old-engine vs corrected-engine.

Usage:
    python scripts/reconcile_experiment26.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import TAKER_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio, bootstrap_drawdowns

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
DATA_PATH = os.path.join(DOCS, "walk_forward_trades_export.csv")
COSTS = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
# Original grid included 0.25%-5.00%, extended to 7.5%-50% once the leverage
# cap was found never to bind under 5%; keep the same extended grid here.
RISK_PCTS = [0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.075, 0.10, 0.15, 0.20, 0.25]
MAX_ACCEPTABLE_DD = 25.0
MAX_MC_P_DD30 = 0.05


def main():
    trades = pd.read_csv(DATA_PATH, parse_dates=["entry_time", "exit_time"])
    print(f"Loaded {len(trades)} trades from {DATA_PATH} ({trades['symbol'].value_counts().to_dict()})")

    rows = []
    for risk_pct in RISK_PCTS:
        limits = RiskLimits(risk_pct=risk_pct, one_position_per_symbol=True, hard_leverage_ceiling=30.0)
        log, curve, metrics = simulate_portfolio(trades, limits, COSTS)
        row = {"risk_pct": risk_pct * 100, **metrics}
        if not log.empty:
            fractions = (log["pnl"] / log["entry_equity"]).to_numpy()
            mc = bootstrap_drawdowns(fractions, n_simulations=10_000, seed=42, block_size=20)
            row["mc_p_dd_gt_30"] = mc.get("p_dd_gt_30")
        else:
            row["mc_p_dd_gt_30"] = None
        rows.append(row)
        ok = (row.get("forced_liquidations", 1) == 0 and abs(row.get("max_dd_pct", 999)) <= MAX_ACCEPTABLE_DD
              and (row.get("mc_p_dd_gt_30") or 1.0) <= MAX_MC_P_DD30)
        print(f"  risk={risk_pct*100:>6.2f}%  n={row.get('n_trades'):>3}  CAGR={row.get('cagr_pct'):>8.2f}%  "
              f"MaxDD={row.get('max_dd_pct'):>7.2f}%  PF={row.get('profit_factor'):>6.3f}  "
              f"Calmar={row.get('calmar'):>7.3f}  forced_liq={row.get('forced_liquidations')}  "
              f"MC_P(DD>30%)={(row.get('mc_p_dd_gt_30') or 0)*100:>5.1f}%  {'OK' if ok else 'REJECT'}")

    df = pd.DataFrame(rows)
    out_path = os.path.join(DOCS, "reconciled_experiment26_risk_sweep.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    ok_rows = df[(df["forced_liquidations"] == 0) & (df["max_dd_pct"].abs() <= MAX_ACCEPTABLE_DD)
                 & (df["mc_p_dd_gt_30"] <= MAX_MC_P_DD30)]
    if len(ok_rows):
        best = ok_rows.loc[ok_rows["calmar"].idxmax()]
        print(f"\nROBUST OPTIMUM (max Calmar among survivors): risk={best['risk_pct']:.2f}%  "
              f"CAGR={best['cagr_pct']:.2f}%  MaxDD={best['max_dd_pct']:.2f}%  Calmar={best['calmar']:.3f}  "
              f"PF={best['profit_factor']:.3f}  n={int(best['n_trades'])}")
        print(f"Highest risk_pct clearing elimination: {ok_rows['risk_pct'].max():.2f}%")
    else:
        print("\nNo risk level cleared elimination.")


if __name__ == "__main__":
    main()
