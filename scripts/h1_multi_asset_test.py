"""
scripts/h1_multi_asset_test.py — autonomous-session task: "une version pour
eth, btc et nasdaq sur 1h." Uses quant_bot.features.build_h1 (hourly-adapted
windows) and quant_bot.data.h1_loader (BTCUSDT/ETHUSDT 9-year H1 carried
over from confluence_ai_v3, NQUSD 2.4-year H1 via yfinance).

Same tier-2 random forest, classification target, real engine (one position
at a time, compounding) as the crypto 1-min work -- only the bar unit and
feature windows change. Tests a horizon sweep per symbol since H1's right
horizon hasn't been established at all yet (unlike 1-min, where 10min beat
30min on trading economics).

Caveat printed in the output: equity/futures (NQUSD) trade under a
different fee structure than crypto perpetuals -- this reuses the crypto
cost assumptions as a first pass, not a precise NQ fee model.

Usage:
    python scripts/h1_multi_asset_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from sklearn.metrics import roc_auc_score

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, RISK_PCT_PER_TRADE
from quant_bot.features.build_h1 import build_feature_matrix_h1, build_labels_h1
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate, buy_and_hold
from quant_bot.signal.model import Tier2RandomForestSignal
from quant_bot.data.h1_loader import load_h1_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOLS = ["BTCUSDT", "ETHUSDT", "NQUSD"]
HORIZONS = [4, 8, 24]  # hours
THRESHOLDS = [0.55, 0.60, 0.65]
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST


def main():
    results = []
    for symbol in SYMBOLS:
        print("\n" + "=" * 70)
        print(f"  {symbol} H1")
        print("=" * 70)
        train_df = load_h1_split(symbol, "train")
        train_feats_full = build_feature_matrix_h1(train_df)
        val_df = load_h1_split(symbol, "validation")
        val_feats_full = build_feature_matrix_h1(val_df)
        val_close = val_df["close"]
        bh = buy_and_hold(val_close)
        print(f"Buy & hold over VALIDATION: {bh['total_return_pct']:+.2f}%")

        for h in HORIZONS:
            y_train = build_labels_h1(train_df["close"], h, COST_THRESHOLD_PCT, direction="long")
            kept, _ = prune_redundant(train_feats_full, y_train, corr_threshold=0.9, max_rows=100_000)
            model = Tier2RandomForestSignal(kept, n_estimators=100).fit(train_feats_full, y_train)

            y_val = build_labels_h1(val_close, h, COST_THRESHOLD_PCT, direction="long")
            proba = model.predict_proba(val_feats_full)
            valid = proba.notna() & y_val.notna()
            if valid.sum() < 20 or y_val[valid].nunique() < 2:
                print(f"  h={h}h: not enough valid/varied data, skipping")
                continue
            auc = roc_auc_score(y_val[valid], proba[valid])
            print(f"\n  --- horizon={h}h --- AUC={auc:.4f}")
            for thresh in THRESHOLDS:
                m = simulate(val_close, proba, h, thresh, capital=10_000.0,
                             risk_pct=RISK_PCT_PER_TRADE, cost_pct=COST_PCT)
                if m.get("n_trades", 0) == 0:
                    print(f"    threshold={thresh}: no trades")
                    continue
                reliable = "n>100" if m["n_trades"] > 100 else "n<100 !!"
                print(f"    threshold={thresh}: n={m['n_trades']}, win%={m['win_rate_pct']:.1f}, "
                      f"PF={m['profit_factor']:.3f}, total_ret={m['total_return_pct']:+.2f}%, "
                      f"max_DD={m['max_drawdown_pct']:.2f}% [{reliable}]")
                results.append({"symbol": symbol, "horizon_h": h, "threshold": thresh, "auc": auc, **m})

    print("\n\n" + "=" * 70)
    print("  SUMMARY — best (n>100) result per symbol by profit factor")
    print("=" * 70)
    df_res = pd.DataFrame(results)
    if len(df_res):
        reliable_res = df_res[df_res["n_trades"] > 100]
        for symbol in SYMBOLS:
            sub = reliable_res[reliable_res["symbol"] == symbol]
            if len(sub) == 0:
                print(f"{symbol}: no reliable (n>100) result found")
                continue
            best = sub.loc[sub["profit_factor"].idxmax()]
            print(f"{symbol}: horizon={best['horizon_h']}h, threshold={best['threshold']}, "
                  f"n={best['n_trades']}, PF={best['profit_factor']:.3f}, "
                  f"total_ret={best['total_return_pct']:+.2f}%")
    print("\nCaveat: NQUSD uses crypto fee/slippage assumptions as a first pass, not a")
    print("precise equity-futures cost model.")


if __name__ == "__main__":
    main()
