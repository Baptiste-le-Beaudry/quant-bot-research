"""scripts/strategy_a/experiment42_fold_marginal_contribution.py —
STRATEGY_ID = A, Experiment 42, Steps 1-3: temporal (fold-by-fold)
marginal contribution of BTC/ETH/BNB/LTC (the leave-one-out "drag"
symbols from the alpha decomposition), computed on each fold's own
TRAIN population, then separately observed on that fold's TEST
population -- answers whether the negative marginal contribution is a
full-sample artifact or a repeatedly-observed pattern across
independent periods. SHADOW/ANALYTICAL ONLY -- frozen baseline
untouched, HOLDOUT never accessed.

STEP 1 (independence audit): the original leave-one-out finding used
the ENTIRE pre-HOLDOUT executed trade population (2021-11-30 ->
2025-04-07) -- there is NO leftover pre-HOLDOUT period that wasn't
already used to discover it. This experiment does NOT claim an
independent holdout-style validation; it uses a walk-forward protocol
where each fold's OWN TRAIN population determines a descriptive
observation, cross-checked against that fold's OWN TEST population,
across 12 non-overlapping TEST periods -- the closest honest
approximation to temporal validation available without touching
HOLDOUT.

Usage:
    python scripts/strategy_a/experiment42_fold_marginal_contribution.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.config import TAKER_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio
from scripts.walk_forward_engine import build_folds, SAFE_END

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
PRIORITY_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "LTCUSDT"]
CONTROL_SYMBOLS = ["SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT"]
ALL_SYMBOLS = PRIORITY_SYMBOLS + CONTROL_SYMBOLS
MIN_TRADES_FOR_METRICS = 30
DATA_START = pd.Timestamp("2019-11-27", tz="UTC")


def score(trades: pd.DataFrame) -> dict:
    if len(trades) < MIN_TRADES_FOR_METRICS:
        return None
    log, curve, metrics = simulate_portfolio(trades, LIMITS, COSTS)
    if metrics.get("n_trades", 0) < MIN_TRADES_FOR_METRICS:
        return None
    return metrics


def marginal_deltas(pop: pd.DataFrame) -> dict:
    full = score(pop)
    if full is None:
        return None
    out = {"full": full}
    for sym in ALL_SYMBOLS:
        variant = pop[pop["symbol"] != sym]
        m = score(variant)
        if m is None:
            out[sym] = None
            continue
        out[sym] = {
            "d_cagr": m["cagr_pct"] - full["cagr_pct"],
            "d_maxdd": m["max_dd_pct"] - full["max_dd_pct"],
            "d_calmar": m["calmar"] - full["calmar"],
            "d_pf": m["profit_factor"] - full["profit_factor"],
            "n_removed": full["n_trades"] - m["n_trades"],
        }
    return out


def main():
    print("=" * 100)
    print("  STRATEGY A -- Experiment 42 Steps 1-3: temporal marginal contribution (BTC/ETH/BNB/LTC)")
    print("=" * 100)
    print("  STEP 1 (independence audit): the full pre-HOLDOUT trade population was ALREADY used for")
    print("  the original leave-one-out finding -- no leftover independent period exists. Using a")
    print("  walk-forward protocol (12 TRAIN/TEST fold pairs) as the honest alternative, per protocol.")

    trades = pd.read_csv(BASELINE_TRADES, parse_dates=["entry_time", "exit_time"])
    folds = build_folds(DATA_START, SAFE_END)
    print(f"\n  {len(folds)} folds available (fold 1 has 0 TRAIN trades, unusable -- {len(folds)-1} usable "
          f"TRAIN/TEST pairs from fold 2 onward)")

    train_records, test_records = [], []
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        train_pop = trades[(trades["entry_time"] >= t0) & (trades["entry_time"] < train_end)]
        test_pop = trades[(trades["entry_time"] >= train_end) & (trades["entry_time"] < test_end)]

        train_deltas = marginal_deltas(train_pop)
        test_deltas = marginal_deltas(test_pop)

        if train_deltas is not None:
            for sym in ALL_SYMBOLS:
                if train_deltas.get(sym) is not None:
                    train_records.append({"fold": fold_i, "symbol": sym, "population": "TRAIN",
                                           "n_pop": len(train_pop), **train_deltas[sym]})
        if test_deltas is not None:
            for sym in ALL_SYMBOLS:
                if test_deltas.get(sym) is not None:
                    test_records.append({"fold": fold_i, "symbol": sym, "population": "TEST",
                                          "n_pop": len(test_pop), **test_deltas[sym]})

    train_df = pd.DataFrame(train_records)
    test_df = pd.DataFrame(test_records)
    train_df.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_train_marginal_contribution.csv"), index=False)
    test_df.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_test_marginal_contribution.csv"), index=False)

    print("\n" + "=" * 100)
    print("  STEP 3 -- CENTRAL QUESTION: is the negative marginal contribution stable across folds?")
    print("=" * 100)
    print("\n  TRAIN population (cumulative, within-fold, larger n -- more folds usable):")
    summary_rows = []
    for sym in PRIORITY_SYMBOLS + CONTROL_SYMBOLS:
        sub = train_df[train_df["symbol"] == sym]
        if len(sub) == 0:
            continue
        pct_improve = (sub["d_calmar"] > 0).mean() * 100  # removing X improves Calmar = X is a drag
        row = {
            "symbol": sym, "n_folds": len(sub),
            "pct_folds_removal_improves_calmar": round(pct_improve, 1),
            "median_d_calmar": round(sub["d_calmar"].median(), 3), "mean_d_calmar": round(sub["d_calmar"].mean(), 3),
            "median_d_cagr": round(sub["d_cagr"].median(), 2), "median_d_maxdd": round(sub["d_maxdd"].median(), 2),
            "worst_fold_d_calmar": round(sub["d_calmar"].min(), 3), "best_fold_d_calmar": round(sub["d_calmar"].max(), 3),
        }
        summary_rows.append(row)
    train_summary = pd.DataFrame(summary_rows).sort_values("pct_folds_removal_improves_calmar", ascending=False)
    print(train_summary.to_string(index=False))
    train_summary.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_train_summary.csv"), index=False)

    print("\n  TEST population (out-of-sample, smaller n per fold -- interpret medians cautiously):")
    summary_rows_test = []
    for sym in PRIORITY_SYMBOLS + CONTROL_SYMBOLS:
        sub = test_df[test_df["symbol"] == sym]
        if len(sub) == 0:
            continue
        pct_improve = (sub["d_calmar"] > 0).mean() * 100
        row = {
            "symbol": sym, "n_folds": len(sub),
            "pct_folds_removal_improves_calmar": round(pct_improve, 1),
            "median_d_calmar": round(sub["d_calmar"].median(), 3), "mean_d_calmar": round(sub["d_calmar"].mean(), 3),
            "median_d_cagr": round(sub["d_cagr"].median(), 2), "median_d_maxdd": round(sub["d_maxdd"].median(), 2),
            "worst_fold_d_calmar": round(sub["d_calmar"].min(), 3), "best_fold_d_calmar": round(sub["d_calmar"].max(), 3),
        }
        summary_rows_test.append(row)
    test_summary = pd.DataFrame(summary_rows_test).sort_values("pct_folds_removal_improves_calmar", ascending=False)
    print(test_summary.to_string(index=False))
    test_summary.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_test_summary.csv"), index=False)

    print("\n  Per-fold detail for the 4 priority symbols (TRAIN population, d_calmar sign per fold):")
    for sym in PRIORITY_SYMBOLS:
        sub = train_df[train_df["symbol"] == sym].sort_values("fold")
        signs = "".join("+" if v > 0 else "-" for v in sub["d_calmar"])
        print(f"  {sym:8s}: folds={list(sub['fold'])}  d_calmar_signs={signs}  "
              f"(+ means removal improves Calmar / symbol is a drag that fold)")


if __name__ == "__main__":
    main()
