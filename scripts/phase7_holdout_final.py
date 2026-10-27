"""
scripts/phase7_holdout_final.py — the ONE-TIME holdout evaluation (SPEC.md
section 8: "touched exactly once, after everything else is frozen").

Configuration is frozen from Phase 6 VALIDATION exploration
(scripts/phase6_tier1_logreg.py output) BEFORE this script is run:
  - model: Tier1LogisticSignal, horizon=30min, trained on TRAIN
  - thresholds: 0.75 / 0.80 / 0.85 — the three candidates that showed
    profit factor > 1 on at least one asset during the VALIDATION sweep,
    pre-registered here before looking at HOLDOUT. All three are reported
    in one run; none of this script's parameters get adjusted afterward
    based on what HOLDOUT shows — that would defeat the point of a holdout.

If this doesn't beat buy-and-hold on HOLDOUT, that's the honest answer, not
a cue to keep tuning against holdout data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, RISK_PCT_PER_TRADE
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate, buy_and_hold
from quant_bot.signal.model import Tier1LogisticSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON_MIN = 30
THRESHOLDS = [0.75, 0.80, 0.85]  # pre-registered from VALIDATION, see docstring


def main():
    print("=" * 64 + "\n  FREEZE: train on TRAIN (same as Phase 6)\n" + "=" * 64)
    train_feats, train_labels = {}, {}
    for symbol in SYMBOLS:
        df = load_split(symbol, "train")
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON_MIN, COST_THRESHOLD_PCT)

    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    model = Tier1LogisticSignal(kept).fit(X_train, y_train)
    print(f"Model frozen: {len(kept)} features, horizon={HORIZON_MIN}min, thresholds={THRESHOLDS}\n")

    print("=" * 64 + "\n  HOLDOUT — touched once, starting now\n" + "=" * 64)
    for symbol in SYMBOLS:
        df = load_split(symbol, "holdout")
        feats = build_feature_matrix(df)
        proba = model.predict_proba(feats)
        bh = buy_and_hold(df["close"])

        print(f"\n--- {symbol} HOLDOUT ---")
        print(f"Buy & hold: {bh['total_return_pct']:+.2f}%  "
              f"(final equity ${bh['final_equity']:,.0f}, max DD {bh['max_drawdown_pct']:.2f}%)")

        header = (f"{'threshold':>10}{'n_trades':>10}{'win%':>8}{'PF':>8}"
                  f"{'total_ret%':>12}{'max_DD%':>10}{'sharpe~':>9}{'sortino~':>10}{'beats_B&H':>11}")
        print(header)
        print("-" * len(header))
        for thresh in THRESHOLDS:
            m = simulate(df["close"], proba, HORIZON_MIN, thresh,
                         capital=10_000.0, risk_pct=RISK_PCT_PER_TRADE)
            if m.get("n_trades", 0) == 0:
                print(f"{thresh:>10.2f}{'(no trades)':>10}")
                continue
            beats = "YES" if m["total_return_pct"] > bh["total_return_pct"] else "no"
            print(f"{thresh:>10.2f}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
                  f"{m['profit_factor']:>8.3f}{m['total_return_pct']:>12.2f}"
                  f"{m['max_drawdown_pct']:>10.2f}{m['sharpe_like']:>9.4f}"
                  f"{m['sortino_like']:>10.4f}{beats:>11}")

    print("\n" + "=" * 64)
    print("This is the one HOLDOUT read for this model/horizon/threshold set.")
    print("If none of these beat buy & hold: the honest conclusion is tier 1")
    print("(logistic regression on this feature set) isn't there yet -- next")
    print("step is tier 2 (SPEC.md section 7), not re-running this holdout.")
    print("=" * 64)


if __name__ == "__main__":
    main()
