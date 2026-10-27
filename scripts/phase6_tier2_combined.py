"""
scripts/phase6_tier2_combined.py — combine the long and short tier-2 signals
per symbol (one position at a time across both directions): each showed
individually near breakeven with maker costs (docs/phase6_tier2_results.md
long, phase6_tier2_short.py output for short — BTC long 0.973 @ n=214, ETH
short 1.020 @ n=285). Does combining them get a reliable, adequately-sampled
edge without needing new discovered signal?

Usage:
    python scripts/phase6_tier2_combined.py --horizon 30
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, RISK_PCT_PER_TRADE
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate_combined, buy_and_hold, MAKER_COST_PCT
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def fit_direction(symbols, horizon, direction):
    feats, labels = {}, {}
    for symbol in symbols:
        df = load_split(symbol, "train", verbose=False)
        feats[symbol] = build_feature_matrix(df)
        labels[symbol] = build_labels(df["close"], horizon, COST_THRESHOLD_PCT, direction=direction)
    X = pd.concat(feats.values(), ignore_index=True)
    y = pd.concat(labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X, y, corr_threshold=0.9)
    fit_n = min(250_000, len(X))
    fit_idx = X.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X.loc[fit_idx], y.loc[fit_idx])
    return model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--long-threshold", type=float, default=0.60)
    parser.add_argument("--short-threshold", type=float, default=0.60)
    args = parser.parse_args()

    print(f"Combined long+short, maker cost = {MAKER_COST_PCT*100:.3f}%, "
          f"long_threshold={args.long_threshold}, short_threshold={args.short_threshold}\n")

    print("Fitting LONG model...")
    long_model = fit_direction(args.symbols, args.horizon, "long")
    print("Fitting SHORT model...")
    short_model = fit_direction(args.symbols, args.horizon, "short")

    print("\n" + "=" * 64 + f"\n  VALIDATION — horizon={args.horizon}min, combined\n" + "=" * 64)
    for symbol in args.symbols:
        df = load_split(symbol, "validation")
        feats = build_feature_matrix(df)
        close = df["close"]
        long_proba = long_model.predict_proba(feats)
        short_proba = short_model.predict_proba(feats)
        bh = buy_and_hold(close)

        m = simulate_combined(close, long_proba, short_proba, args.horizon,
                               args.long_threshold, args.short_threshold,
                               capital=10_000.0, risk_pct=RISK_PCT_PER_TRADE, cost_pct=MAKER_COST_PCT)

        print(f"\n--- {symbol} ---")
        print(f"Buy & hold: {bh['total_return_pct']:+.2f}%")
        if m.get("n_trades", 0) == 0:
            print("No trades.")
            continue
        reliable = "n>100 (reliable)" if m["n_trades"] > 100 else "n<100 !! DO NOT TRUST"
        print(f"n_trades={m['n_trades']} ({m['n_long']} long / {m['n_short']} short) [{reliable}]")
        print(f"win_rate={m['win_rate_pct']:.1f}% | PF={m['profit_factor']:.3f} | "
              f"total_return={m['total_return_pct']:+.2f}% | max_DD={m['max_drawdown_pct']:.2f}% | "
              f"sharpe~={m['sharpe_like']:.4f}")
        beats = "YES" if m["total_return_pct"] > bh["total_return_pct"] else "no"
        print(f"Beats buy & hold: {beats}")


if __name__ == "__main__":
    main()
