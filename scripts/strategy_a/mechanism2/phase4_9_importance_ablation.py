"""Phases 4-9: feature importance (Gini + permutation-on-TEST), feature
ablation (refit-based), directionality, winner/loser signature,
probability calibration, near-miss/counterfactual analysis.

Scope (disclosed, deliberate compute-budget decision, see the parent
mandate message): FULL depth (permutation importance + feature ablation
refits + PDP-style directionality + winner/loser signature) on
BTCUSDT/ETHUSDT's LAST 4 walk-forward folds only. CHEAP depth
(permutation importance only, no refits) on the other 7 symbols, all
folds.

Checkpointed per (symbol, fold) -- resumable.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from common import (
    SYMBOLS_9, MECH2_DOCS, load_symbol, get_folds, fold_layers,
    build_layer_trades, trades_to_metrics, stop_distance_for_layer, classify_outcome,
    load_symbol_feats,
)
from quant_bot.signal.model import Tier2RandomForestSignal
from quant_bot.features.build import build_labels
from quant_bot.config import COST_THRESHOLD_PCT
from scripts.multi_crypto_walkforward import HORIZON, THRESHOLD

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FULL_DEPTH_SYMBOLS = {"BTCUSDT", "ETHUSDT"}
FULL_DEPTH_LAST_N_FOLDS = 4

IMPORTANCE_PATH = os.path.join(MECH2_DOCS, "strategy_a_feature_importance_by_fold.csv")
ABLATION_PATH = os.path.join(MECH2_DOCS, "strategy_a_feature_ablation.csv")
WINLOSE_PATH = os.path.join(MECH2_DOCS, "strategy_a_winner_loser_signature.csv")
CALIB_PATH = os.path.join(MECH2_DOCS, "strategy_a_probability_calibration.csv")
NEARMISS_PATH = os.path.join(MECH2_DOCS, "strategy_a_near_miss.csv")


def permutation_importance_on_test(model, test_feats: pd.DataFrame, test_labels: pd.Series,
                                    n_repeats: int = 5, seed: int = 0) -> pd.Series:
    """AUC-drop permutation importance on TEST (OOS), not TRAIN -- shuffles
    one feature column at a time among the valid (non-NaN, labeled) rows."""
    valid = test_feats[model.feature_names].notna().all(axis=1) & test_labels.notna()
    X, y = test_feats.loc[valid, model.feature_names], test_labels.loc[valid]
    if y.nunique() < 2 or len(y) < 50:
        return pd.Series(dtype=float)
    base_proba = model.model.predict_proba(X)[:, 1]
    base_auc = roc_auc_score(y, base_proba)
    rng = np.random.default_rng(seed)
    drops = {}
    for feat in model.feature_names:
        aucs = []
        for r in range(n_repeats):
            Xp = X.copy()
            Xp[feat] = rng.permutation(Xp[feat].to_numpy())
            p = model.model.predict_proba(Xp)[:, 1]
            aucs.append(roc_auc_score(y, p))
        drops[feat] = base_auc - float(np.mean(aucs))
    return pd.Series(drops).sort_values(ascending=False)


def fit_ablation_variant(train_feats: pd.DataFrame, train_labels: pd.Series,
                          feature_subset: list, fit_n_cap: int = 250_000) -> Tier2RandomForestSignal:
    fit_n = min(fit_n_cap, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(feature_subset, n_estimators=100)
    model.fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
    return model


def already_done(path) -> set:
    if not os.path.exists(path):
        return set()
    df = pd.read_csv(path)
    return set(zip(df["symbol"], df["fold"])) if "fold" in df.columns else set()


def main():
    imp_done = already_done(IMPORTANCE_PATH)
    imp_rows = pd.read_csv(IMPORTANCE_PATH).to_dict("records") if os.path.exists(IMPORTANCE_PATH) else []
    abl_done = already_done(ABLATION_PATH)
    abl_rows = pd.read_csv(ABLATION_PATH).to_dict("records") if os.path.exists(ABLATION_PATH) else []
    wl_done = already_done(WINLOSE_PATH)
    wl_rows = pd.read_csv(WINLOSE_PATH).to_dict("records") if os.path.exists(WINLOSE_PATH) else []
    cal_done = already_done(CALIB_PATH)
    cal_rows = pd.read_csv(CALIB_PATH).to_dict("records") if os.path.exists(CALIB_PATH) else []
    nm_done = already_done(NEARMISS_PATH)
    nm_rows = pd.read_csv(NEARMISS_PATH).to_dict("records") if os.path.exists(NEARMISS_PATH) else []

    for symbol in SYMBOLS_9:
        full = load_symbol(symbol)
        folds, _ = get_folds(full)
        full_depth = symbol in FULL_DEPTH_SYMBOLS
        fold_list = list(enumerate(folds, 1))
        if full_depth:
            fold_list = fold_list[-FULL_DEPTH_LAST_N_FOLDS:]
        print(f"[{symbol}] full_depth={full_depth}  processing {len(fold_list)} fold(s)")
        full_feats = load_symbol_feats(symbol, full)

        for fold_i, (t0, train_end, test_end) in fold_list:
            train_df = full[(full.index >= t0) & (full.index < train_end)]
            test_df = full[(full.index >= train_end) & (full.index < test_end)]
            res = fold_layers(symbol, fold_i, train_df, test_df, full_feats=full_feats)
            if res is None:
                continue
            model = res["model"]
            test_feats, test_proba = res["test_feats"], res["test_proba"]
            test_labels = build_labels(test_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")

            # -- Gini importance (always, cheap) --
            gini = model.feature_importance()

            # -- Permutation importance on TEST (always, cheap: no refit) --
            if (symbol, fold_i) not in imp_done:
                perm = permutation_importance_on_test(model, test_feats, test_labels)
                for feat in model.feature_names:
                    imp_rows.append({
                        "symbol": symbol, "fold": fold_i, "feature": feat,
                        "gini_importance": float(gini.get(feat, np.nan)),
                        "permutation_auc_drop": float(perm.get(feat, np.nan)),
                        "full_depth_fold": full_depth,
                    })
                pd.DataFrame(imp_rows).to_csv(IMPORTANCE_PATH, index=False)
                print(f"  [{symbol}] fold {fold_i}: importance done ({len(model.feature_names)} features)")

            # -- Winner/loser signature (always, cheap: no refit) --
            if (symbol, fold_i) not in wl_done:
                H_mask = res["layers"]["H_full_strategy_a"]
                trades = build_layer_trades(res["test_close"], H_mask, test_feats)
                if len(trades) >= 5:
                    stop_distance, liq_move, protective = stop_distance_for_layer(trades)
                    entry_idx_arr = [t["entry_idx"] for t in trades]
                    entry_times = test_df.index[entry_idx_arr]
                    feats_at_entry = test_feats.loc[entry_times]
                    outcomes = [classify_outcome(t, stop_distance, liq_move) for t in trades]
                    mfe_arr = np.array([t["mfe"] for t in trades])
                    # BIG WINNER = trailing + top-tercile MFE among trailing winners
                    trailing_mfe = mfe_arr[[o == "TRAILING_STOP" for o in outcomes]]
                    big_winner_cut = np.percentile(trailing_mfe, 66.7) if len(trailing_mfe) >= 3 else np.inf
                    for j, (t, o, feat_row) in enumerate(zip(trades, outcomes, feats_at_entry.itertuples())):
                        group = ("BIG_WINNER" if (o == "TRAILING_STOP" and t["mfe"] >= big_winner_cut)
                                 else "NORMAL_WINNER" if o == "TRAILING_STOP"
                                 else "PROTECTIVE_STOP_LOSER" if o == "PROTECTIVE_STOP"
                                 else "END_OF_WINDOW")
                        row = {"symbol": symbol, "fold": fold_i, "group": group,
                               "mfe": t["mfe"], "mae": t["mae"], "raw_return_h": t["close_path"][HORIZON] if len(t["close_path"]) > HORIZON else np.nan,
                               "proba_at_entry": float(test_proba.loc[entry_times[j]])}
                        for feat in model.feature_names:
                            row[f"feat__{feat}"] = getattr(feat_row, feat, np.nan)
                        wl_rows.append(row)
                pd.DataFrame(wl_rows).to_csv(WINLOSE_PATH, index=False)

            # -- Probability calibration (always, cheap) --
            if (symbol, fold_i) not in cal_done:
                range_ok = test_feats["range_pos_60"] < res["range_pos_cut"]
                vol_ok = test_feats["realized_vol_30"] > res["vol_cut"]
                elig = range_ok & vol_ok & test_proba.notna()
                sub = pd.DataFrame({"proba": test_proba[elig], "close_idx": np.arange(len(test_df))[elig.to_numpy()]})
                if len(sub) >= 20:
                    try:
                        sub["bucket"] = pd.qcut(sub["proba"], 5, labels=False, duplicates="drop")
                    except ValueError:
                        sub["bucket"] = 0
                    test_close = res["test_close"]
                    for b, g in sub.groupby("bucket"):
                        idxs = g["close_idx"].to_numpy()
                        idxs = idxs[idxs + HORIZON < len(test_close)]
                        if len(idxs) == 0:
                            continue
                        fwd = test_close[idxs + HORIZON] / test_close[idxs] - 1.0
                        cal_rows.append({"symbol": symbol, "fold": fold_i, "proba_bucket": int(b),
                                          "n": len(idxs), "mean_proba": float(g["proba"].mean()),
                                          "median_fwdret_h_pct": float(np.median(fwd)) * 100,
                                          "winrate_h_pct": float(np.mean(fwd > 0)) * 100})
                pd.DataFrame(cal_rows).to_csv(CALIB_PATH, index=False)

            # -- Near-miss / counterfactual (always, cheap) --
            if (symbol, fold_i) not in nm_done:
                band = 0.02
                near_proba = (test_proba > THRESHOLD - band) & (test_proba <= THRESHOLD + band) & test_proba.notna()
                for label_, mask_ in [("accepted_near_boundary", near_proba & (test_proba > THRESHOLD)),
                                       ("rejected_near_boundary", near_proba & (test_proba <= THRESHOLD))]:
                    mask_full = mask_ & (test_feats["range_pos_60"] < res["range_pos_cut"]) & (test_feats["realized_vol_30"] > res["vol_cut"])
                    trades = build_layer_trades(res["test_close"], mask_full, test_feats)
                    m = trades_to_metrics(trades)
                    nm_rows.append({"symbol": symbol, "fold": fold_i, "boundary": "proba", "group": label_, **m})
                rband = (res["range_pos_cut"] * 0.9, res["range_pos_cut"] * 1.1) if res["range_pos_cut"] > 0 else (res["range_pos_cut"] - 0.05, res["range_pos_cut"] + 0.05)
                near_range = test_feats["range_pos_60"].between(min(rband), max(rband))
                for label_, mask_ in [("accepted_near_boundary", near_range & (test_feats["range_pos_60"] < res["range_pos_cut"])),
                                       ("rejected_near_boundary", near_range & (test_feats["range_pos_60"] >= res["range_pos_cut"]))]:
                    mask_full = mask_ & (test_proba > THRESHOLD) & (test_feats["realized_vol_30"] > res["vol_cut"])
                    trades = build_layer_trades(res["test_close"], mask_full, test_feats)
                    m = trades_to_metrics(trades)
                    nm_rows.append({"symbol": symbol, "fold": fold_i, "boundary": "range_pos_60", "group": label_, **m})
                pd.DataFrame(nm_rows).to_csv(NEARMISS_PATH, index=False)

            # -- Feature ablation (EXPENSIVE, full-depth symbols/folds only) --
            if full_depth and (symbol, fold_i) not in abl_done:
                train_feats = res["train_feats"]
                train_labels = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
                kept = list(model.feature_names)
                H_mask_base = res["layers"]["H_full_strategy_a"]
                base_trades = build_layer_trades(res["test_close"], H_mask_base, test_feats)
                base_m = trades_to_metrics(base_trades)
                abl_rows.append({"symbol": symbol, "fold": fold_i, "dropped_feature": "NONE_baseline", **base_m})
                for feat in kept:
                    subset = [f for f in kept if f != feat]
                    if len(subset) < 2:
                        continue
                    variant = fit_ablation_variant(train_feats, train_labels, subset)
                    v_train_proba = variant.predict_proba(train_feats)
                    v_train_sel = v_train_proba > THRESHOLD
                    if int(v_train_sel.sum()) < 20:
                        abl_rows.append({"symbol": symbol, "fold": fold_i, "dropped_feature": feat, "n": 0, "note": "insufficient TRAIN pop"})
                        continue
                    v_range_cut = float(train_feats.loc[v_train_sel, "range_pos_60"].median())
                    v_vol_cut = float(train_feats.loc[v_train_sel, "realized_vol_30"].median())
                    v_test_proba = variant.predict_proba(test_feats)
                    v_mask = (v_test_proba > THRESHOLD) & (test_feats["range_pos_60"] < v_range_cut) & (test_feats["realized_vol_30"] > v_vol_cut)
                    v_trades = build_layer_trades(res["test_close"], v_mask, test_feats)
                    v_m = trades_to_metrics(v_trades)
                    abl_rows.append({"symbol": symbol, "fold": fold_i, "dropped_feature": feat, **v_m})
                    print(f"    [{symbol}] fold {fold_i}: ablate {feat} -> n={v_m.get('n')} ratio={v_m.get('mfe_over_abs_mae')}")
                pd.DataFrame(abl_rows).to_csv(ABLATION_PATH, index=False)
            print(f"  [{symbol}] fold {fold_i} DONE")

    print("\nAll phase 4-9 outputs saved.")


if __name__ == "__main__":
    main()
