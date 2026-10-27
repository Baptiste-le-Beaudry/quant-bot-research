"""
scripts/step17b_portfolio_leverage_stress.py — stress-test Experiment 15's
portfolio leverage multiplier candidate (~1.2-1.3x uniform on both symbols'
base leverage) before considering it for BASELINE_CANDIDATE_V3. Applies
the same gap-stress dimension used throughout this session (0.25%/0.50%
fill gap + the standard combined worst case) to the COMBINED portfolio at
mult=1.0 (baseline)/1.2/1.3/1.5, since Experiment 15 already showed 1.5x
is where forced liquidations start jumping even frictionlessly.

Usage:
    python scripts/step17b_portfolio_leverage_stress.py
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
from scripts.step1_stress_test import load_funding, funding_cost_for_window

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
BASE_LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL_PER_BOOK = 10_000.0
RISK_PCT = 0.01
MULTIPLIERS = [1.0, 1.2, 1.3, 1.5]


def resolve(path, stop_distance, leverage, gap_extra=0.0, slip_mult=1.0):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    forced = liq_move <= stop_distance
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - gap_extra - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2, forced
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - gap_extra - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2, False
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2, False


def max_dd(eq, capital):
    running_max = np.maximum.accumulate(np.concatenate([[capital], eq]))
    return float(((np.concatenate([[capital], eq]) - running_max) / running_max).min() * 100)


def run_scenario(per_symbol, mult, gap_extra=0.0, slip_mult=1.0, funding_mult=0.0, entry_delay=0):
    combined_capital = CAPITAL_PER_BOOK * 2
    rows = []
    total_forced = 0
    for symbol, data in per_symbol.items():
        leverage = BASE_LEVERAGE[symbol] * mult
        close_arr, timestamps, funding = data["close_arr"], data["timestamps"], data["funding"]
        n = len(close_arr)
        for t in data["trades"]:
            i = t["entry_idx"] + entry_delay
            if i < 0 or i >= n - 51:
                continue
            entry_price = close_arr[i]
            path = close_arr[i:i + 51] / entry_price - 1.0
            ret, forced = resolve(path, data["stop_distance"], leverage, gap_extra, slip_mult)
            if funding_mult > 0:
                exit_j = min(len(path) - 1, 50)
                fcost = funding_cost_for_window(funding, timestamps[i], timestamps[min(i + exit_j, n - 1)], funding_mult)
                ret -= fcost
            pnl = ret * CAPITAL_PER_BOOK * RISK_PCT * leverage
            rows.append({"entry_time": timestamps[i], "pnl": pnl})
            total_forced += int(forced)
    if not rows:
        return {"n_trades": 0}
    df_c = pd.DataFrame(rows).sort_values("entry_time")
    pnls = df_c["pnl"].to_numpy()
    eq = combined_capital + np.cumsum(pnls)
    dd = max_dd(eq, combined_capital)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / combined_capital * 100, 3),
            "max_dd_pct": round(dd, 3), "n_forced_liq": total_forced}


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

    per_symbol = {}
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
        per_symbol[symbol] = {"trades": val_trades, "close_arr": val_close, "timestamps": val_df.index,
                               "stop_distance": stop_distance, "funding": load_funding(symbol)}

    print("=" * 100)
    print("  Portfolio leverage multiplier under stress")
    print("=" * 100)
    print(f"  {'mult':>6}{'scenario':>14}{'n':>5}{'PF':>9}{'ret%':>9}{'maxDD%':>9}{'forced_liq':>12}")
    for mult in MULTIPLIERS:
        r0 = run_scenario(per_symbol, mult)
        print(f"  {mult:>5.2f}x{'frictionless':>14}{r0.get('n_trades',0):>5}{r0.get('profit_factor',float('nan')):>9.3f}"
              f"{r0.get('total_return_pct',float('nan')):>+9.3f}{r0.get('max_dd_pct',float('nan')):>+9.3f}"
              f"{r0.get('n_forced_liq','-'):>12}")
        r25 = run_scenario(per_symbol, mult, gap_extra=0.0025)
        print(f"  {mult:>5.2f}x{'gap=0.25%':>14}{r25.get('n_trades',0):>5}{r25.get('profit_factor',float('nan')):>9.3f}"
              f"{r25.get('total_return_pct',float('nan')):>+9.3f}{r25.get('max_dd_pct',float('nan')):>+9.3f}"
              f"{r25.get('n_forced_liq','-'):>12}")
        r50 = run_scenario(per_symbol, mult, gap_extra=0.0050)
        print(f"  {mult:>5.2f}x{'gap=0.50%':>14}{r50.get('n_trades',0):>5}{r50.get('profit_factor',float('nan')):>9.3f}"
              f"{r50.get('total_return_pct',float('nan')):>+9.3f}{r50.get('max_dd_pct',float('nan')):>+9.3f}"
              f"{r50.get('n_forced_liq','-'):>12}")
        rw = run_scenario(per_symbol, mult, gap_extra=0.0025, slip_mult=2.0, funding_mult=2.0, entry_delay=1)
        print(f"  {mult:>5.2f}x{'WORST CASE':>14}{rw.get('n_trades',0):>5}{rw.get('profit_factor',float('nan')):>9.3f}"
              f"{rw.get('total_return_pct',float('nan')):>+9.3f}{rw.get('max_dd_pct',float('nan')):>+9.3f}"
              f"{rw.get('n_forced_liq','-'):>12}")
        print()


if __name__ == "__main__":
    main()
