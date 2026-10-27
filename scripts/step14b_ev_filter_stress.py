"""
scripts/step14b_ev_filter_stress.py — immediate follow-up to Experiment 12:
does the EV>0% filter's clean win (both symbols, n barely shrinks) survive
gap stress, the same check that correctly rejected the p70 stop (6b) and
threshold=0.725 (8) leads?

Usage:
    python scripts/step14b_ev_filter_stress.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.step1_stress_test import TRAIN_SYMBOLS, HORIZON, LEVERAGE, load_funding, simulate_stressed
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

THRESHOLD = 0.75
STOP_PCT_PERCENTILE = 90


def cell_of(entry_idx, vol_arr, hour_arr, vol_tertiles):
    v = vol_arr[entry_idx]
    vol_bucket = 0 if v <= vol_tertiles[0] else (1 if v <= vol_tertiles[1] else 2)
    h = hour_arr[entry_idx]
    return (vol_bucket, h // 6)


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

        train_vol = train_feats["realized_vol_30"].to_numpy()
        train_hour = train_df.index.hour.to_numpy()
        vol_tertiles = np.nanpercentile(train_vol[[t["entry_idx"] for t in train_trades]], [33.3, 66.7])

        # EV per cell from TRAIN, using each trade's OWN close_path resolved
        # via the identical trailing+stop+time exit simulate_stressed uses
        # (gap_extra=0 baseline), for full consistency with the stress checker.
        from scripts.step1_stress_test import ACTIVATE_AT, TRAIL_DIST, FEE_PER_SIDE, BASE_SLIP_PER_SIDE
        from scripts.diagnostic_leverage import STOP_OUT_FRACTION

        def resolve(path, lev):
            liq_move = STOP_OUT_FRACTION / lev
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

        cell_rets = {}
        for t in train_trades:
            k = cell_of(t["entry_idx"], train_vol, train_hour, vol_tertiles)
            cell_rets.setdefault(k, []).append(resolve(t["close_path"], leverage))
        ev_table = {}
        for k, rets in cell_rets.items():
            rets = np.array(rets)
            wins, losses = rets[rets > 0], rets[rets <= 0]
            p_win = len(wins) / len(rets)
            avg_win = wins.mean() if len(wins) else 0.0
            avg_loss = -losses.mean() if len(losses) else 0.0
            ev_table[k] = p_win * avg_win - (1 - p_win) * avg_loss

        good_cells = {k for k, ev in ev_table.items() if ev > 0}

        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()
        val_vol = val_feats["realized_vol_30"].to_numpy()
        val_hour = val_df.index.hour.to_numpy()
        val_filtered = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        val_trades_all = build_trades_with_mae_mfe(val_close, val_filtered, val_ema_slope, val_ret_1)
        val_trades_ev = [t for t in val_trades_all
                         if cell_of(t["entry_idx"], val_vol, val_hour, vol_tertiles) in good_cells]

        funding = load_funding(symbol)
        timestamps = val_df.index

        print("=" * 100)
        print(f"  {symbol} — EV>0% filter under gap stress (baseline n={len(val_trades_all)}, "
              f"EV-filtered n={len(val_trades_ev)})")
        print("=" * 100)
        for label, trades in [("baseline (all)", val_trades_all), ("EV>0% filtered", val_trades_ev)]:
            for gap in [0.0, 0.0025, 0.0050]:
                r = simulate_stressed(trades, val_close, timestamps, funding, stop_distance, leverage, gap_extra=gap)
                print(f"    {label:<18} gap={gap*100:>5.2f}%  n={r.get('n_trades',0):>4} "
                      f"PF={r.get('profit_factor',float('nan')):>7.3f} "
                      f"ret={r.get('total_return_pct',float('nan')):>+7.3f}%")
            worst = simulate_stressed(trades, val_close, timestamps, funding, stop_distance, leverage,
                                       slip_mult_entry=2, slip_mult_trailing=2, slip_mult_stop=2,
                                       slip_mult_time=2, gap_extra=0.0025, funding_mult=2, entry_delay=1)
            print(f"    {label:<18} WORST CASE      n={worst.get('n_trades',0):>4} "
                  f"PF={worst.get('profit_factor',float('nan')):>7.3f} "
                  f"ret={worst.get('total_return_pct',float('nan')):>+7.3f}%")
        print()


if __name__ == "__main__":
    main()
