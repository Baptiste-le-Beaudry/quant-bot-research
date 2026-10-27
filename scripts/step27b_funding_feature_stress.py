"""
scripts/step27b_funding_feature_stress.py — stress-test Experiment 18's
funding-feature candidate (both symbols improved PF ~25-30% frictionless)
before trusting it. Same gap-stress dimension used throughout this session.

Usage:
    python scripts/step27b_funding_feature_stress.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR, COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.step1_stress_test import load_funding as load_funding_cost, funding_cost_for_window
from scripts.step27_funding_feature import load_funding_full, add_funding_feature

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


def resolve(path, stop_distance, leverage, gap_extra=0.0, slip_mult=1.0):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - gap_extra - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - gap_extra - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2


def simulate(trades, close_arr, timestamps, funding, stop_distance, leverage,
             gap_extra=0.0, slip_mult=1.0, funding_mult=0.0, entry_delay=0) -> dict:
    n = len(close_arr)
    pnls = []
    for t in trades:
        i = t["entry_idx"] + entry_delay
        if i < 0 or i >= n - 51:
            continue
        entry_price = close_arr[i]
        path = close_arr[i:i + 51] / entry_price - 1.0
        ret = resolve(path, stop_distance, leverage, gap_extra, slip_mult)
        if funding_mult > 0:
            exit_j = min(len(path) - 1, 50)
            fcost = funding_cost_for_window(funding, timestamps[i], timestamps[min(i + exit_j, n - 1)], funding_mult)
            ret -= fcost
        pnls.append(ret * CAPITAL * RISK_PCT * leverage)
    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3)}


def get_trades(symbol, model, use_funding, funding_series_full):
    train_df = load_split(symbol, "train", verbose=False)
    train_feats = build_feature_matrix(train_df)
    if use_funding:
        train_feats = add_funding_feature(train_feats, funding_series_full[symbol])
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

    val_df = load_split(symbol, "validation", verbose=False)
    val_feats = build_feature_matrix(val_df)
    if use_funding:
        val_feats = add_funding_feature(val_feats, funding_series_full[symbol])
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
    return val_trades, val_close, val_df.index, stop_distance


def fit_model(use_funding, funding_series_full):
    train_feats_all, train_labels_all = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        feats = build_feature_matrix(df)
        if use_funding:
            feats = add_funding_feature(feats, funding_series_full[symbol])
        train_feats_all[symbol] = feats
        train_labels_all[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train = pd.concat(train_labels_all.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    return Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])


def main():
    funding_series_full = {s: load_funding_full(s) for s in TRAIN_SYMBOLS}
    funding_cost_series = {s: load_funding_cost(s) for s in TRAIN_SYMBOLS}

    for use_funding in [False, True]:
        label = "WITH funding feature" if use_funding else "WITHOUT funding (baseline)"
        print("=" * 100)
        print(f"  {label}")
        print("=" * 100)
        model = fit_model(use_funding, funding_series_full)
        for symbol in ["ETHUSDT", "BTCUSDT"]:
            trades, close_arr, timestamps, stop_distance = get_trades(symbol, model, use_funding, funding_series_full)
            leverage = LEVERAGE[symbol]
            funding = funding_cost_series[symbol]
            print(f"\n  {symbol} (n_entries={len(trades)}, stop={stop_distance*100:.2f}%):")
            for gap in [0.0, 0.0025, 0.0050]:
                r = simulate(trades, close_arr, timestamps, funding, stop_distance, leverage, gap_extra=gap)
                print(f"    gap={gap*100:>5.2f}%  n={r.get('n_trades',0):>4} "
                      f"PF={r.get('profit_factor',float('nan')):>7.3f} "
                      f"ret={r.get('total_return_pct',float('nan')):>+7.3f}%")
            worst = simulate(trades, close_arr, timestamps, funding, stop_distance, leverage,
                              gap_extra=0.0025, slip_mult=2.0, funding_mult=2.0, entry_delay=1)
            print(f"    WORST CASE      n={worst.get('n_trades',0):>4} "
                  f"PF={worst.get('profit_factor',float('nan')):>7.3f} "
                  f"ret={worst.get('total_return_pct',float('nan')):>+7.3f}%")
        print()


if __name__ == "__main__":
    main()
