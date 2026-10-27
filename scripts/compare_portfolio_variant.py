"""scripts/compare_portfolio_variant.py — Alpha-track experiment tool: score
two portfolio trade populations (current baseline vs a candidate variant that
changes exactly ONE symbol's config) through Codex's corrected quant_bot/risk
engine, same risk grid, for a direct KEEP/REJECT comparison. Read-only import
of quant_bot/risk (Codex-owned).

Usage:
    python scripts/compare_portfolio_variant.py --baseline docs/multi_crypto_portfolio_9sym_trades.csv --variant docs/multi_crypto_portfolio_9sym_xrpp80_trades.csv --baseline-label "9-symbol baseline" --variant-label "9-symbol + XRP p80"
"""
import argparse
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
COSTS = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
RISK_PCTS = [0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175, 0.02, 0.025, 0.03]
MAX_ACCEPTABLE_DD = 25.0
MAX_MC_P_DD30 = 0.05


def score(data_path: str, label: str) -> pd.DataFrame:
    trades = pd.read_csv(data_path, parse_dates=["entry_time", "exit_time"])
    rows = []
    for risk_pct in RISK_PCTS:
        limits = RiskLimits(risk_pct=risk_pct, one_position_per_symbol=True, hard_leverage_ceiling=30.0)
        log, curve, metrics = simulate_portfolio(trades, limits, COSTS)
        row = {"portfolio": label, "risk_pct": risk_pct * 100, **metrics}
        if not log.empty:
            fractions = (log["pnl"] / log["entry_equity"]).to_numpy()
            mc = bootstrap_drawdowns(fractions, n_simulations=10_000, seed=42, block_size=20)
            row["mc_p_dd_gt_30"] = mc.get("p_dd_gt_30")
        rows.append(row)
        ok = (row.get("forced_liquidations", 1) == 0 and abs(row.get("max_dd_pct", 999)) <= MAX_ACCEPTABLE_DD
              and (row.get("mc_p_dd_gt_30") or 1.0) <= MAX_MC_P_DD30)
        print(f"  [{label}] risk={risk_pct*100:>5.2f}%  n={row.get('n_trades'):>5}  "
              f"CAGR={row.get('cagr_pct'):>7.2f}%  MaxDD={row.get('max_dd_pct'):>7.2f}%  "
              f"PF={row.get('profit_factor'):>6.3f}  Calmar={row.get('calmar'):>7.3f}  "
              f"forced_liq={row.get('forced_liquidations')}  "
              f"MC_P(DD>30%)={(row.get('mc_p_dd_gt_30') or 0)*100:>5.1f}%  {'OK' if ok else 'REJECT'}")
    return pd.DataFrame(rows)


def robust_pick(df: pd.DataFrame):
    ok = df[(df["forced_liquidations"] == 0) & (df["max_dd_pct"].abs() <= MAX_ACCEPTABLE_DD)
            & (df["mc_p_dd_gt_30"] <= MAX_MC_P_DD30)]
    if len(ok):
        return ok.loc[ok["calmar"].idxmax()]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--baseline-label", default="baseline")
    parser.add_argument("--variant-label", default="variant")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    print("=" * 110)
    print(f"  {args.baseline_label}")
    print("=" * 110)
    df_base = score(args.baseline, args.baseline_label)

    print(f"\n{'='*110}\n  {args.variant_label}\n{'='*110}")
    df_var = score(args.variant, args.variant_label)

    out = pd.concat([df_base, df_var], ignore_index=True)
    out_path = args.out or os.path.join(DOCS, "portfolio_variant_comparison.csv")
    out.to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    best_base, best_var = robust_pick(df_base), robust_pick(df_var)
    print(f"\n{args.baseline_label} ROBUST OPTIMUM:", end=" ")
    if best_base is not None:
        print(f"risk={best_base['risk_pct']:.2f}%  CAGR={best_base['cagr_pct']:.2f}%  "
              f"MaxDD={best_base['max_dd_pct']:.2f}%  Calmar={best_base['calmar']:.3f}  PF={best_base['profit_factor']:.3f}")
    else:
        print("none cleared elimination")
    print(f"{args.variant_label} ROBUST OPTIMUM:", end=" ")
    if best_var is not None:
        print(f"risk={best_var['risk_pct']:.2f}%  CAGR={best_var['cagr_pct']:.2f}%  "
              f"MaxDD={best_var['max_dd_pct']:.2f}%  Calmar={best_var['calmar']:.3f}  PF={best_var['profit_factor']:.3f}")
    else:
        print("none cleared elimination")

    if best_base is not None and best_var is not None:
        print(f"\nDELTA (variant - baseline, at each side's OWN robust optimum): "
              f"CAGR={best_var['cagr_pct']-best_base['cagr_pct']:+.2f}pp  "
              f"MaxDD={best_var['max_dd_pct']-best_base['max_dd_pct']:+.2f}pp  "
              f"Calmar={best_var['calmar']-best_base['calmar']:+.3f}")
        # Also compare AT THE BASELINE'S OWN risk_pct, to isolate the trade-quality
        # effect from any risk_pct shift.
        same_risk = df_var[df_var["risk_pct"] == best_base["risk_pct"]]
        if len(same_risk):
            r = same_risk.iloc[0]
            print(f"Variant AT baseline's risk_pct ({best_base['risk_pct']:.2f}%): "
                  f"CAGR={r['cagr_pct']:.2f}%  MaxDD={r['max_dd_pct']:.2f}%  Calmar={r['calmar']:.3f}  "
                  f"PF={r['profit_factor']:.3f}  forced_liq={r['forced_liquidations']}")


if __name__ == "__main__":
    main()
