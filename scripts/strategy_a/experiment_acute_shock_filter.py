"""scripts/strategy_a/experiment_acute_shock_filter.py — STRATEGY_ID = A,
SHADOW/CANDIDATE experiment (pre-registered in docs/strategy_a/
STRATEGY_A_ALPHA_DECOMPOSITION.md Section 8): does excluding entries
during an acute, short-horizon (15min) sharply-negative BTC move reduce
the correlated protective-stop-cluster losses found in the decomposition
(Section 5) without giving up a comparable share of trailing-stop
profit? SHADOW TEST ONLY -- does not modify the frozen baseline used by
Codex's forward paper trading. HOLDOUT never accessed.

TRAIN-only calibration: the exclusion threshold (5th percentile of
btc_ret_15min) is computed from BTC's OWN first 24 months of price data
(2019-09-08 -> 2021-09-08, matching this project's own INITIAL_TRAIN_MONTHS
convention) -- a single frozen threshold, not per-fold recalibrated (a
documented simplification appropriate for a first-pass SHADOW screen,
not for baseline promotion).

Usage:
    python scripts/strategy_a/experiment_acute_shock_filter.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR, TAKER_FEE_PCT, SLIPPAGE_PCT_EST
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
BTC_HOLDOUT_START = pd.Timestamp("2025-03-28", tz="UTC")
TRAIN_START, TRAIN_END = pd.Timestamp("2019-09-08", tz="UTC"), pd.Timestamp("2021-09-08", tz="UTC")
RET_WINDOW_MIN = 15
EXCLUSION_PERCENTILE = 5  # TRAIN-only


def load_btc_1min() -> pd.Series:
    files = sorted(glob.glob(os.path.join(DATA_DIR, "BTCUSDT_1m_*.csv")))
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    close = df["close"]
    close = close[close.index < BTC_HOLDOUT_START]  # never read at/after BTC's own lock
    return close


def main():
    print("=" * 100)
    print("  STRATEGY A -- SHADOW experiment: acute short-horizon BTC-shock exclusion filter")
    print("  (pre-registered in STRATEGY_A_ALPHA_DECOMPOSITION.md Section 8; baseline NOT modified)")
    print("=" * 100)

    btc_close = load_btc_1min()
    btc_ret_15min = btc_close.pct_change(RET_WINDOW_MIN)

    train_slice = btc_ret_15min[(btc_ret_15min.index >= TRAIN_START) & (btc_ret_15min.index < TRAIN_END)].dropna()
    threshold = float(np.percentile(train_slice, EXCLUSION_PERCENTILE))
    print(f"  TRAIN-only (2019-09-08 -> 2021-09-08) {EXCLUSION_PERCENTILE}th percentile of "
          f"BTC {RET_WINDOW_MIN}min return: {threshold*100:.3f}%  (n_train={len(train_slice)})")

    trades = pd.read_csv(BASELINE_TRADES, parse_dates=["entry_time", "exit_time"])
    trades = trades.sort_values("entry_time")

    # Attach btc_ret_15min at each trade's entry_time via merge_asof (backward, causal).
    btc_feat = btc_ret_15min.rename("btc_ret_15min").to_frame()
    merged = pd.merge_asof(trades, btc_feat, left_on="entry_time", right_index=True, direction="backward")
    n_no_btc_data = int(merged["btc_ret_15min"].isna().sum())
    print(f"  Trades without a usable btc_ret_15min value (entry_time >= BTC's own HOLDOUT_START, "
          f"correctly left un-filterable rather than reading forbidden data): {n_no_btc_data}")

    excluded_mask = merged["btc_ret_15min"] < threshold
    excluded_mask = excluded_mask.fillna(False)  # NaN (post-BTC-holdout trades) => not excluded, conservative
    print(f"\n  Trades excluded by the acute-shock filter: {excluded_mask.sum()} of {len(merged)} "
          f"({excluded_mask.sum()/len(merged)*100:.1f}%)")

    # Load the enriched log (has exit_reason) to check what KIND of trades are being excluded.
    enriched_path = os.path.join(STRATEGY_A_DIR, "enriched_trade_log.csv")
    if os.path.exists(enriched_path):
        enriched = pd.read_csv(enriched_path, parse_dates=["entry_time", "exit_time"])
        exit_reason_map = enriched.set_index(["symbol", "entry_time", "exit_time"])["exit_reason"]
        merged_idx = merged.set_index(["symbol", "entry_time", "exit_time"])
        merged_idx["exit_reason"] = merged_idx.index.map(exit_reason_map)
        excluded_reasons = merged_idx.loc[excluded_mask.to_numpy(), "exit_reason"].value_counts()
        print(f"\n  Composition of EXCLUDED trades by their ORIGINAL exit_reason (executed-log trades only):")
        print(excluded_reasons.to_string())

    variant_trades = trades[~excluded_mask.to_numpy()]

    def score(t, label):
        log, curve, metrics = simulate_portfolio(t, LIMITS, COSTS)
        row = {"label": label, **metrics}
        if not log.empty:
            fractions = (log["pnl"] / log["entry_equity"]).to_numpy()
            mc = bootstrap_drawdowns(fractions, n_simulations=10_000, seed=42, block_size=20)
            row["mc_p_dd_gt_30"] = mc.get("p_dd_gt_30")
        return row

    baseline_metrics = score(trades, "BASELINE (frozen)")
    variant_metrics = score(variant_trades, "VARIANT (+acute-shock filter)")

    print(f"\n  BASELINE: CAGR={baseline_metrics['cagr_pct']:.2f}%  MaxDD={baseline_metrics['max_dd_pct']:.2f}%  "
          f"Calmar={baseline_metrics['calmar']:.3f}  PF={baseline_metrics['profit_factor']:.3f}  "
          f"n={baseline_metrics['n_trades']}  MC_P(DD>30%)={(baseline_metrics.get('mc_p_dd_gt_30') or 0)*100:.1f}%")
    print(f"  VARIANT:  CAGR={variant_metrics['cagr_pct']:.2f}%  MaxDD={variant_metrics['max_dd_pct']:.2f}%  "
          f"Calmar={variant_metrics['calmar']:.3f}  PF={variant_metrics['profit_factor']:.3f}  "
          f"n={variant_metrics['n_trades']}  MC_P(DD>30%)={(variant_metrics.get('mc_p_dd_gt_30') or 0)*100:.1f}%")

    d_cagr = variant_metrics["cagr_pct"] - baseline_metrics["cagr_pct"]
    d_dd = variant_metrics["max_dd_pct"] - baseline_metrics["max_dd_pct"]
    d_calmar = variant_metrics["calmar"] - baseline_metrics["calmar"]
    print(f"\n  DELTA: CAGR={d_cagr:+.2f}pp  MaxDD={d_dd:+.2f}pp  Calmar={d_calmar:+.3f}")

    out = pd.DataFrame([baseline_metrics, variant_metrics])
    out_path = os.path.join(STRATEGY_A_DIR, "experiment_acute_shock_filter_results.csv")
    out.to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    print("\n" + "=" * 100)
    print("  PRE-REGISTERED PASS/REJECT CHECK (Section 8)")
    print("=" * 100)
    if d_calmar > 0:
        print(f"  Calmar improved ({d_calmar:+.3f}) -- candidate PASS at the single-population screen stage.")
        print("  NOTE: this is a single-population SHADOW screen only, per this cycle's scope. Before ANY")
        print("  promotion to NEXT_BASELINE_CANDIDATE, per Section 9 of the mandate this MUST still clear:")
        print("  per-fold walk-forward (not yet run), stress test (not yet run), and independent reproduction.")
    else:
        print(f"  Calmar did NOT improve ({d_calmar:+.3f}) -- REJECT at the single-population screen stage.")
        print("  No further validation (walk-forward/stress) will be run on this specific threshold.")


if __name__ == "__main__":
    main()
