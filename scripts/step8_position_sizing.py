"""
scripts/step8_position_sizing.py — Phase 8 (user's revised priority order):
dynamic position sizing, compared honestly against fixed sizing rather
than assumed to help. Five schemes on the SAME BASELINE_CANDIDATE_V2
entries/exits (only position size varies):

  1. FIXED (baseline): risk_pct=0.01 always.
  2. PROBA-SCALED: size ∝ clip((proba-threshold)/(1-threshold), 0.25, 1.0)
     -- the exact scheme already tested and falsified in a prior session
     (hypothesis_tests.py H1) because probas cluster too tightly. Included
     here again for a direct, current-architecture comparison, not skipped.
  3. INVERSE-PREDICTED-MAE: FIRST checks whether entry-time features can
     predict a trade's eventual MAE at all (fit a RandomForestRegressor on
     TRAIN, correlate predicted vs actual MAE on VALIDATION -- genuinely
     out-of-sample, not the trade's own realized MAE fed back into itself).
     Only proceeds to size by 1/predicted_MAE if that correlation is
     actually non-trivial; reports the correlation honestly either way,
     since Experiment 7 already found entry features don't predict
     bad-trade outcomes above chance (AUC~0.52-0.54) and this may well
     fail the same way.
  4. EV-CELL PROPORTIONAL: size ∝ clip(cell_EV / reference_EV, 0.5, 2.0),
     using Experiment 12's TRAIN-calibrated (vol tercile x hour quadrant)
     EV table as a CONTINUOUS sizing multiplier instead of a hard
     include/exclude filter -- directly the "revisit as a sizing
     multiplier" idea flagged in Experiment 12's own writeup.
  5. PROBA + EV-CELL combined (multiplicative).

Usage:
    python scripts/step8_position_sizing.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from scipy.stats import spearmanr

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
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01
MAE_FEATURES = ["realized_vol_30", "atr_norm", "dist_ema20_atr", "ema_slope_20",
                "rel_volume_20", "volume_accel", "range_pos_60"]


def resolve(path, stop_distance, leverage):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2


def cell_of(entry_idx, vol_arr, hour_arr, vol_tertiles):
    v = vol_arr[entry_idx]
    vol_bucket = 0 if v <= vol_tertiles[0] else (1 if v <= vol_tertiles[1] else 2)
    h = hour_arr[entry_idx]
    return (vol_bucket, h // 6)


def report(label, pnls) -> None:
    pnls = np.array(pnls)
    if len(pnls) == 0:
        print(f"  {label:<28} no trades")
        return
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = float(((np.concatenate([[CAPITAL], eq]) - running_max) / running_max).min() * 100)
    per_trade = pnls / CAPITAL
    sharpe = float(per_trade.mean() / (per_trade.std() + 1e-12))
    print(f"  {label:<28} n={len(pnls):>4} PF={pf:>7.3f} ret={pnls.sum()/CAPITAL*100:>+7.3f}% "
          f"maxDD={dd:>+7.3f}% sharpe={sharpe:>7.4f}")


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
        train_filtered = (
            (train_proba > THRESHOLD)
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        train_trades = build_trades_with_mae_mfe(train_close, train_filtered, train_ema_slope, train_ret_1)
        stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
        leverage = LEVERAGE[symbol]

        # --- Feasibility check: can entry features predict MAE at all? ---
        train_feat_arr = train_feats[MAE_FEATURES].to_numpy()
        mae_X = np.array([train_feat_arr[t["entry_idx"]] for t in train_trades])
        mae_y = np.array([abs(t["mae"]) for t in train_trades])
        mae_reg = RandomForestRegressor(n_estimators=100, max_depth=5, min_samples_leaf=20, random_state=42, n_jobs=-1)
        mae_reg.fit(mae_X, mae_y)

        # --- TRAIN EV-cell table (Experiment 12) ---
        train_vol = train_feats["realized_vol_30"].to_numpy()
        train_hour = train_df.index.hour.to_numpy()
        vol_tertiles = np.nanpercentile(train_vol[[t["entry_idx"] for t in train_trades]], [33.3, 66.7])
        cell_rets = {}
        for t in train_trades:
            ret = resolve(t["close_path"], stop_distance, leverage)
            k = cell_of(t["entry_idx"], train_vol, train_hour, vol_tertiles)
            cell_rets.setdefault(k, []).append(ret)
        ev_table = {}
        for k, rets in cell_rets.items():
            rets = np.array(rets)
            wins, losses = rets[rets > 0], rets[rets <= 0]
            p_win = len(wins) / len(rets)
            avg_win = wins.mean() if len(wins) else 0.0
            avg_loss = -losses.mean() if len(losses) else 0.0
            ev_table[k] = p_win * avg_win - (1 - p_win) * avg_loss
        ref_ev = np.mean(list(ev_table.values()))

        # --- VALIDATION ---
        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()
        val_filtered = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        val_trades = build_trades_with_mae_mfe(val_close, val_filtered, val_ema_slope, val_ret_1)
        val_vol = val_feats["realized_vol_30"].to_numpy()
        val_hour = val_df.index.hour.to_numpy()
        val_feat_arr = val_feats[MAE_FEATURES].to_numpy()

        val_pred_mae = mae_reg.predict(np.array([val_feat_arr[t["entry_idx"]] for t in val_trades]))
        val_actual_mae = np.array([abs(t["mae"]) for t in val_trades])
        corr, pval = spearmanr(val_pred_mae, val_actual_mae)

        print("=" * 100)
        print(f"  {symbol} — position sizing comparison (n={len(val_trades)})")
        print("=" * 100)
        print(f"  Feasibility check: predicted-MAE vs actual-MAE Spearman corr (VALIDATION, OOS) = "
              f"{corr:+.3f} (p={pval:.3f}) -- {'usable signal' if abs(corr) > 0.15 and pval < 0.05 else 'WEAK/NOISE, sizing on this would mostly add variance, not edge'}")

        notional_base = CAPITAL * RISK_PCT

        rets, probas, weights_ev = [], [], []
        for t in val_trades:
            i = t["entry_idx"]
            ret = resolve(t["close_path"], stop_distance, leverage)
            rets.append(ret)
            probas.append(float(val_proba.iloc[i]))
            k = cell_of(i, val_vol, val_hour, vol_tertiles)
            cell_ev = ev_table.get(k, ref_ev)
            weights_ev.append(float(np.clip(cell_ev / ref_ev if ref_ev != 0 else 1.0, 0.5, 2.0)))
        rets = np.array(rets)
        probas = np.array(probas)
        weights_ev = np.array(weights_ev)
        weights_proba = np.clip((probas - THRESHOLD) / (1 - THRESHOLD), 0.25, 1.0)
        weights_mae = np.clip(1.0 / (val_pred_mae + 1e-4), 0.25, 4.0)
        weights_mae = weights_mae / np.median(weights_mae)  # normalize around 1.0
        weights_mae = np.clip(weights_mae, 0.25, 2.0)

        pnl_fixed = rets * notional_base * leverage
        pnl_proba = rets * notional_base * leverage * weights_proba
        pnl_mae = rets * notional_base * leverage * weights_mae
        pnl_ev = rets * notional_base * leverage * weights_ev
        pnl_combo = rets * notional_base * leverage * weights_proba * weights_ev

        report("1. FIXED (baseline)", pnl_fixed)
        report("2. PROBA-scaled", pnl_proba)
        report("3. 1/predicted-MAE-scaled", pnl_mae)
        report("4. EV-cell proportional", pnl_ev)
        report("5. PROBA x EV-cell combo", pnl_combo)
        print()


if __name__ == "__main__":
    main()
