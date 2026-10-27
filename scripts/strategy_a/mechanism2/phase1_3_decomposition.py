"""Phases 1-3: pipeline decomposition (8 layers A-H) + RF-vs-filter
contribution, ALL 9 symbols, ALL their pre-HOLDOUT walk-forward folds.
Cheap: exactly ONE RandomForest fit per fold (the same fit the frozen
baseline itself required), the 8 layers are just boolean-mask
combinations of that one fold's already-computed test_proba/features.

Checkpointed per (symbol, fold) row -- resumable.

Usage: python scripts/strategy_a/mechanism2/phase1_3_decomposition.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd

from common import (
    SYMBOLS_9, MECH2_DOCS, load_symbol, get_folds, fold_layers,
    build_layer_trades, trades_to_metrics, load_symbol_feats,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_PATH = os.path.join(MECH2_DOCS, "strategy_a_component_decomposition.csv")
LAYER_ORDER = ["A_all_eligible", "B_range_only", "C_vol_only", "D_both_filters",
               "E_rf_only", "F_rf_range", "G_rf_vol", "H_full_strategy_a"]


def already_done() -> set:
    if not os.path.exists(OUT_PATH):
        return set()
    df = pd.read_csv(OUT_PATH)
    return set(zip(df["symbol"], df["fold"]))


def main():
    done = already_done()
    rows = pd.read_csv(OUT_PATH).to_dict("records") if os.path.exists(OUT_PATH) else []
    for symbol in SYMBOLS_9:
        full = load_symbol(symbol)
        folds, adapted = get_folds(full)
        print(f"[{symbol}] {len(folds)} folds (adapted={adapted}), "
              f"{full.index[0]:%Y-%m-%d} -> {full.index[-1]:%Y-%m-%d}")
        if any((symbol, fold_i) not in done for fold_i in range(1, len(folds) + 1)):
            full_feats = load_symbol_feats(symbol, full)
        else:
            full_feats = None
        for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
            if (symbol, fold_i) in done:
                continue
            train_df = full[(full.index >= t0) & (full.index < train_end)]
            test_df = full[(full.index >= train_end) & (full.index < test_end)]
            res = fold_layers(symbol, fold_i, train_df, test_df, full_feats=full_feats)
            if res is None:
                print(f"  [{symbol}] fold {fold_i}: TRAIN pop too small, skip")
                continue
            for layer in LAYER_ORDER:
                mask = res["layers"][layer]
                trades = build_layer_trades(res["test_close"], mask, res["test_feats"])
                m = trades_to_metrics(trades)
                row = {"symbol": symbol, "fold": fold_i, "layer": layer,
                       "train_start": t0, "train_end": train_end, "test_end": test_end,
                       "n_kept_features": len(res["kept_features"]),
                       "range_pos_cut": res["range_pos_cut"], "vol_cut": res["vol_cut"], **m}
                rows.append(row)
            print(f"  [{symbol}] fold {fold_i}/{len(folds)} done "
                  f"(H n={res['layers']['H_full_strategy_a'].sum()})")
            pd.DataFrame(rows).to_csv(OUT_PATH, index=False)
    print(f"\nSaved -> {OUT_PATH}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
