"""
scripts/step0_reproducibility_audit.py — Étape 0 of the iterative research
plan (docs/research_plan_status.md): before any new optimization, (1) print
the exact TRAIN/VALIDATION/HOLDOUT date ranges for BTCUSDT/ETHUSDT so they
are on record, and (2) re-run BASELINE_CANDIDATE_V1 (trailing exit, 1x, no
stop) exactly as scripts/leverage_trailing_combined.py did, to confirm it
reproduces the recorded numbers (ETH n=89 PF=1.239 +0.12%; BTC n=42
PF=1.952 +0.15%). If this does not reproduce, STOP per the plan and
investigate before continuing.

Usage:
    python scripts/step0_reproducibility_audit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.leverage_trailing_combined import apply_stop_and_trailing_leveraged, report as lev_report

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST

EXPECTED = {
    "ETHUSDT": {"n": 89, "pf": 1.239, "ret": 0.12},
    "BTCUSDT": {"n": 42, "pf": 1.952, "ret": 0.15},
}


def main():
    print("=" * 90)
    print("  TEST 0.2 — exact TRAIN/VALIDATION/HOLDOUT date ranges")
    print("=" * 90)
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        for split in ["train", "validation", "holdout"]:
            df = load_split(symbol, split, verbose=False)
            marker = "  <-- LOCKED — DO NOT TOUCH" if split == "holdout" else ""
            print(f"{symbol:<10}{split.upper():<12}{len(df):>10,} bars   "
                  f"{df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}{marker}")
        print()

    print("=" * 90)
    print("  TEST 0.1 — reproduce BASELINE_CANDIDATE_V1 (trailing, 1x, no stop)")
    print("=" * 90)
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min, random_state=42...")
    train_feats, train_labels = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept: {kept}\n")

    all_pass = True
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df_sym = load_split(symbol, "train", verbose=False)
        train_feats_sym = build_feature_matrix(train_df_sym)
        train_proba_sym = model.predict_proba(train_feats_sym)
        train_selected_sym = train_proba_sym > THRESHOLD
        range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
        vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

        df_val = load_split(symbol, "validation", verbose=False)
        feats_val = build_feature_matrix(df_val)
        close_val = df_val["close"]
        proba = model.predict_proba(feats_val)
        filtered_mask = (
            (proba > THRESHOLD)
            & (feats_val["range_pos_60"] < range_pos_cut)
            & (feats_val["realized_vol_30"] > vol_cut)
        ).to_numpy()
        close_arr = close_val.to_numpy()
        ema_slope_arr = feats_val["ema_slope_20"].to_numpy()
        ret_1_arr = feats_val["ret_1"].to_numpy()

        trades = build_trades_with_mae_mfe(close_arr, filtered_mask, ema_slope_arr, ret_1_arr)
        results_1x = apply_stop_and_trailing_leveraged(trades, stop_distance=1.0, leverage=1.0)
        r = lev_report(symbol, results_1x, 1.0, 1.0, "1x")

        exp = EXPECTED[symbol]
        n_ok = r_n_matches = len(trades) == exp["n"]
        pf_ok = abs(r["profit_factor"] - exp["pf"]) < 0.01
        ret_ok = abs(r["total_return_pct"] - exp["ret"]) < 0.02
        status = "PASS" if (n_ok and pf_ok and ret_ok) else "MISMATCH"
        all_pass = all_pass and (n_ok and pf_ok and ret_ok)
        print(f"  {symbol}: expected n={exp['n']} PF={exp['pf']} ret={exp['ret']:+.2f}% | "
              f"got n={len(trades)} PF={r['profit_factor']} ret={r['total_return_pct']:+.2f}% -> {status}\n")

    print("=" * 90)
    if all_pass:
        print("  RESULT: REPRODUCIBLE — proceeding is safe. CONTINUE to Étape 1 (stress test).")
    else:
        print("  RESULT: MISMATCH DETECTED — per the plan, STOP and investigate before continuing.")
    print("=" * 90)


if __name__ == "__main__":
    main()
