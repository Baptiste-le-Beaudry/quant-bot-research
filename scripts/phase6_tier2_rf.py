"""
scripts/phase6_tier2_rf.py — Phase 6, tier 2: random forest. SPEC.md section
7's promotion rule: must clear a REAL, adequately-sampled edge over tier 1's
result (docs/phase6_7_results.md — tier 1 didn't survive HOLDOUT).

Uses quant_bot.backtest.engine (one-position-at-a-time, compounding) for
the VALIDATION sweep this time, not the naive screening tool — after
Phase 7's lesson about trade counts collapsing under realistic constraints,
better to see that up front on VALIDATION than get surprised again on
HOLDOUT.

Usage:
    python scripts/phase6_tier2_rf.py --horizon 30
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
from quant_bot.backtest.engine import simulate, buy_and_hold, COST_PCT, MAKER_COST_PCT
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def build_xy(symbols, split, horizon):
    feats, labels, closes = {}, {}, {}
    for symbol in symbols:
        df = load_split(symbol, split)
        feats[symbol] = build_feature_matrix(df)
        labels[symbol] = build_labels(df["close"], horizon, COST_THRESHOLD_PCT)
        closes[symbol] = df["close"]
    return feats, labels, closes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--thresholds", nargs="+", type=float, default=[0.5, 0.55, 0.6, 0.65, 0.7])
    parser.add_argument("--maker", action="store_true",
                         help=f"Use limit/maker round-trip cost ({MAKER_COST_PCT*100:.3f}%%) instead of "
                              f"market/taker ({COST_PCT*100:.3f}%%) -- tests whether cost, not model "
                              f"capacity, is the binding constraint (docs/phase6_7_results.md).")
    args = parser.parse_args()
    cost_pct = MAKER_COST_PCT if args.maker else COST_PCT

    print(f"Cost model: {'MAKER/limit' if args.maker else 'TAKER/market'} "
          f"round-trip = {cost_pct*100:.3f}%\n")
    print("=" * 64 + "\n  TRAIN: feature selection + model fit (tier 2: random forest)\n" + "=" * 64)
    train_feats, train_labels, _ = build_xy(args.symbols, "train", args.horizon)
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)

    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)

    # Subsample the fit itself, not just the MI screen: this environment has
    # been killing multi-minute background computations (repeatedly, at
    # varying stages — looks like external sleep/wake, not a code issue).
    # 250k rows is still ample for a depth-5, min-leaf-200 forest and cuts
    # fit time roughly 5x vs the full 1.26M-row TRAIN set.
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"\n{len(kept)} features kept. Fit on {fit_n:,} subsampled rows, 100 trees.")
    print("Feature importance (Gini, random forest):")
    for feat, imp in model.feature_importance().items():
        print(f"  {feat:<24} {imp:.4f}")

    print("\n" + "=" * 64 + f"\n  VALIDATION — horizon={args.horizon}min, real engine (one position at a time)\n" + "=" * 64)
    val_feats, val_labels, val_close = build_xy(args.symbols, "validation", args.horizon)

    for symbol in args.symbols:
        X_val, y_val, close = val_feats[symbol], val_labels[symbol], val_close[symbol]
        proba = model.predict_proba(X_val)
        valid = proba.notna() & y_val.notna()
        auc = roc_auc_score(y_val[valid], proba[valid])
        ll = log_loss(y_val[valid], proba[valid])
        bh = buy_and_hold(close)

        print(f"\n--- {symbol} ---")
        print(f"AUC: {auc:.4f} (0.5 = random) | log-loss: {ll:.4f} | "
              f"proba range: [{proba[valid].min():.3f}, {proba[valid].max():.3f}] mean={proba[valid].mean():.3f}")
        print(f"Buy & hold: {bh['total_return_pct']:+.2f}% (max DD {bh['max_drawdown_pct']:.2f}%)")

        header = (f"{'threshold':>10}{'n_trades':>10}{'win%':>8}{'PF':>8}"
                  f"{'total_ret%':>12}{'max_DD%':>10}{'sharpe~':>9}{'reliable?':>10}")
        print(header)
        print("-" * len(header))
        for thresh in args.thresholds:
            m = simulate(close, proba, args.horizon, thresh, capital=10_000.0,
                         risk_pct=RISK_PCT_PER_TRADE, cost_pct=cost_pct)
            if m.get("n_trades", 0) == 0:
                print(f"{thresh:>10.2f}{'(no trades)':>10}")
                continue
            reliable = "n>100" if m["n_trades"] > 100 else "n<100 !!"
            print(f"{thresh:>10.2f}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
                  f"{m['profit_factor']:>8.3f}{m['total_return_pct']:>12.2f}"
                  f"{m['max_drawdown_pct']:>10.2f}{m['sharpe_like']:>9.4f}{reliable:>10}")


if __name__ == "__main__":
    main()
