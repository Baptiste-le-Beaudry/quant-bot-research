"""
scripts/phase6_tier1_logreg.py — Phase 6, tier 1: does a simple logistic
regression, on the Phase 4 redundancy-pruned features, produce a validated
out-of-sample edge? Fit on TRAIN, every number reported here is on
VALIDATION (never touched before this script) — SPEC.md section 8.

This is the actual test of whether combining the weak individual features
from Phase 4 (docs/phase4_results.md) into a model beats what any of them
showed alone.

Usage:
    python scripts/phase6_tier1_logreg.py --horizon 30
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss

from quant_bot.config import COST_THRESHOLD_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.simple_engine import evaluate_signal, buy_and_hold_return_pct, null_baseline
from quant_bot.signal.model import Tier1LogisticSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def build_xy(symbols, split, horizon):
    feats_by_symbol, label_by_symbol, close_by_symbol = {}, {}, {}
    for symbol in symbols:
        df = load_split(symbol, split)
        feats_by_symbol[symbol] = build_feature_matrix(df)
        label_by_symbol[symbol] = build_labels(df["close"], horizon, COST_THRESHOLD_PCT)
        close_by_symbol[symbol] = df["close"]
    return feats_by_symbol, label_by_symbol, close_by_symbol


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--thresholds", nargs="+", type=float, default=[0.5, 0.55, 0.6, 0.65])
    args = parser.parse_args()

    print("=" * 64 + "\n  TRAIN: feature selection + model fit\n" + "=" * 64)
    train_feats, train_labels, _ = build_xy(args.symbols, "train", args.horizon)
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)

    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    print(f"\n{len(kept)} features kept (recomputed on TRAIN only, matches docs/redundancy_report.md "
          f"if horizon/symbols match): {kept}\n")

    model = Tier1LogisticSignal(kept).fit(X_train, y_train)
    print("Feature importance (|coef|, logistic regression):")
    for feat, imp in model.feature_importance().items():
        print(f"  {feat:<24} {imp:.4f}")

    print("\n" + "=" * 64 + f"\n  VALIDATION (never used above) — horizon={args.horizon}min\n" + "=" * 64)
    val_feats, val_labels, val_close = build_xy(args.symbols, "validation", args.horizon)

    for symbol in args.symbols:
        X_val, y_val, close = val_feats[symbol], val_labels[symbol], val_close[symbol]
        proba = model.predict_proba(X_val)
        valid = proba.notna() & y_val.notna()

        auc = roc_auc_score(y_val[valid], proba[valid])
        ll = log_loss(y_val[valid], proba[valid])
        print(f"\n--- {symbol} ---")
        print(f"AUC: {auc:.4f} (0.5 = random) | log-loss: {ll:.4f} | "
              f"proba range: [{proba[valid].min():.3f}, {proba[valid].max():.3f}] "
              f"mean={proba[valid].mean():.3f}")

        bh = buy_and_hold_return_pct(close)
        print(f"Buy & hold over VALIDATION: {bh:+.2f}%")

        header = f"{'threshold':>10}{'n_trades':>10}{'win%':>8}{'PF':>8}{'expectancy%':>13}{'naive_ret%':>12}"
        print(header)
        print("-" * len(header))
        for thresh in args.thresholds:
            signal = pd.Series(0, index=close.index)
            signal[proba > thresh] = 1
            m = evaluate_signal(close, signal, args.horizon)
            if m.get("n_trades", 0) == 0:
                print(f"{thresh:>10.2f}{'(no trades)':>10}")
                continue
            print(f"{thresh:>10.2f}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
                  f"{m['profit_factor']:>8.3f}{m['expectancy_pct']:>13.5f}{m['total_naive_return_pct']:>12.2f}")
            null = null_baseline(close, m["n_trades"], args.horizon, seed=int(thresh * 100))
            if null.get("n_trades", 0) > 0:
                print(f"{'  null':>10}{null['n_trades']:>10}{null['win_rate_pct']:>8.1f}"
                      f"{null['profit_factor']:>8.3f}{null['expectancy_pct']:>13.5f}{null['total_naive_return_pct']:>12.2f}")


if __name__ == "__main__":
    main()
