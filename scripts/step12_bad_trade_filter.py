"""
scripts/step12_bad_trade_filter.py — Étape 12: can an entry-time feature
predict whether a qualifying entry will become a "bad trade" (net loss
under BASELINE_CANDIDATE_V2's exit logic), rather than just LONG/SHORT?
Experiment 3 found a striking low-MAE/high-MFE vs high-MAE/low-MFE split,
but MAE/MFE are OUTCOME variables only known after the trade plays out --
this tests whether that split is predictable AT ENTRY TIME.

HONEST CAVEAT UP FRONT: TRAIN's own filtered-entry population (the only
data available to fit this on, per discipline -- never VALIDATION) is
itself only ~200-350 trades for a 10-feature logistic regression. That is
thin for a model with this many parameters; treat any result here as a
lead, not a validated filter, even more so than Étape 15's simpler
single-feature volatility filter.

Usage:
    python scripts/step12_bad_trade_filter.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080  # V2
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01

BAD_TRADE_FEATURES = ["realized_vol_30", "atr_norm", "dist_ema20_atr", "ema_slope_20",
                       "rel_volume_20", "volume_accel", "range_pos_60"]


def resolve_exit_return(path: np.ndarray, stop_distance: float, leverage: float) -> float:
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
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
    return exit_ret


def simulate_from_returns(returns: list, leverage: float) -> dict:
    pnls = np.array(returns) * CAPITAL * RISK_PCT * leverage
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
            "win_rate_pct": round((pnls > 0).mean() * 100, 1)}


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min...")
    train_feats_all, train_labels_all = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats_all[symbol] = build_feature_matrix(df)
        train_labels_all[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train = pd.concat(train_labels_all.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.\n")

    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df = load_split(symbol, "train", verbose=False)
        train_feats = build_feature_matrix(train_df)
        train_proba = model.predict_proba(train_feats)
        train_selected = train_proba > THRESHOLD
        range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
        vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()
        train_close = train_df["close"].to_numpy()
        train_ema_slope = train_feats["ema_slope_20"].to_numpy()
        train_ret_1 = train_feats["ret_1"].to_numpy()
        train_filtered_mask = (
            (train_proba > THRESHOLD)
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        train_trades = build_trades_with_mae_mfe(train_close, train_filtered_mask, train_ema_slope, train_ret_1)
        stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
        leverage = LEVERAGE[symbol]

        # Label each TRAIN trade by whether V2's actual exit logic would realize a loss.
        # (hoisted OUTSIDE the loop -- re-selecting these columns from the full
        # multi-million-row frame inside the loop was allocating a fresh ~113MB
        # array per trade and exhausting memory)
        train_feat_arr = train_feats[BAD_TRADE_FEATURES].to_numpy()
        train_X, train_y = [], []
        for t in train_trades:
            i = t["entry_idx"]
            ret = resolve_exit_return(t["close_path"], stop_distance, leverage)
            train_y.append(1 if ret <= 0 else 0)  # 1 = bad trade
            train_X.append(train_feat_arr[i])
        train_X = np.array(train_X, dtype=float)
        train_y = np.array(train_y)

        print("=" * 100)
        print(f"  {symbol} — bad-trade filter (TRAIN n={len(train_trades)}, "
              f"bad_trade_rate={train_y.mean()*100:.1f}%)")
        print("=" * 100)
        if len(train_trades) < 40 or train_y.sum() < 10 or (len(train_y) - train_y.sum()) < 10:
            print("  Too few TRAIN trades / class imbalance to fit a meaningful classifier -- skipping.\n")
            continue

        scaler = StandardScaler()
        Xs = scaler.fit_transform(train_X)
        clf = LogisticRegression(max_iter=1000, class_weight="balanced")
        cv_scores = cross_val_score(clf, Xs, train_y, cv=5, scoring="roc_auc")
        clf.fit(Xs, train_y)
        print(f"  5-fold CV AUC (predicting bad_trade on TRAIN, in-sample-ish): "
              f"{cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")
        coefs = pd.Series(clf.coef_[0], index=BAD_TRADE_FEATURES).sort_values(key=abs, ascending=False)
        print("  Feature coefficients (standardized, sign = direction toward BAD trade):")
        for feat, c in coefs.items():
            print(f"    {feat:<18} {c:>+7.3f}")

        # Apply to VALIDATION: filter out entries the TRAIN-fit classifier scores as high bad-trade risk.
        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()
        val_filtered_mask = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        val_trades = build_trades_with_mae_mfe(val_close, val_filtered_mask, val_ema_slope, val_ret_1)

        val_feat_arr = val_feats[BAD_TRADE_FEATURES].to_numpy()
        val_X, val_returns, val_ok = [], [], []
        for t in val_trades:
            i = t["entry_idx"]
            ret = resolve_exit_return(t["close_path"], stop_distance, leverage)
            val_returns.append(ret)
            val_X.append(val_feat_arr[i])
        val_X = np.array(val_X, dtype=float)
        val_bad_proba = clf.predict_proba(scaler.transform(val_X))[:, 1]

        baseline = simulate_from_returns(val_returns, leverage)
        print(f"\n  BASELINE (no bad-trade filter): n={baseline.get('n_trades',0)} "
              f"PF={baseline.get('profit_factor',float('nan')):.3f} "
              f"ret={baseline.get('total_return_pct',float('nan')):+.3f}% "
              f"win%={baseline.get('win_rate_pct',float('nan')):.1f}")

        train_bad_proba = clf.predict_proba(Xs)[:, 1]
        for pct in [50, 60, 70]:
            cutoff = np.percentile(train_bad_proba, pct)
            keep_mask = val_bad_proba < cutoff
            kept_returns = [r for r, k in zip(val_returns, keep_mask) if k]
            r = simulate_from_returns(kept_returns, leverage)
            print(f"  + filter (drop top {100-pct}% predicted-bad, TRAIN cutoff): "
                  f"n={r.get('n_trades',0)} PF={r.get('profit_factor',float('nan')):.3f} "
                  f"ret={r.get('total_return_pct',float('nan')):+.3f}% "
                  f"win%={r.get('win_rate_pct',float('nan')):.1f}")
        print()


if __name__ == "__main__":
    main()
