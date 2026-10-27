"""
scripts/phase6_tier2_short.py — does the symmetric SHORT-side signal show
the same edge as the LONG-side one (docs/phase6_tier2_results.md, next
lever #1)? Same tier 2 random forest, same features, mirrored label
(quant_bot.features.build.build_labels(direction='short')), maker-cost
assumption (the lever that got long-side closest to breakeven).

Usage:
    python scripts/phase6_tier2_short.py --horizon 30
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss

from quant_bot.config import COST_THRESHOLD_PCT, RISK_PCT_PER_TRADE
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate, buy_and_hold, MAKER_COST_PCT
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--thresholds", nargs="+", type=float, default=[0.5, 0.55, 0.6, 0.65])
    args = parser.parse_args()

    print(f"SHORT-side signal, maker cost round-trip = {MAKER_COST_PCT*100:.3f}%\n")
    print("=" * 64 + "\n  TRAIN\n" + "=" * 64)
    train_feats, train_labels = {}, {}
    for symbol in args.symbols:
        df = load_split(symbol, "train")
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], args.horizon, COST_THRESHOLD_PCT, direction="short")

    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    print(f"Short label positive rate: {y_train.mean()*100:.2f}%")

    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept, fit on {fit_n:,} rows.\n")

    print("=" * 64 + f"\n  VALIDATION — horizon={args.horizon}min, SHORT signal\n" + "=" * 64)
    for symbol in args.symbols:
        df = load_split(symbol, "validation")
        feats = build_feature_matrix(df)
        label = build_labels(df["close"], args.horizon, COST_THRESHOLD_PCT, direction="short")
        close = df["close"]
        proba = model.predict_proba(feats)
        valid = proba.notna() & label.notna()
        auc = roc_auc_score(label[valid], proba[valid])
        bh = buy_and_hold(close)

        print(f"\n--- {symbol} ---")
        print(f"AUC: {auc:.4f} (0.5=random) | proba range: [{proba[valid].min():.3f}, "
              f"{proba[valid].max():.3f}] mean={proba[valid].mean():.3f}")
        print(f"Buy & hold: {bh['total_return_pct']:+.2f}%")

        header = f"{'threshold':>10}{'n_trades':>10}{'win%':>8}{'PF':>8}{'total_ret%':>12}{'reliable?':>10}"
        print(header)
        print("-" * len(header))
        for thresh in args.thresholds:
            m = simulate(close, proba, args.horizon, thresh, capital=10_000.0,
                         risk_pct=RISK_PCT_PER_TRADE, cost_pct=MAKER_COST_PCT, direction="short")
            if m.get("n_trades", 0) == 0:
                print(f"{thresh:>10.2f}{'(no trades)':>10}")
                continue
            reliable = "n>100" if m["n_trades"] > 100 else "n<100 !!"
            print(f"{thresh:>10.2f}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
                  f"{m['profit_factor']:>8.3f}{m['total_return_pct']:>12.2f}{reliable:>10}")


if __name__ == "__main__":
    main()
