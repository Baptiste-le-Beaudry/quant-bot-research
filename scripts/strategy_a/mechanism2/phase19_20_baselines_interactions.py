"""Phase 19: simple baseline models (random / filter-only / logistic /
adopted RF), same feature set + fold split, no hyperparameter search.
Phase 20: nonlinear-interaction analysis via TreeSHAP interaction values
(now installed) on BTCUSDT/ETHUSDT's LATEST fold only (most compute-
intensive phase, scoped to one representative fold per symbol per the
mandate's own explicit budget note).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from common import SYMBOLS_9, MECH2_DOCS, load_symbol, get_folds, fold_layers, build_layer_trades, trades_to_metrics, load_symbol_feats
from quant_bot.signal.model import Tier1LogisticSignal
from quant_bot.features.build import build_labels
from quant_bot.config import COST_THRESHOLD_PCT
from scripts.multi_crypto_walkforward import HORIZON, THRESHOLD

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASELINE_SYMBOLS_FULL = ["BTCUSDT", "ETHUSDT"]
SPOT_CHECK_OTHERS = ["SOLUSDT", "LINKUSDT"]  # disclosed spot-check picks for phase 19
BASELINE_PATH = os.path.join(MECH2_DOCS, "strategy_a_phase19_simple_baselines.csv")
INTERACTION_PATH = os.path.join(MECH2_DOCS, "strategy_a_phase20_shap_interactions.csv")


def phase19():
    rows = []
    for symbol in BASELINE_SYMBOLS_FULL + SPOT_CHECK_OTHERS:
        full = load_symbol(symbol)
        folds, _ = get_folds(full)
        last4 = folds[-4:] if symbol in BASELINE_SYMBOLS_FULL else folds[-1:]
        full_feats = load_symbol_feats(symbol, full)
        for fold_i, (t0, train_end, test_end) in list(enumerate(folds, 1))[-len(last4):]:
            train_df = full[(full.index >= t0) & (full.index < train_end)]
            test_df = full[(full.index >= train_end) & (full.index < test_end)]
            res = fold_layers(symbol, fold_i, train_df, test_df, full_feats=full_feats)
            if res is None:
                continue
            kept = list(res["model"].feature_names)
            train_feats, test_feats, test_close = res["train_feats"], res["test_feats"], res["test_close"]
            train_labels = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")

            # -- random selection, matched in time/regime to H's own event rate --
            rng = np.random.default_rng(42)
            h_rate = res["layers"]["H_full_strategy_a"].mean()
            valid = res["layers"]["A_all_eligible"]
            rand_mask = pd.Series(False, index=test_feats.index)
            elig_idx = np.flatnonzero(valid.to_numpy())
            n_pick = int(round(h_rate * valid.sum()))
            if n_pick > 0 and len(elig_idx) > 0:
                pick = rng.choice(elig_idx, size=min(n_pick, len(elig_idx)), replace=False)
                rand_mask.iloc[pick] = True
            rand_trades = build_layer_trades(test_close, rand_mask, test_feats)
            rows.append({"symbol": symbol, "fold": fold_i, "model": "random_matched_rate", **trades_to_metrics(rand_trades)})

            # -- filter-only (D layer, already computed) --
            filt_trades = build_layer_trades(test_close, res["layers"]["D_both_filters"], test_feats)
            rows.append({"symbol": symbol, "fold": fold_i, "model": "filter_only", **trades_to_metrics(filt_trades)})

            # -- simple logistic regression, same feature set, same TRAIN/TEST --
            fit_n = min(250_000, len(train_feats))
            fit_idx = train_feats.sample(n=fit_n, random_state=42).index
            logi = Tier1LogisticSignal(kept).fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
            logi_train_proba = logi.predict_proba(train_feats)
            logi_train_sel = logi_train_proba > THRESHOLD
            if int(logi_train_sel.sum()) >= 20:
                lr_range_cut = float(train_feats.loc[logi_train_sel, "range_pos_60"].median())
                lr_vol_cut = float(train_feats.loc[logi_train_sel, "realized_vol_30"].median())
                logi_test_proba = logi.predict_proba(test_feats)
                logi_mask = (logi_test_proba > THRESHOLD) & (test_feats["range_pos_60"] < lr_range_cut) & (test_feats["realized_vol_30"] > lr_vol_cut)
                logi_trades = build_layer_trades(test_close, logi_mask, test_feats)
                rows.append({"symbol": symbol, "fold": fold_i, "model": "logistic_regression", **trades_to_metrics(logi_trades)})
            else:
                rows.append({"symbol": symbol, "fold": fold_i, "model": "logistic_regression", "n": 0, "note": "insufficient TRAIN pop"})

            # -- adopted RF (H layer, already computed) --
            rf_trades = build_layer_trades(test_close, res["layers"]["H_full_strategy_a"], test_feats)
            rows.append({"symbol": symbol, "fold": fold_i, "model": "adopted_random_forest", **trades_to_metrics(rf_trades)})

            pd.DataFrame(rows).to_csv(BASELINE_PATH, index=False)
            print(f"[{symbol}] fold {fold_i}: baselines done")
    print(f"Saved -> {BASELINE_PATH}")


def phase20():
    import shap
    rows = []
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        full = load_symbol(symbol)
        folds, _ = get_folds(full)
        fold_i = len(folds)
        t0, train_end, test_end = folds[-1]
        train_df = full[(full.index >= t0) & (full.index < train_end)]
        test_df = full[(full.index >= train_end) & (full.index < test_end)]
        full_feats = load_symbol_feats(symbol, full)
        res = fold_layers(symbol, fold_i, train_df, test_df, full_feats=full_feats)
        if res is None:
            continue
        model, test_feats = res["model"], res["test_feats"]
        kept = model.feature_names
        elig = test_feats[kept].notna().all(axis=1) & res["layers"]["A_all_eligible"]
        sample_idx = test_feats[elig].sample(n=min(2000, int(elig.sum())), random_state=0).index
        X = test_feats.loc[sample_idx, kept]
        explainer = shap.TreeExplainer(model.model)
        try:
            shap_inter = explainer.shap_interaction_values(X)
            if isinstance(shap_inter, list):
                shap_inter = shap_inter[1]  # class-1 (positive label) interactions
            elif shap_inter.ndim == 4:
                shap_inter = shap_inter[:, :, :, 1]  # this shap version: (n, feat, feat, n_classes)
            mean_abs_inter = np.abs(shap_inter).mean(axis=0)
            for i, fi in enumerate(kept):
                for j, fj in enumerate(kept):
                    if j <= i:
                        continue
                    rows.append({"symbol": symbol, "fold": fold_i, "feature_1": fi, "feature_2": fj,
                                 "mean_abs_shap_interaction": float(mean_abs_inter[i, j])})
            print(f"[{symbol}] SHAP interaction matrix computed on {len(X)} TEST rows")
        except Exception as e:
            print(f"[{symbol}] SHAP interaction failed ({e}); falling back to main-effect-only SHAP")
            shap_vals = explainer.shap_values(X)
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[1]
            elif shap_vals.ndim == 3:
                shap_vals = shap_vals[:, :, 1]
            mean_abs = np.abs(shap_vals).mean(axis=0)
            for i, f in enumerate(kept):
                rows.append({"symbol": symbol, "fold": fold_i, "feature_1": f, "feature_2": "MAIN_EFFECT_ONLY",
                             "mean_abs_shap_interaction": float(mean_abs[i])})
        pd.DataFrame(rows).to_csv(INTERACTION_PATH, index=False)
    print(f"Saved -> {INTERACTION_PATH}")


if __name__ == "__main__":
    phase19()
    phase20()
