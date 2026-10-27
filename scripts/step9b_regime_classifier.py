"""
scripts/step9b_regime_classifier.py — Étape 9 (user's revised priority):
a proper 2-D market regime (trend/range x low/high vol) rather than the
single-dimension volatility filter (Experiment 4) or the vol x hour-of-day
EV table (Experiment 12/19). Uses hurst_120 (already in the feature set,
Hurst exponent: >0.5 = trending/persistent, <=0.5 = mean-reverting/range)
crossed with realized_vol_30 tercile -- both TRAIN-calibrated cutoffs,
never VALIDATION.

This directly tests whether TREND vs RANGE is informative beyond what
volatility alone (Experiment 4) or vol x hour (Experiment 12) already
captured, using a feature explicitly designed to measure trend persistence
rather than a calendar proxy (hour-of-day).

Reports the regime x performance breakdown, then tests the EV>0 filter
built from THIS grid (same methodology as Experiment 12) on VALIDATION.

Usage:
    python scripts/step9b_regime_classifier.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

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


def regime_of(entry_idx, hurst_arr, vol_arr, vol_tertiles, hurst_median):
    trend = "TREND" if hurst_arr[entry_idx] > hurst_median else "RANGE"
    v = vol_arr[entry_idx]
    vol_bucket = "LOWVOL" if v <= vol_tertiles[0] else ("MIDVOL" if v <= vol_tertiles[1] else "HIGHVOL")
    return (trend, vol_bucket)


def simulate(returns, leverage) -> dict:
    pnls = np.array(returns) * CAPITAL * RISK_PCT * leverage
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3)}


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
    print(f"{len(kept)} features kept ('hurst_120' in set: {'hurst_120' in kept}).\n")

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

        train_hurst = train_feats["hurst_120"].to_numpy()
        train_vol = train_feats["realized_vol_30"].to_numpy()
        entry_idxs = [t["entry_idx"] for t in train_trades]
        hurst_median = np.nanmedian(train_hurst[entry_idxs])
        vol_tertiles = np.nanpercentile(train_vol[entry_idxs], [33.3, 66.7])

        regime_rets = {}
        for t in train_trades:
            ret = resolve(t["close_path"], stop_distance, leverage)
            r = regime_of(t["entry_idx"], train_hurst, train_vol, vol_tertiles, hurst_median)
            regime_rets.setdefault(r, []).append(ret)

        print("=" * 100)
        print(f"  {symbol} — TRAIN regime table (trend/range x vol tercile), hurst_median={hurst_median:.3f}")
        print("=" * 100)
        ev_table = {}
        for r, rets in sorted(regime_rets.items()):
            rets = np.array(rets)
            wins, losses = rets[rets > 0], rets[rets <= 0]
            p_win = len(wins) / len(rets)
            avg_win = wins.mean() if len(wins) else 0.0
            avg_loss = -losses.mean() if len(losses) else 0.0
            ev = p_win * avg_win - (1 - p_win) * avg_loss
            ev_table[r] = ev
            pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
            print(f"  {r[0]:<6} {r[1]:<8} n={len(rets):>4} win%={p_win*100:>5.1f} PF={pf:>7.3f} EV={ev*100:>+7.4f}%")
        good_regimes = {r for r, ev in ev_table.items() if ev > 0}

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
        val_hurst = val_feats["hurst_120"].to_numpy()
        val_vol = val_feats["realized_vol_30"].to_numpy()

        baseline_returns = [resolve(t["close_path"], stop_distance, leverage) for t in val_trades]
        r_base = simulate(baseline_returns, leverage)
        filtered_returns = [ret for t, ret in zip(val_trades, baseline_returns)
                             if regime_of(t["entry_idx"], val_hurst, val_vol, vol_tertiles, hurst_median) in good_regimes]
        r_filt = simulate(filtered_returns, leverage)

        print(f"\n  VALIDATION baseline: n={r_base.get('n_trades',0)} PF={r_base.get('profit_factor',float('nan')):.3f} "
              f"ret={r_base.get('total_return_pct',float('nan')):+.3f}%")
        print(f"  VALIDATION + regime filter (EV>0 trend/vol cells): n={r_filt.get('n_trades',0)} "
              f"PF={r_filt.get('profit_factor',float('nan')):.3f} ret={r_filt.get('total_return_pct',float('nan')):+.3f}%")
        print()


if __name__ == "__main__":
    main()
