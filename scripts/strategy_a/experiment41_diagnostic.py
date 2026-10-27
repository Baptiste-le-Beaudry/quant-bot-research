"""scripts/strategy_a/experiment41_diagnostic.py — STRATEGY_ID = A,
Experiment 41, Steps 2-4: attach shock_breadth to Strategy A's own
CANDIDATE trade population (not all market minutes -- the Experiment 40
lesson), calibrate the GATE threshold on the PRE-2024 conditional
population only, bucket POST-2024 trades by shock_breadth, and verify
the mechanism against the known protective-stop clusters from the
alpha decomposition report. SHADOW/ANALYTICAL ONLY.

Usage:
    python scripts/strategy_a/experiment41_diagnostic.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
STRATEGY_A_DIR = os.path.join(DOCS, "strategy_a")
BASELINE_TRADES = os.path.join(DOCS, "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv")
SHOCK_BREADTH_PATH = os.path.join(STRATEGY_A_DIR, "shock_breadth_1min.csv")
ENRICHED_LOG_PATH = os.path.join(STRATEGY_A_DIR, "enriched_trade_log.csv")
CALIBRATION_CUTOFF = pd.Timestamp("2024-01-01", tz="UTC")
GATE_PERCENTILE = 90  # conditional-population percentile for the "extreme breadth" gate


def main():
    print("=" * 100)
    print("  STRATEGY A -- Experiment 41 Steps 2-4: conditional calibration + diagnostic + mechanism check")
    print("=" * 100)

    shock = pd.read_csv(SHOCK_BREADTH_PATH, index_col=0, parse_dates=True)["shock_breadth"]
    trades = pd.read_csv(BASELINE_TRADES, parse_dates=["entry_time", "exit_time"]).sort_values("entry_time")

    # Attach shock_breadth AT each candidate trade's own entry_time (causal, backward, 1-min data
    # so nearest available minute at/before entry_time).
    merged = pd.merge_asof(trades, shock.rename("shock_breadth").to_frame(),
                            left_on="entry_time", right_index=True, direction="backward")
    n_missing = int(merged["shock_breadth"].isna().sum())
    print(f"  Candidate trades with a usable shock_breadth value: {len(merged)-n_missing}/{len(merged)} "
          f"({n_missing} missing -- investigate if >0)")

    # STEP 2: conditional population = Strategy A's OWN candidate entries, PRE-2024 only (the
    # correction for Experiment 40's mistake of using the unconditional market distribution).
    pre_cal = merged[merged["entry_time"] < CALIBRATION_CUTOFF]
    gate_threshold = float(np.percentile(pre_cal["shock_breadth"].dropna(), GATE_PERCENTILE))
    print(f"\n  STEP 2 -- CONDITIONAL population for gate calibration: Strategy A's own PRE-2024 candidate "
          f"entries (n={len(pre_cal)}), NOT all market minutes.")
    print(f"  Gate threshold (p{GATE_PERCENTILE} of shock_breadth AT Strategy A's own candidate entries): "
          f"{gate_threshold:.4f}")
    print(f"  For comparison, unconditional p{GATE_PERCENTILE} of shock_breadth over ALL market minutes "
          f"(pre-2024, NOT used for calibration, printed only to show the difference Experiment 40 missed): "
          f"{np.percentile(shock[shock.index < CALIBRATION_CUTOFF].dropna(), GATE_PERCENTILE):.4f}")

    # STEP 3: diagnostic bucket table on POST-2024 trades (genuine forward-looking evaluation slice).
    post = merged[merged["entry_time"] >= CALIBRATION_CUTOFF].copy()
    print(f"\n  STEP 3 -- DIAGNOSTIC: bucketing POST-2024 candidate trades (n={len(post)}) by shock_breadth")

    if os.path.exists(ENRICHED_LOG_PATH):
        enriched = pd.read_csv(ENRICHED_LOG_PATH, parse_dates=["entry_time", "exit_time"])
        exit_map = enriched.set_index(["symbol", "entry_time", "exit_time"])["exit_reason"]
        pnl_map = enriched.set_index(["symbol", "entry_time", "exit_time"])["pnl"]
        post = post.set_index(["symbol", "entry_time", "exit_time"], drop=False)
        post["exit_reason"] = post.index.map(exit_map)
        post["pnl"] = post.index.map(pnl_map)
        post = post.reset_index(drop=True)
        post_executed = post.dropna(subset=["pnl"])
        print(f"  ({len(post_executed)}/{len(post)} POST-2024 candidates were actually executed by the risk "
              f"engine and have a known pnl/exit_reason -- bucket table uses this executed subset)")
    else:
        raise SystemExit("Run decompose_trades.py first to produce enriched_trade_log.csv")

    post_executed["breadth_bucket"] = pd.cut(
        post_executed["shock_breadth"],
        bins=[-0.01, 0.0, 0.111, 0.222, 0.333, 1.01],
        labels=["0 (none)", "0-11%", "11-22%", "22-33%", "33%+"])

    rows = []
    for name, sub in post_executed.groupby("breadth_bucket", observed=True):
        wins, losses = sub[sub["pnl"] > 0]["pnl"], sub[sub["pnl"] <= 0]["pnl"]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else np.inf
        n_stop = int((sub["exit_reason"] == "PROTECTIVE_STOP").sum())
        n_trail = int((sub["exit_reason"] == "TRAILING_STOP").sum())
        rows.append({
            "breadth_bucket": name, "n": len(sub), "pf": round(pf, 3),
            "expectancy_$": round(float(sub["pnl"].mean()), 2), "total_pnl_$": round(float(sub["pnl"].sum()), 2),
            "protective_stop_rate_pct": round(n_stop / len(sub) * 100, 1),
            "trailing_stop_rate_pct": round(n_trail / len(sub) * 100, 1),
            "avg_win_$": round(float(wins.mean()) if len(wins) else 0.0, 2),
            "avg_loss_$": round(float(losses.mean()) if len(losses) else 0.0, 2),
        })
    bucket_table = pd.DataFrame(rows)
    print(bucket_table.to_string(index=False))
    bucket_table.to_csv(os.path.join(STRATEGY_A_DIR, "experiment41_shock_breadth_buckets.csv"), index=False)

    # Explicit LOW/NORMAL vs EXTREME comparison
    low_normal = post_executed[post_executed["shock_breadth"] < gate_threshold]
    extreme = post_executed[post_executed["shock_breadth"] >= gate_threshold]
    print(f"\n  LOW/NORMAL breadth (< gate {gate_threshold:.3f}): n={len(low_normal)}  "
          f"protective_stop_rate={((low_normal['exit_reason']=='PROTECTIVE_STOP').mean()*100):.1f}%  "
          f"PF={(low_normal[low_normal.pnl>0].pnl.sum()/-low_normal[low_normal.pnl<=0].pnl.sum() if low_normal[low_normal.pnl<=0].pnl.sum()<0 else np.inf):.3f}  "
          f"total_pnl={low_normal['pnl'].sum():,.0f}$")
    print(f"  EXTREME breadth (>= gate {gate_threshold:.3f}): n={len(extreme)}  "
          f"protective_stop_rate={((extreme['exit_reason']=='PROTECTIVE_STOP').mean()*100):.1f}%  "
          f"PF={(extreme[extreme.pnl>0].pnl.sum()/-extreme[extreme.pnl<=0].pnl.sum() if extreme[extreme.pnl<=0].pnl.sum()<0 else np.inf):.3f}  "
          f"total_pnl={extreme['pnl'].sum():,.0f}$")

    # STEP 4: mechanism verification against the KNOWN clusters from the alpha decomposition report.
    print(f"\n  STEP 4 -- MECHANISM VERIFICATION: known protective-stop clusters vs shock_breadth AT that time")
    known_clusters = ["2025-02-03", "2025-02-25", "2024-08-05", "2024-03-05", "2022-11-08", "2024-12-09", "2025-01-19"]
    for date_str in known_clusters:
        day_stops = post_executed[(post_executed["entry_time"].dt.date.astype(str) == date_str) &
                                   (post_executed["exit_reason"] == "PROTECTIVE_STOP")]
        if len(day_stops) == 0:
            # check pre-2024 trades too (merged has shock_breadth for all)
            day_stops = merged[(merged["entry_time"].dt.date.astype(str) == date_str)]
        if len(day_stops):
            print(f"  {date_str}: n_stops_that_day={len(day_stops)}  "
                  f"shock_breadth range=[{day_stops['shock_breadth'].min():.3f}, {day_stops['shock_breadth'].max():.3f}]  "
                  f"mean={day_stops['shock_breadth'].mean():.3f}  (gate={gate_threshold:.3f})")
        else:
            print(f"  {date_str}: no matching trades found in this population")

    out_path = os.path.join(STRATEGY_A_DIR, "experiment41_gate_threshold.txt")
    with open(out_path, "w") as f:
        f.write(str(gate_threshold))
    print(f"\nGate threshold saved -> {out_path}")


if __name__ == "__main__":
    main()
