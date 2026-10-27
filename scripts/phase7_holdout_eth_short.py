"""
scripts/phase7_holdout_eth_short.py — the second ONE-TIME holdout look this
project has spent (SPEC.md section 8: "touched exactly once, after
everything else is frozen"). First one (tier 1, docs/phase6_7_results.md)
did not survive holdout. This is a materially different, well-motivated
configuration, pre-registered in docs/phase6_tier3_results.md BEFORE
running this script:

  - symbol: ETHUSDT only (BTC showed no edge under any tier-3 configuration
    tried, docs/phase6_tier3_results.md — not worth spending holdout on)
  - model: Tier3GradientBoostSignal, regression target, horizon=30min
  - direction: SHORT only (the side that showed the pattern)
  - cost: maker (0.06% round trip)
  - thresholds: 1.5x, 1.75x, 2.5x, 3.0x maker cost — pre-registered from
    the VALIDATION sweep in docs/phase6_tier3_results.md, all four of which
    showed PF>1 with n>100 there

None of these get adjusted after seeing HOLDOUT. If none clear breakeven
here, the honest conclusion is this doesn't generalize either, full stop —
not a cue to search further thresholds against this holdout.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import RISK_PCT_PER_TRADE
from quant_bot.features.build import build_feature_matrix, build_regression_label
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate, buy_and_hold, MAKER_COST_PCT
from quant_bot.signal.model import Tier3GradientBoostSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOLS_FOR_TRAINING = ["BTCUSDT", "ETHUSDT"]  # train on both, as every prior tier did
HOLDOUT_SYMBOL = "ETHUSDT"
HORIZON_MIN = 30
THRESHOLD_MULTIPLIERS = [1.5, 1.75, 2.5, 3.0]  # pre-registered, see docstring


def main():
    print("=" * 64 + "\n  FREEZE: train tier-3 regression model on TRAIN\n" + "=" * 64)
    train_feats, train_labels = {}, {}
    for symbol in SYMBOLS_FOR_TRAINING:
        df = load_split(symbol, "train")
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_regression_label(df["close"], HORIZON_MIN)

    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9, regression=True)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier3GradientBoostSignal(kept).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"Model frozen: {len(kept)} features, horizon={HORIZON_MIN}min, "
          f"direction=SHORT, thresholds(x maker cost)={THRESHOLD_MULTIPLIERS}\n")

    print("=" * 64 + f"\n  HOLDOUT ({HOLDOUT_SYMBOL}) — touched once, starting now\n" + "=" * 64)
    df = load_split(HOLDOUT_SYMBOL, "holdout")
    feats = build_feature_matrix(df)
    close = df["close"]
    pred = model.predict(feats)
    bh = buy_and_hold(close)

    print(f"\nBuy & hold: {bh['total_return_pct']:+.2f}% "
          f"(final equity ${bh['final_equity']:,.0f}, max DD {bh['max_drawdown_pct']:.2f}%)")

    header = (f"{'mult':>6}{'thresh%':>10}{'n_trades':>10}{'win%':>8}{'PF':>8}"
              f"{'total_ret%':>12}{'max_DD%':>10}{'sharpe~':>9}{'beats_B&H':>11}")
    print(header)
    print("-" * len(header))
    for k in THRESHOLD_MULTIPLIERS:
        thresh = k * MAKER_COST_PCT
        m = simulate(close, -pred, HORIZON_MIN, thresh, capital=10_000.0,
                     risk_pct=RISK_PCT_PER_TRADE, cost_pct=MAKER_COST_PCT, direction="short")
        if m.get("n_trades", 0) == 0:
            print(f"{k:>6.2f}{thresh*100:>10.3f}{'(no trades)':>10}")
            continue
        beats = "YES" if m["total_return_pct"] > bh["total_return_pct"] else "no"
        reliable = "" if m["n_trades"] > 100 else "  (n<100, DO NOT TRUST)"
        print(f"{k:>6.2f}{thresh*100:>10.3f}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
              f"{m['profit_factor']:>8.3f}{m['total_return_pct']:>12.2f}"
              f"{m['max_drawdown_pct']:>10.2f}{m['sharpe_like']:>9.4f}{beats:>11}{reliable}")

    print("\n" + "=" * 64)
    print("This is the one HOLDOUT read for this configuration. No further")
    print("threshold search against this holdout regardless of outcome.")
    print("=" * 64)


if __name__ == "__main__":
    main()
