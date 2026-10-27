"""
scripts/step13_regression_target.py — Étape 13: does predicting the raw
forward return (RegressionForestSignal, quant_bot/signal/model.py, already
built but not used anywhere in this session) instead of the binary
cost-threshold label improve on BASELINE_CANDIDATE_V2's classifier, within
the CURRENT pipeline (entry filter + trailing exit + protective stop) --
not the old, superseded docs/phase6_regression_results.md setup (2yr data,
horizon=30min, no entry filter, no trailing/stop mechanism at all).

Two things checked:
  1. Feature importance comparison -- docs/phase6_regression_results.md's
     finding was that autocorr_240 jumps from ~0.02-0.03 (classifier) to
     0.125 (regressor, 3rd-ranked) once the model can use return
     MAGNITUDE instead of a collapsed binary label. Does that still hold
     on the current 7yr data / feature set?
  2. Trading result: gate entries on predicted_return > threshold (TRAIN-
     calibrated) AND the same range_pos_60/realized_vol_30 filter (cutoffs
     also TRAIN-calibrated on the regression-selected population), run
     through V2's exact exit logic, compare n/PF/return to the classifier
     baseline.

Usage:
    python scripts/step13_regression_target.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels, build_regression_label
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal, RegressionForestSignal
from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
CLASSIFIER_THRESHOLD = 0.75
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01
RETURN_PCTL_CANDIDATES = [90, 92.5, 95, 97.5]  # top-X percentile of TRAIN predicted return as the entry gate


def simulate(trades, leverage, stop_distance) -> dict:
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = CAPITAL * RISK_PCT
    pnls = []
    for t in trades:
        path = t["close_path"]
        peak, activated = -np.inf, False
        exit_ret = None
        for x in path:
            if x <= -protective:
                exit_ret = -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    exit_ret = stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                    break
        if exit_ret is None:
            exit_ret = path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        pnls.append(exit_ret * notional * leverage)
    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
            "win_rate_pct": round((pnls > 0).mean() * 100, 1)}


def main():
    print("Fitting BOTH tier-2 classifier and regression forest (BTC+ETH jointly), horizon=10min...")
    train_feats_all, train_labels_cls, train_labels_reg = {}, {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats_all[symbol] = build_feature_matrix(df)
        train_labels_cls[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
        train_labels_reg[symbol] = build_regression_label(df["close"], HORIZON)
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train_cls = pd.concat(train_labels_cls.values(), ignore_index=True)
    y_train_reg = pd.concat(train_labels_reg.values(), ignore_index=True)

    kept_cls, _ = prune_redundant(X_train, y_train_cls, corr_threshold=0.9)
    kept_reg, _ = prune_redundant(X_train, y_train_reg, corr_threshold=0.9, regression=True)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index

    clf = Tier2RandomForestSignal(kept_cls, n_estimators=100).fit(X_train.loc[fit_idx], y_train_cls.loc[fit_idx])
    reg = RegressionForestSignal(kept_reg, n_estimators=100).fit(X_train.loc[fit_idx], y_train_reg.loc[fit_idx])
    print(f"Classifier: {len(kept_cls)} features. Regressor: {len(kept_reg)} features.\n")

    print("=" * 100)
    print("  Feature importance comparison (top 8 each)")
    print("=" * 100)
    cls_imp = clf.feature_importance().head(8)
    reg_imp = reg.feature_importance().head(8)
    print(f"  {'CLASSIFIER':<28}{'importance':>12}   {'REGRESSOR':<28}{'importance':>12}")
    for (cf, ci), (rf, ri) in zip(cls_imp.items(), reg_imp.items()):
        print(f"  {cf:<28}{ci:>12.4f}   {rf:<28}{ri:>12.4f}")
    autocorr_cls = clf.feature_importance().get("autocorr_240", clf.feature_importance().get("autocorr_60", None))
    autocorr_reg = reg.feature_importance().get("autocorr_240", reg.feature_importance().get("autocorr_60", None))
    if autocorr_cls is not None and autocorr_reg is not None:
        print(f"\n  autocorr feature: classifier={autocorr_cls:.4f}  regressor={autocorr_reg:.4f}  "
              f"(phase6's prior finding: ~0.02-0.03 -> 0.125 going classifier->regressor)")

    all_rows = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df = load_split(symbol, "train", verbose=False)
        train_feats = build_feature_matrix(train_df)
        train_close = train_df["close"].to_numpy()
        train_ema_slope = train_feats["ema_slope_20"].to_numpy()
        train_ret_1 = train_feats["ret_1"].to_numpy()

        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()

        # AUC-style check: does the regressor's predicted return rank-order actual outcomes on VALIDATION?
        val_pred_ret = reg.predict(val_feats)
        val_actual_label = build_labels(val_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
        valid = val_pred_ret.notna() & val_actual_label.notna()
        auc_reg_as_ranker = roc_auc_score(val_actual_label[valid], val_pred_ret[valid])
        val_cls_proba = clf.predict_proba(val_feats)
        auc_cls = roc_auc_score(val_actual_label[valid], val_cls_proba[valid])
        print(f"\n{symbol}: classifier AUC={auc_cls:.4f} | regressor-as-ranker AUC={auc_reg_as_ranker:.4f} "
              f"(predicted return used to rank the same binary outcome)")

        print(f"\n  -- Trading result comparison, {symbol} --")
        # Classifier baseline (registered V2)
        train_proba = clf.predict_proba(train_feats)
        train_selected_cls = train_proba > CLASSIFIER_THRESHOLD
        rp_cut_cls = train_feats.loc[train_selected_cls, "range_pos_60"].median()
        vol_cut_cls = train_feats.loc[train_selected_cls, "realized_vol_30"].median()
        val_proba = clf.predict_proba(val_feats)
        cls_mask = (
            (val_proba > CLASSIFIER_THRESHOLD)
            & (val_feats["range_pos_60"] < rp_cut_cls)
            & (val_feats["realized_vol_30"] > vol_cut_cls)
        ).to_numpy()
        cls_trades = build_trades_with_mae_mfe(val_close, cls_mask, val_ema_slope, val_ret_1)
        cls_stop = float(np.percentile(np.abs([t["mae"] for t in
                          build_trades_with_mae_mfe(train_close,
                              ((train_proba > CLASSIFIER_THRESHOLD) & (train_feats["range_pos_60"] < rp_cut_cls) &
                               (train_feats["realized_vol_30"] > vol_cut_cls)).to_numpy(),
                              train_ema_slope, train_ret_1)]), STOP_PCT_PERCENTILE))
        r_cls = simulate(cls_trades, LEVERAGE[symbol], cls_stop)
        print(f"  classifier (registered V2, thr={CLASSIFIER_THRESHOLD}): n={r_cls.get('n_trades',0)} "
              f"PF={r_cls.get('profit_factor',float('nan')):.3f} "
              f"ret={r_cls.get('total_return_pct',float('nan')):+.3f}%")
        all_rows.append({"symbol": symbol, "model": "classifier", **r_cls})

        # Regressor-gated variants
        train_pred_ret = reg.predict(train_feats)
        for pctl in RETURN_PCTL_CANDIDATES:
            ret_cut = np.nanpercentile(train_pred_ret, pctl)
            train_reg_selected = train_pred_ret > ret_cut
            if train_reg_selected.sum() < 20:
                print(f"  regressor p{pctl}: TRAIN-selected population < 20, skipping")
                continue
            rp_cut_reg = train_feats.loc[train_reg_selected, "range_pos_60"].median()
            vol_cut_reg = train_feats.loc[train_reg_selected, "realized_vol_30"].median()

            val_pred_ret_arr = reg.predict(val_feats)
            reg_mask = (
                (val_pred_ret_arr > ret_cut)
                & (val_feats["range_pos_60"] < rp_cut_reg)
                & (val_feats["realized_vol_30"] > vol_cut_reg)
            ).to_numpy()
            reg_trades = build_trades_with_mae_mfe(val_close, reg_mask, val_ema_slope, val_ret_1)
            if len(reg_trades) < 5:
                print(f"  regressor p{pctl}: only {len(reg_trades)} VALIDATION entries, skipping")
                continue
            train_reg_trades = build_trades_with_mae_mfe(
                train_close,
                ((train_pred_ret > ret_cut) & (train_feats["range_pos_60"] < rp_cut_reg) &
                 (train_feats["realized_vol_30"] > vol_cut_reg)).to_numpy(),
                train_ema_slope, train_ret_1)
            if len(train_reg_trades) < 10:
                print(f"  regressor p{pctl}: too few TRAIN trades to calibrate stop, skipping")
                continue
            reg_stop = float(np.percentile(np.abs([t["mae"] for t in train_reg_trades]), STOP_PCT_PERCENTILE))
            r_reg = simulate(reg_trades, LEVERAGE[symbol], reg_stop)
            print(f"  regressor p{pctl} (pred_ret>{ret_cut*100:.3f}%): n={r_reg.get('n_trades',0)} "
                  f"PF={r_reg.get('profit_factor',float('nan')):.3f} "
                  f"ret={r_reg.get('total_return_pct',float('nan')):+.3f}%")
            all_rows.append({"symbol": symbol, "model": f"regressor_p{pctl}", "ret_cutoff": ret_cut, **r_reg})

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step13_regression_raw.csv")
    pd.DataFrame(all_rows).to_csv(out_path, index=False)
    print(f"\nRaw results saved -> {out_path}")


if __name__ == "__main__":
    main()
