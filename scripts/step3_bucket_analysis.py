"""
scripts/step3_bucket_analysis.py — Étape 3: where does the edge actually
live? Buckets the 131-trade diagnostic dataset (docs/step2_trade_diagnostic.csv,
BASELINE_CANDIDATE_V2) along every dimension the plan asks for: signal
probability, volatility, trend, range position, MFE/MAE, hour of day,
holding time, BTC cross-asset regime.

HONEST CAVEAT, per the plan's own Étape 4 n-size rule: total n=131 (89 ETH
+ 42 BTC) split across 3-5 buckets per dimension puts MOST cells at n<20
("exploration only") or n<50 ("interesting but not enough to validate a
rule"). Every table below prints n alongside the stat -- read the n before
the number, not after.

Usage:
    python scripts/step3_bucket_analysis.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "step2_trade_diagnostic.csv")


def reliability(n: int) -> str:
    if n < 20:
        return "EXPLORATION ONLY"
    if n < 50:
        return "interesting, not enough"
    if n < 100:
        return "starting to be usable"
    return "exploitable"


def bucket_report(df: pd.DataFrame, col: str, bins, labels, title: str):
    print(f"\n-- {title} --")
    cats = pd.cut(df[col], bins=bins, labels=labels, include_lowest=True)
    g = df.groupby(cats, observed=True)["net_return"]
    for name, sub in g:
        n = len(sub)
        if n == 0:
            continue
        win = (sub > 0).mean() * 100
        avg = sub.mean() * 100
        wins, losses = sub[sub > 0], sub[sub <= 0]
        pf = wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf")
        print(f"  {str(name):<14} n={n:>4} win%={win:>5.1f} avg_ret={avg:>+7.4f}% "
              f"PF={pf:>7.3f}  [{reliability(n)}]")


def main():
    df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"])
    print(f"Loaded {len(df)} trades ({df['symbol'].value_counts().to_dict()})\n")
    print("=" * 100)
    print("  OVERALL (all symbols pooled)")
    print("=" * 100)
    n = len(df)
    win = (df["net_return"] > 0).mean() * 100
    print(f"n={n} win%={win:.1f} avg_net_return={df['net_return'].mean()*100:+.4f}%  [{reliability(n)}]")

    bucket_report(df, "signal_probability", [0.75, 0.80, 0.85, 0.90, 0.95, 1.0],
                  ["0.75-0.80", "0.80-0.85", "0.85-0.90", "0.90-0.95", "0.95+"],
                  "By signal probability")

    bucket_report(df, "realized_vol_30", df["realized_vol_30"].quantile([0, .25, .5, .75, 1.0]).values,
                  ["Q1 low vol", "Q2", "Q3", "Q4 high vol"], "By realized volatility quartile")

    bucket_report(df, "ema_slope_20", [-np.inf, -1e-9, 1e-9, np.inf],
                  ["downtrend", "flat", "uptrend"], "By local trend (ema_slope_20 sign)")

    bucket_report(df, "range_pos_60", [0, .25, .5, .75, 1.0],
                  ["near low", "low-mid", "mid-high", "near high"], "By range position at entry")

    bucket_report(df, "mfe", df["mfe"].quantile([0, .25, .5, .75, 1.0]).values,
                  ["Q1 low MFE", "Q2", "Q3", "Q4 high MFE"], "By MFE quartile")

    bucket_report(df, "mae", df["mae"].quantile([0, .25, .5, .75, 1.0]).values,
                  ["Q1 (most adverse)", "Q2", "Q3", "Q4 (least adverse)"], "By MAE quartile")

    df["hour"] = df["timestamp"].dt.hour
    bucket_report(df, "hour", [-1, 6, 12, 18, 24],
                  ["00-06 UTC", "06-12 UTC", "12-18 UTC", "18-24 UTC"], "By hour of day (UTC)")

    bucket_report(df, "holding_time_min", [0, 10, 20, 30, 50],
                  ["0-10min", "10-20min", "20-30min", "30-50min"], "By holding time")

    bucket_report(df, "btc_ret_60", df["btc_ret_60"].quantile([0, .25, .5, .75, 1.0]).values,
                  ["Q1 BTC falling", "Q2", "Q3", "Q4 BTC rising"], "By BTC cross-asset 60min return regime")

    print("\n" + "=" * 100)
    print("  MAE-quartile x MFE-quartile matrix (the split found earlier this session, re-verified on V2)")
    print("=" * 100)
    mae_q = pd.qcut(df["mae"], 4, labels=["Q1(low|mae|)", "Q2", "Q3", "Q4(high|mae|)"], duplicates="drop")
    mfe_q = pd.qcut(df["mfe"], 4, labels=["Q1(lowMFE)", "Q2", "Q3", "Q4(highMFE)"], duplicates="drop")
    tmp = pd.DataFrame({"mae_q": mae_q, "mfe_q": mfe_q, "ret": df["net_return"]})
    for (mq, fq), sub in tmp.groupby(["mae_q", "mfe_q"], observed=True):
        n = len(sub)
        if n == 0:
            continue
        print(f"  MAE={str(mq):<16} MFE={str(fq):<12} n={n:>4} win%={(sub['ret']>0).mean()*100:>5.1f} "
              f"avg_ret={sub['ret'].mean()*100:>+7.4f}%  [{reliability(n)}]")

    print("\n" + "=" * 100)
    print("  Exit reason x outcome")
    print("=" * 100)
    for reason, sub in df.groupby("exit_reason")["net_return"]:
        n = len(sub)
        print(f"  {reason:<10} n={n:>4} win%={(sub>0).mean()*100:>5.1f} avg_ret={sub.mean()*100:>+7.4f}%  "
              f"[{reliability(n)}]")


if __name__ == "__main__":
    main()
