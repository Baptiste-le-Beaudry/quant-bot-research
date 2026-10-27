"""
scripts/diagnostic_waterfall.py — the two diagnostics requested: (1) a cost
waterfall (gross edge -> after fees -> after fees+slippage -> after
fees+slippage+funding) to tell "signal too weak to survive costs" apart
from "no real signal," and (2) a full horizon sweep (5/10/15/30/60min) with
AUC + edge + profit factor at each, so the horizon decision is made from a
complete table instead of the two horizons (10, 30) tested individually so
far.

Tier 2 (random forest), classification target matching the plan's original
example (P(R_h > cost)). Evaluated at SEVERAL thresholds per horizon, not
just one — a first pass at threshold=0.55 showed gross edge ~0 at every
horizon, but that threshold barely filters anything (>50% of all bars
selected at h=5min), so it mostly measures the whole market's near-zero
short-horizon drift, not what the model's more confident predictions
actually do. Higher thresholds (0.65-0.85) are where prior sweeps this
session showed something. VALIDATION only (not touching HOLDOUT for a
diagnostic sweep across 5 horizons x multiple thresholds -- that would burn
holdout on exploration, not a frozen configuration).

Usage:
    python scripts/diagnostic_waterfall.py --symbol ETHUSDT
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from sklearn.metrics import roc_auc_score

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.costs import waterfall, load_funding
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HORIZONS = [5, 10, 15, 30, 60]
THRESHOLDS = [0.55, 0.65, 0.75, 0.85]
DIRECTION = "long"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--train-symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"],
                         help="symbols used to fit the model (kept at both, as every prior tier did)")
    args = parser.parse_args()

    funding = load_funding(args.symbol)
    print(f"Funding data: {len(funding)} events, {funding.index[0]:%Y-%m-%d} -> {funding.index[-1]:%Y-%m-%d}")
    print(f"Fee/slippage assumed: taker round-trip={ROUND_TRIP_FEE_PCT*100:.3f}%, "
          f"slippage={SLIPPAGE_PCT_EST*100:.3f}%\n")

    rows = []
    for h in HORIZONS:
        print(f"--- horizon={h}min ---")
        train_feats, train_labels = {}, {}
        for symbol in args.train_symbols:
            df = load_split(symbol, "train", verbose=False)
            train_feats[symbol] = build_feature_matrix(df)
            train_labels[symbol] = build_labels(df["close"], h, COST_THRESHOLD_PCT, direction=DIRECTION)
        X_train = pd.concat(train_feats.values(), ignore_index=True)
        y_train = pd.concat(train_labels.values(), ignore_index=True)

        kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
        fit_n = min(250_000, len(X_train))
        fit_idx = X_train.sample(n=fit_n, random_state=42).index
        model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])

        df_val = load_split(args.symbol, "validation", verbose=False)
        feats_val = build_feature_matrix(df_val)
        close_val = df_val["close"]
        label_val = build_labels(close_val, h, COST_THRESHOLD_PCT, direction=DIRECTION)
        proba = model.predict_proba(feats_val)

        valid = proba.notna() & label_val.notna()
        auc = roc_auc_score(label_val[valid], proba[valid])
        print(f"  AUC={auc:.4f}")

        for thresh in THRESHOLDS:
            entry_mask = proba > thresh
            wf = waterfall(close_val, entry_mask, h, DIRECTION, funding=funding)
            wf["horizon"] = h
            wf["threshold"] = thresh
            wf["auc"] = round(auc, 4)
            rows.append(wf)

    print("\n" + "=" * 100)
    print(f"  FULL RESULTS TABLE — {args.symbol}, VALIDATION, direction={DIRECTION}")
    print("=" * 100)
    header = (f"{'h(min)':>7}{'thr':>6}{'AUC':>7}{'n':>8}{'gross%':>9}{'+fees%':>9}"
              f"{'+slip%':>9}{'+fund%':>9}{'PF_gross':>10}{'PF_net':>9}{'win%':>7}{'reliable?':>10}")
    print(header)
    print("-" * len(header))
    for r in rows:
        if r.get("n_trades", 0) == 0:
            print(f"{r['horizon']:>7}{r['threshold']:>6.2f}{'(no trades)':>8}")
            continue
        reliable = "n>100" if r["n_trades"] > 100 else "n<100 !!"
        print(f"{r['horizon']:>7}{r['threshold']:>6.2f}{r['auc']:>7.4f}{r['n_trades']:>8}"
              f"{r['gross_mean_pct']:>9.4f}{r['after_fees_mean_pct']:>9.4f}"
              f"{r['after_fees_slip_mean_pct']:>9.4f}{r['after_all_mean_pct']:>9.4f}"
              f"{r['pf_gross']:>10.3f}{r['pf_after_all']:>9.3f}{r['win_rate_after_all_pct']:>7.1f}{reliable:>10}")

    print("\nInterpretation guide:")
    print("  gross% ~ 0 or negative at EVERY horizon -> features don't capture predictive")
    print("    information (Example 2 in your message): no amount of cost optimization helps.")
    print("  gross% clearly positive but PF_net < 1 -> signal exists but isn't strong enough")
    print("    to survive costs (Example 1): worth chasing cheaper execution or a higher")
    print("    conviction threshold, not new features.")
    print("  gross% positive AND PF_net > 1 with n>100 -> Example 3, worth a holdout look.")


if __name__ == "__main__":
    main()
