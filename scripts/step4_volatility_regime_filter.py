"""
scripts/step4_volatility_regime_filter.py — Étape 15 pulled forward: the
Experiment 3 bucket analysis found realized_vol_30's top quartile at entry
carries most of the edge (PF=8.333, n=33) vs the bottom 3 quartiles
(PF 0.86-1.28). This tests whether adding that as an EXPLICIT additional
entry filter -- with the cutoff computed on TRAIN's own filtered
population, never on VALIDATION -- actually improves BASELINE_CANDIDATE_V2
out-of-sample, or whether the bucket split was mostly noise.

Usage:
    python scripts/step4_volatility_regime_filter.py
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
TRAIL_DIST = 0.0080  # V2
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0


def simulate(trades, leverage, stop_distance) -> dict:
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = 10_000.0 * 0.01
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
            "total_return_pct": round(pnls.sum() / 10_000.0 * 100, 3),
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

        # NEW: additional volatility-regime cutoff, computed on TRAIN's own
        # filtered population's realized_vol_30 (top quartile = p75), never on VALIDATION.
        base_filter_train = (
            (train_proba > THRESHOLD)
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        )
        vol_p75_cut = train_feats.loc[base_filter_train, "realized_vol_30"].quantile(0.75)

        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()

        base_mask = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        regime_mask = base_mask & (val_feats["realized_vol_30"] > vol_p75_cut).to_numpy()

        trades_base = build_trades_with_mae_mfe(val_close, base_mask, val_ema_slope, val_ret_1)
        trades_regime = build_trades_with_mae_mfe(val_close, regime_mask, val_ema_slope, val_ret_1)

        stop_base = float(np.percentile(np.abs([t["mae"] for t in trades_base]), STOP_PCT_PERCENTILE))
        stop_regime = (float(np.percentile(np.abs([t["mae"] for t in trades_regime]), STOP_PCT_PERCENTILE))
                       if len(trades_regime) >= 10 else stop_base)

        r_base = simulate(trades_base, LEVERAGE[symbol], stop_base)
        r_regime = simulate(trades_regime, LEVERAGE[symbol], stop_regime)

        print("=" * 100)
        print(f"  {symbol} — TRAIN p75 realized_vol_30 cutoff (on already-filtered pop) = {vol_p75_cut:.6f}")
        print("=" * 100)
        print(f"  BASELINE_CANDIDATE_V2 (no regime filter): n={r_base.get('n_trades',0):>4} "
              f"PF={r_base.get('profit_factor',float('nan')):>7.3f} "
              f"ret={r_base.get('total_return_pct',float('nan')):>+7.3f}% "
              f"win%={r_base.get('win_rate_pct',float('nan')):>5.1f}")
        print(f"  + volatility regime filter (top quartile): n={r_regime.get('n_trades',0):>4} "
              f"PF={r_regime.get('profit_factor',float('nan')):>7.3f} "
              f"ret={r_regime.get('total_return_pct',float('nan')):>+7.3f}% "
              f"win%={r_regime.get('win_rate_pct',float('nan')):>5.1f}")
        print()


if __name__ == "__main__":
    main()
