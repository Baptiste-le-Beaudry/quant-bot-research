"""
scripts/step7_entry_timing.py — Étape 7: does the entry timing itself
(immediate vs delayed vs limit-retrace) matter, independent of WHICH bars
qualify (that's the entry filter, unchanged)? Three variants tested
against BASELINE_CANDIDATE_V2's immediate-entry baseline:
  A. Immediate (baseline): enter at the signal bar's own close.
  B. Delayed 1-3min: enter at close[signal_idx + delay] instead (note:
     this is the SAME mechanic Experiment 1's latency stress used, but
     tested here as a DELIBERATE strategy choice with its own TRAIN-
     calibrated stop, not as a friction assumption on top of the
     immediate-entry baseline).
  C. Limit retrace -0.10%/-0.20%/-0.30%: wait (up to the 50min window) for
     price to pull back to signal_price*(1-X%) before entering; skip the
     trade entirely if it never retraces that far in time. The remaining
     window (for stop/trailing/time-exit purposes) starts from the actual
     fill bar, not the signal bar.

Usage:
    python scripts/step7_entry_timing.py
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
EXTENSION_CAP = 40
LOOKAHEAD = HORIZON + EXTENSION_CAP
THRESHOLD = 0.75
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01


def resolve_from_entry(close_arr, entry_i, entry_price, stop_distance, leverage, remaining_window):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    path = close_arr[entry_i:entry_i + remaining_window + 1] / entry_price - 1.0
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


def simulate_immediate_or_delayed(trades, close_arr, n, stop_distance, leverage, delay: int):
    rets = []
    for t in trades:
        i = t["entry_idx"] + delay
        if i < 0 or i >= n - LOOKAHEAD - 1:
            continue
        entry_price = close_arr[i]
        remaining = LOOKAHEAD - delay if delay <= LOOKAHEAD else 0
        if remaining <= 0:
            continue
        rets.append(resolve_from_entry(close_arr, i, entry_price, stop_distance, leverage, remaining))
    return rets


def simulate_limit_retrace(trades, close_arr, n, stop_distance, leverage, retrace_pct: float):
    rets = []
    for t in trades:
        i0 = t["entry_idx"]
        if i0 >= n - LOOKAHEAD - 1:
            continue
        signal_price = close_arr[i0]
        target = signal_price * (1 - retrace_pct)
        filled_i = None
        for j in range(0, LOOKAHEAD + 1):
            if close_arr[i0 + j] <= target:
                filled_i = i0 + j
                break
        if filled_i is None:
            continue  # never retraced -- no trade
        remaining = LOOKAHEAD - (filled_i - i0)
        if remaining <= 0:
            continue
        rets.append(resolve_from_entry(close_arr, filled_i, target, stop_distance, leverage, remaining))
    return rets


def simulate(rets, leverage) -> dict:
    pnls = np.array(rets) * CAPITAL * RISK_PCT * leverage
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
        train_filtered = (
            (train_proba > THRESHOLD)
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        train_trades = build_trades_with_mae_mfe(train_close, train_filtered, train_ema_slope, train_ret_1)
        stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
        leverage = LEVERAGE[symbol]

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
        n = len(val_close)

        print("=" * 100)
        print(f"  {symbol} — entry timing (n_signals={len(val_trades)}, stop={stop_distance*100:.2f}%)")
        print("=" * 100)

        r_imm = simulate(simulate_immediate_or_delayed(val_trades, val_close, n, stop_distance, leverage, 0), leverage)
        print(f"  A. Immediate (baseline): n={r_imm.get('n_trades',0):>4} "
              f"PF={r_imm.get('profit_factor',float('nan')):>7.3f} "
              f"ret={r_imm.get('total_return_pct',float('nan')):>+7.3f}%")

        for delay in [1, 2, 3]:
            r = simulate(simulate_immediate_or_delayed(val_trades, val_close, n, stop_distance, leverage, delay), leverage)
            print(f"  B. Delayed {delay}min:          n={r.get('n_trades',0):>4} "
                  f"PF={r.get('profit_factor',float('nan')):>7.3f} "
                  f"ret={r.get('total_return_pct',float('nan')):>+7.3f}%")

        for retrace in [0.001, 0.002, 0.003]:
            rets = simulate_limit_retrace(val_trades, val_close, n, stop_distance, leverage, retrace)
            r = simulate(rets, leverage)
            print(f"  C. Limit retrace -{retrace*100:.2f}%:    n={r.get('n_trades',0):>4} "
                  f"PF={r.get('profit_factor',float('nan')):>7.3f} "
                  f"ret={r.get('total_return_pct',float('nan')):>+7.3f}%  "
                  f"(fill rate: {r.get('n_trades',0)}/{len(val_trades)})")
        print()


if __name__ == "__main__":
    main()
