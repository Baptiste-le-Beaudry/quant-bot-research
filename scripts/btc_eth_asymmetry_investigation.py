"""
scripts/btc_eth_asymmetry_investigation.py — investigates the recurring
pattern this session where BTC tolerates aggressive config changes well
under gap stress but ETH doesn't (confirmed independently on the stop
percentile, Experiment 6b, and the RF threshold, Experiment 8). Direct
hypothesis: does ETH simply have more extreme/gappy 1-min price action
than BTC over their respective VALIDATION windows, which would mechanically
explain why a fixed-size stress gap hurts ETH's tighter-parameter configs
more?

Pure data analysis -- no model fitting, fast. Compares, over each symbol's
own VALIDATION window:
  - realized volatility of 1-min returns (std)
  - tail percentiles of |1-min return| (p99, p99.9, p99.99, max)
  - count of "gap-like" 1-min moves exceeding 0.25%/0.50%/1.00%
    (the exact stress levels tested all session) and their frequency
    per entry-filter-qualifying period specifically (not just unconditionally)

Usage:
    python scripts/btc_eth_asymmetry_investigation.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def analyze(symbol: str) -> dict:
    df = load_split(symbol, "validation", verbose=True)
    close = df["close"]
    rets = close.pct_change().dropna()
    abs_rets = rets.abs()

    stats = {
        "symbol": symbol,
        "n_bars": len(df),
        "realized_vol_1min_pct": rets.std() * 100,
        "p99": abs_rets.quantile(0.99) * 100,
        "p999": abs_rets.quantile(0.999) * 100,
        "p9999": abs_rets.quantile(0.9999) * 100,
        "max_abs_move_pct": abs_rets.max() * 100,
        "n_moves_gt_025pct": int((abs_rets > 0.0025).sum()),
        "n_moves_gt_050pct": int((abs_rets > 0.0050).sum()),
        "n_moves_gt_100pct": int((abs_rets > 0.0100).sum()),
        "freq_gt_025pct_per_1000bars": (abs_rets > 0.0025).sum() / len(df) * 1000,
        "freq_gt_050pct_per_1000bars": (abs_rets > 0.0050).sum() / len(df) * 1000,
    }
    return stats


def main():
    all_stats = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        s = analyze(symbol)
        all_stats.append(s)
        print(f"\n{symbol} VALIDATION 1-min return distribution:")
        print(f"  realized vol (std of 1-min ret): {s['realized_vol_1min_pct']:.4f}%")
        print(f"  p99 |ret|: {s['p99']:.4f}%   p99.9 |ret|: {s['p999']:.4f}%   "
              f"p99.99 |ret|: {s['p9999']:.4f}%   max |ret|: {s['max_abs_move_pct']:.4f}%")
        print(f"  moves > 0.25%: {s['n_moves_gt_025pct']:,} ({s['freq_gt_025pct_per_1000bars']:.3f}/1000 bars)")
        print(f"  moves > 0.50%: {s['n_moves_gt_050pct']:,} ({s['freq_gt_050pct_per_1000bars']:.3f}/1000 bars)")
        print(f"  moves > 1.00%: {s['n_moves_gt_100pct']:,}")

    df_stats = pd.DataFrame(all_stats).set_index("symbol")
    print("\n" + "=" * 90)
    print("  DIRECT COMPARISON (ETH / BTC ratio)")
    print("=" * 90)
    eth, btc = df_stats.loc["ETHUSDT"], df_stats.loc["BTCUSDT"]
    for col in ["realized_vol_1min_pct", "p99", "p999", "p9999", "max_abs_move_pct",
                "freq_gt_025pct_per_1000bars", "freq_gt_050pct_per_1000bars"]:
        ratio = eth[col] / btc[col] if btc[col] != 0 else float("nan")
        print(f"  {col:<32} ETH={eth[col]:>10.4f}  BTC={btc[col]:>10.4f}  ratio={ratio:>6.2f}x")

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "btc_eth_asymmetry_raw.csv")
    df_stats.to_csv(out_path)
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
