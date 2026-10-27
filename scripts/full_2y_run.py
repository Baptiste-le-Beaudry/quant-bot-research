"""
scripts/full_2y_run.py — what would the frozen tier-3 ETHUSDT-short
configuration (docs/phase6_tier3_results.md / phase7_holdout_eth_short.py)
have returned over the FULL 2-year dataset, run continuously?

IMPORTANT CAVEAT, printed again at runtime: the model is fit on TRAIN
(first ~14.4 months). Running it over that same period is in-sample —
those trades benefit from the model having seen that exact data during
fitting, so returns there are inflated and not a fair test. Only the
VALIDATION+HOLDOUT portion (last ~9.6 months) is genuinely out-of-sample.
Both are reported, clearly separated, so the in-sample portion can't be
mistaken for a real result.

Usage:
    python scripts/full_2y_run.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import RISK_PCT_PER_TRADE, TRAIN_FRACTION
from quant_bot.features.build import build_feature_matrix, build_regression_label
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate, buy_and_hold, MAKER_COST_PCT
from quant_bot.signal.model import Tier3GradientBoostSignal
from scripts.phase3_baseline import load_split, _load_full

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOLS_FOR_TRAINING = ["BTCUSDT", "ETHUSDT"]
TARGET_SYMBOL = "ETHUSDT"
HORIZON_MIN = 30
THRESHOLD_MULT = 1.75  # the best-sampled reliable point from the holdout test


def main():
    print("Fitting the exact frozen configuration (same as phase7_holdout_eth_short.py)...")
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
    print(f"Model frozen: {len(kept)} features, threshold={THRESHOLD_MULT}x maker cost, SHORT only\n")

    full_df = _load_full(TARGET_SYMBOL)
    n = len(full_df)
    train_end = int(n * TRAIN_FRACTION)
    split_date = full_df.index[train_end]

    feats = build_feature_matrix(full_df)
    close = full_df["close"]
    pred = model.predict(feats)
    thresh = THRESHOLD_MULT * MAKER_COST_PCT

    print("=" * 70)
    print(f"  FULL 2-YEAR RUN — {TARGET_SYMBOL} ({full_df.index[0]:%Y-%m-%d} -> {full_df.index[-1]:%Y-%m-%d})")
    print("=" * 70)

    m_full = simulate(close, -pred, HORIZON_MIN, thresh, capital=10_000.0,
                       risk_pct=RISK_PCT_PER_TRADE, cost_pct=MAKER_COST_PCT, direction="short")
    bh_full = buy_and_hold(close)
    print(f"\n[ALL 2 YEARS, mixed in-sample+out-of-sample -- see caveat below]")
    print(f"  Strategy: {m_full.get('total_return_pct', 0):+.2f}% | "
          f"n_trades={m_full.get('n_trades', 0)} | PF={m_full.get('profit_factor', 0):.3f} | "
          f"max_DD={m_full.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Buy & hold: {bh_full['total_return_pct']:+.2f}%")

    # In-sample portion (TRAIN) -- for context only, not a fair test
    train_close, train_pred = close.iloc[:train_end], pred.iloc[:train_end]
    m_train = simulate(train_close, -train_pred, HORIZON_MIN, thresh, capital=10_000.0,
                        risk_pct=RISK_PCT_PER_TRADE, cost_pct=MAKER_COST_PCT, direction="short")
    bh_train = buy_and_hold(train_close)
    print(f"\n[IN-SAMPLE portion only: {full_df.index[0]:%Y-%m-%d} -> {split_date:%Y-%m-%d} "
          f"-- model was FIT on this data, not a fair test]")
    print(f"  Strategy: {m_train.get('total_return_pct', 0):+.2f}% | n_trades={m_train.get('n_trades', 0)} | "
          f"PF={m_train.get('profit_factor', 0):.3f}")
    print(f"  Buy & hold: {bh_train['total_return_pct']:+.2f}%")

    # Out-of-sample portion (VALIDATION + HOLDOUT combined) -- the fair test
    oos_close, oos_pred = close.iloc[train_end:], pred.iloc[train_end:]
    m_oos = simulate(oos_close, -oos_pred, HORIZON_MIN, thresh, capital=10_000.0,
                      risk_pct=RISK_PCT_PER_TRADE, cost_pct=MAKER_COST_PCT, direction="short")
    bh_oos = buy_and_hold(oos_close)
    print(f"\n[OUT-OF-SAMPLE portion only: {split_date:%Y-%m-%d} -> {full_df.index[-1]:%Y-%m-%d} "
          f"-- the fair test, VALIDATION+HOLDOUT combined]")
    print(f"  Strategy: {m_oos.get('total_return_pct', 0):+.2f}% | n_trades={m_oos.get('n_trades', 0)} | "
          f"PF={m_oos.get('profit_factor', 0):.3f} | max_DD={m_oos.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Buy & hold: {bh_oos['total_return_pct']:+.2f}%")

    print("\n" + "=" * 70)
    print("CAVEAT: the 'ALL 2 YEARS' and 'IN-SAMPLE' numbers above include")
    print("performance on data the model was fitted on -- inflated, not a")
    print("real forward-looking result. Only the OUT-OF-SAMPLE number is a")
    print("fair test, and it's the same period phase7_holdout_eth_short.py")
    print("already tested (that test used ONLY the last 20% / HOLDOUT; this")
    print("one adds the 20% VALIDATION slice in front of it, still fitted")
    print("only on TRAIN).")
    print("=" * 70)


if __name__ == "__main__":
    main()
