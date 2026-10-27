"""
scripts/phase6_regression.py — option 2 (docs/phase6_summary.md): predict
the raw forward return (RegressionForestSignal) instead of a binary
cost-threshold label, at the horizon that showed the best trading economics
so far (30min, docs/phase6_summary.md option-3 result — 10min had higher
AUC but worse PF because typical moves are too small relative to fixed
cost there).

Trading rule: LONG when predicted return > k * maker_cost, SHORT when
predicted return < -k * maker_cost, for a swept selectivity multiplier k —
mirrors the confidence-threshold sweep used for the classifiers, but the
threshold now has a direct, interpretable meaning (a multiple of the cost
the trade needs to clear) instead of an arbitrary probability cutoff.

Usage:
    python scripts/phase6_regression.py --horizon 30
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np

from quant_bot.config import RISK_PCT_PER_TRADE
from quant_bot.features.build import build_feature_matrix, build_regression_label
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate, buy_and_hold, MAKER_COST_PCT
from quant_bot.signal.model import RegressionForestSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--multipliers", nargs="+", type=float, default=[1.0, 1.5, 2.0, 3.0, 4.0])
    args = parser.parse_args()

    print(f"Regression target, horizon={args.horizon}min, maker cost={MAKER_COST_PCT*100:.3f}%\n")
    print("=" * 64 + "\n  TRAIN\n" + "=" * 64)

    train_feats, train_labels = {}, {}
    for symbol in args.symbols:
        df = load_split(symbol, "train")
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_regression_label(df["close"], args.horizon)

    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    print(f"Label stats: mean={y_train.mean()*100:.4f}% std={y_train.std()*100:.4f}% "
          f"(n={y_train.notna().sum():,})")

    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9, regression=True)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = RegressionForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"\n{len(kept)} features kept, fit on {fit_n:,} rows.")
    print("Feature importance:")
    for feat, imp in model.feature_importance().items():
        print(f"  {feat:<24} {imp:.4f}")

    print("\n" + "=" * 64 + f"\n  VALIDATION — horizon={args.horizon}min\n" + "=" * 64)
    for symbol in args.symbols:
        df = load_split(symbol, "validation")
        feats = build_feature_matrix(df)
        close = df["close"]
        actual = build_regression_label(close, args.horizon)
        pred = model.predict(feats)

        valid = pred.notna() & actual.notna()
        corr = np.corrcoef(pred[valid], actual[valid])[0, 1]
        bh = buy_and_hold(close)

        print(f"\n--- {symbol} ---")
        print(f"corr(predicted, actual forward return): {corr:.4f} | "
              f"pred range: [{pred[valid].min()*100:.3f}%, {pred[valid].max()*100:.3f}%]")
        print(f"Buy & hold: {bh['total_return_pct']:+.2f}%")

        header = f"{'mult':>6}{'thresh%':>10}{'side':>7}{'n_trades':>10}{'win%':>8}{'PF':>8}{'total_ret%':>12}{'reliable?':>10}"
        print(header)
        print("-" * len(header))
        for k in args.multipliers:
            thresh = k * MAKER_COST_PCT
            for side, proba, direction in [
                ("LONG", pred, "long"),
                ("SHORT", -pred, "short"),
            ]:
                m = simulate(close, proba, args.horizon, thresh, capital=10_000.0,
                             risk_pct=RISK_PCT_PER_TRADE, cost_pct=MAKER_COST_PCT, direction=direction)
                if m.get("n_trades", 0) == 0:
                    print(f"{k:>6.1f}{thresh*100:>10.3f}{side:>7}{'(no trades)':>10}")
                    continue
                reliable = "n>100" if m["n_trades"] > 100 else "n<100 !!"
                print(f"{k:>6.1f}{thresh*100:>10.3f}{side:>7}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
                      f"{m['profit_factor']:>8.3f}{m['total_return_pct']:>12.2f}{reliable:>10}")


if __name__ == "__main__":
    main()
