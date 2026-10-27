"""scripts/strategy_a/experiment42_dynamic_universe.py — STRATEGY_ID = A,
Experiment 42, Steps 7-11: TRAIN-DECIDE / TEST-EVALUATE dynamic universe
vs the static 9-symbol baseline, with a NULL CONTROL (random exclusion
of the same size) to check the improvement isn't just mechanical
risk-reduction from fewer positions. SHADOW/ANALYTICAL ONLY.

PRE-REGISTERED RULE (fixed before looking at TEST results): at the end
of each fold's TRAIN period, a symbol among {BTC,ETH,BNB,LTC} is
EXCLUDED from that fold's NEXT TEST period if and only if its TRAIN
marginal d_calmar > 0 (i.e. removing it improved TRAIN Calmar) for that
specific fold -- using the already-computed
experiment42_train_marginal_contribution.csv. No other symbols are ever
excluded (SOL/XRP/ADA/DOGE/LINK are never candidates, per the mandate's
explicit "one hypothesis per symbol, only the 4 priority symbols").

Usage:
    python scripts/strategy_a/experiment42_dynamic_universe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.config import TAKER_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio, bootstrap_drawdowns
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
DATA_START = pd.Timestamp("2019-11-27", tz="UTC")
N_NULL_DRAWS = 200
RNG_SEED = 42


def score(trades: pd.DataFrame) -> dict:
    if len(trades) < 10:
        return None
    log, curve, metrics = simulate_portfolio(trades, LIMITS, COSTS)
    if not log.empty:
        fractions = (log["pnl"] / log["entry_equity"]).to_numpy()
        mc = bootstrap_drawdowns(fractions, n_simulations=5_000, seed=RNG_SEED, block_size=20)
        metrics["mc_p_dd_gt_20"] = mc.get("p_dd_gt_20")
        metrics["mc_p_dd_gt_30"] = mc.get("p_dd_gt_30")
        metrics["mc_p_dd_gt_50"] = mc.get("p_dd_gt_50")
    return metrics


def main():
    print("=" * 100)
    print("  STRATEGY A -- Experiment 42 Steps 7-11: TRAIN-DECIDE/TEST-EVALUATE dynamic universe + NULL CONTROL")
    print("=" * 100)

    trades = pd.read_csv(BASELINE_TRADES, parse_dates=["entry_time", "exit_time"])
    train_deltas = pd.read_csv(os.path.join(STRATEGY_A_DIR, "experiment42_train_marginal_contribution.csv"))
    train_deltas = train_deltas[train_deltas["population"] == "TRAIN"]

    folds = build_folds(DATA_START, SAFE_END)
    print(f"\n  Pre-registered rule: exclude symbol X from fold i's TEST if X's TRAIN d_calmar > 0 in fold i "
          f"(computed on fold i's TRAIN population, from experiment42_fold_marginal_contribution.py)")

    static_test_trades, dynamic_test_trades = [], []
    exclusion_log = []
    rng = np.random.default_rng(RNG_SEED)
    null_draws_trades = [[] for _ in range(N_NULL_DRAWS)]

    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        test_pop = trades[(trades["entry_time"] >= train_end) & (trades["entry_time"] < test_end)]
        if len(test_pop) == 0:
            continue
        static_test_trades.append(test_pop)

        fold_train = train_deltas[train_deltas["fold"] == fold_i]
        excluded_this_fold = []
        for sym in PRIORITY_SYMBOLS:
            row = fold_train[fold_train["symbol"] == sym]
            if len(row) and row["d_calmar"].iloc[0] > 0:
                excluded_this_fold.append(sym)
        exclusion_log.append({"fold": fold_i, "test_start": train_end, "excluded": ",".join(excluded_this_fold) or "(none)",
                               "n_excluded": len(excluded_this_fold)})
        dynamic_pop = test_pop[~test_pop["symbol"].isin(excluded_this_fold)]
        dynamic_test_trades.append(dynamic_pop)

        # NULL CONTROL: for each of N_NULL_DRAWS random draws, exclude the SAME NUMBER of symbols
        # (drawn randomly from the 4 priority symbols present that fold) as the real rule did.
        for draw_i in range(N_NULL_DRAWS):
            if len(excluded_this_fold) > 0:
                candidates = [s for s in PRIORITY_SYMBOLS if s in test_pop["symbol"].unique()]
                k = min(len(excluded_this_fold), len(candidates))
                random_excl = rng.choice(candidates, size=k, replace=False) if k > 0 else []
                null_pop = test_pop[~test_pop["symbol"].isin(random_excl)]
            else:
                null_pop = test_pop
            null_draws_trades[draw_i].append(null_pop)

    exclusion_df = pd.DataFrame(exclusion_log)
    print("\n  STEP 8 -- universe turnover:")
    print(exclusion_df.to_string(index=False))
    exclusion_df.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_exclusion_log.csv"), index=False)
    for sym in PRIORITY_SYMBOLS:
        flips = exclusion_df["excluded"].apply(lambda x: sym in x.split(","))
        n_flips = (flips != flips.shift(1)).sum() - 1  # transitions in/out
        print(f"  {sym}: excluded in {flips.sum()}/{len(flips)} folds, status changes {max(0,n_flips)} times")

    static_all = pd.concat(static_test_trades, ignore_index=True)
    dynamic_all = pd.concat(dynamic_test_trades, ignore_index=True)

    static_metrics = score(static_all)
    dynamic_metrics = score(dynamic_all)

    print(f"\n  STEP 9 -- portfolio metrics (TEST-fold trades only, same population basis, risk_pct={RISK_PCT}):")
    print(f"  STATIC 9-SYMBOL (TEST folds only): n={static_metrics['n_trades']}  CAGR={static_metrics['cagr_pct']:.2f}%  "
          f"MaxDD={static_metrics['max_dd_pct']:.2f}%  Calmar={static_metrics['calmar']:.3f}  PF={static_metrics['profit_factor']:.3f}  "
          f"P(DD>20%)={static_metrics.get('mc_p_dd_gt_20',0)*100:.1f}%  P(DD>30%)={static_metrics.get('mc_p_dd_gt_30',0)*100:.1f}%  "
          f"P(DD>50%)={static_metrics.get('mc_p_dd_gt_50',0)*100:.1f}%")
    print(f"  DYNAMIC UNIVERSE (TRAIN-decided):   n={dynamic_metrics['n_trades']}  CAGR={dynamic_metrics['cagr_pct']:.2f}%  "
          f"MaxDD={dynamic_metrics['max_dd_pct']:.2f}%  Calmar={dynamic_metrics['calmar']:.3f}  PF={dynamic_metrics['profit_factor']:.3f}  "
          f"P(DD>20%)={dynamic_metrics.get('mc_p_dd_gt_20',0)*100:.1f}%  P(DD>30%)={dynamic_metrics.get('mc_p_dd_gt_30',0)*100:.1f}%  "
          f"P(DD>50%)={dynamic_metrics.get('mc_p_dd_gt_50',0)*100:.1f}%")

    d_calmar_actual = dynamic_metrics["calmar"] - static_metrics["calmar"]
    print(f"\n  ACTUAL delta Calmar (dynamic - static): {d_calmar_actual:+.3f}")

    # STEP 11: null control
    print(f"\n  STEP 11 -- NULL CONTROL: {N_NULL_DRAWS} random-exclusion draws (same exclusion COUNT per fold)")
    null_calmars = []
    for draw_i in range(N_NULL_DRAWS):
        null_all = pd.concat(null_draws_trades[draw_i], ignore_index=True)
        m = score(null_all)
        if m is not None:
            null_calmars.append(m["calmar"])
    null_calmars = np.array(null_calmars)
    pct_null_better_than_actual = float((null_calmars >= dynamic_metrics["calmar"]).mean() * 100)
    print(f"  null-draw Calmar distribution: mean={null_calmars.mean():.3f}  median={np.median(null_calmars):.3f}  "
          f"std={null_calmars.std():.3f}  min={null_calmars.min():.3f}  max={null_calmars.max():.3f}")
    print(f"  static baseline Calmar (TEST folds): {static_metrics['calmar']:.3f}")
    print(f"  TRAIN-decided dynamic universe Calmar: {dynamic_metrics['calmar']:.3f}")
    print(f"  fraction of RANDOM exclusion draws that matched or beat the TRAIN-decided result: "
          f"{pct_null_better_than_actual:.1f}%")
    print(f"  (if this fraction is high, e.g. >30-50%, the TRAIN-decided rule is NOT meaningfully better than")
    print(f"   randomly dropping the same number of symbols -- the 'improvement' would just be mechanical")
    print(f"   risk reduction from fewer positions, not smart symbol selection)")

    out = pd.DataFrame([
        {"label": "STATIC_9SYM_TEST_FOLDS", **static_metrics},
        {"label": "DYNAMIC_UNIVERSE_TRAIN_DECIDED", **dynamic_metrics},
        {"label": "NULL_CONTROL_MEAN", "calmar": null_calmars.mean(), "n_trades": None, "cagr_pct": None,
         "max_dd_pct": None, "profit_factor": None},
    ])
    out.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_dynamic_vs_static_vs_null.csv"), index=False)
    print(f"\nSaved -> {os.path.join(STRATEGY_A_DIR, 'experiment42_dynamic_vs_static_vs_null.csv')}")


if __name__ == "__main__":
    main()
