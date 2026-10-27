"""scripts/strategy_a/phase5_symbol_contribution.py — STRATEGY_ID = A
diagnostic (user mandate 2026-08-24, Phase 5): for each of the 9
symbols in the frozen baseline, compare FULL PORTFOLIO vs PORTFOLIO
WITHOUT SYMBOL X through the actual corrected risk engine (not naive
PnL subtraction -- removing a symbol changes compounding/ordering/
simultaneous-risk for every OTHER trade too). SHADOW/ANALYTICAL ONLY --
does not modify the frozen baseline.

Usage:
    python scripts/strategy_a/phase5_symbol_contribution.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd

from quant_bot.config import TAKER_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio, bootstrap_drawdowns

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
STRATEGY_A_DIR = os.path.join(DOCS, "strategy_a")
BASELINE_TRADES = os.path.join(DOCS, "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv")
RISK_PCT = 0.015
COSTS = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
LIMITS = RiskLimits(risk_pct=RISK_PCT, one_position_per_symbol=True, hard_leverage_ceiling=30.0)
SYMBOLS = ["ADAUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT", "XRPUSDT"]


def score(trades: pd.DataFrame, label: str) -> dict:
    log, curve, metrics = simulate_portfolio(trades, LIMITS, COSTS)
    row = {"label": label, **metrics}
    if not log.empty:
        fractions = (log["pnl"] / log["entry_equity"]).to_numpy()
        mc = bootstrap_drawdowns(fractions, n_simulations=10_000, seed=42, block_size=20)
        row["mc_p_dd_gt_30"] = mc.get("p_dd_gt_30")
    return row


def main():
    print("=" * 100)
    print("  STRATEGY A -- Phase 5: symbol marginal contribution (leave-one-out, via corrected engine)")
    print("=" * 100)

    trades = pd.read_csv(BASELINE_TRADES, parse_dates=["entry_time", "exit_time"])

    full = score(trades, "FULL_PORTFOLIO")
    print(f"\n  FULL PORTFOLIO: CAGR={full['cagr_pct']:.2f}%  MaxDD={full['max_dd_pct']:.2f}%  "
          f"Calmar={full['calmar']:.3f}  PF={full['profit_factor']:.3f}  n={full['n_trades']}  "
          f"MC_P(DD>30%)={(full.get('mc_p_dd_gt_30') or 0)*100:.1f}%")

    rows = [full]
    for sym in SYMBOLS:
        variant = trades[trades["symbol"] != sym]
        r = score(variant, f"WITHOUT_{sym}")
        rows.append(r)
        d_cagr = r["cagr_pct"] - full["cagr_pct"]
        d_dd = r["max_dd_pct"] - full["max_dd_pct"]
        d_calmar = r["calmar"] - full["calmar"]
        print(f"  WITHOUT {sym:8s}: CAGR={r['cagr_pct']:7.2f}% ({d_cagr:+6.2f}pp)  "
              f"MaxDD={r['max_dd_pct']:7.2f}% ({d_dd:+6.2f}pp)  Calmar={r['calmar']:6.3f} ({d_calmar:+6.3f})  "
              f"PF={r['profit_factor']:.3f}  n={r['n_trades']}  "
              f"MC_P(DD>30%)={(r.get('mc_p_dd_gt_30') or 0)*100:5.1f}%")

    out = pd.DataFrame(rows)
    out_path = os.path.join(STRATEGY_A_DIR, "phase5_symbol_leave_one_out.csv")
    out.to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    print("\n  Interpretation guide:")
    print("  - Calmar DROPS when removed -> symbol adds genuine risk-adjusted value (diversifying or high-quality).")
    print("  - Calmar IMPROVES when removed -> symbol is a net drag on risk-adjusted return (candidate for review).")
    print("  - CAGR drops but MaxDD also drops similarly -> symbol adds return AND proportional risk (neutral).")


if __name__ == "__main__":
    main()
