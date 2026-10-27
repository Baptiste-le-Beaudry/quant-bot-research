"""
scripts/short_side_test.py — hypothesis: does the entry-filter +
trend-gated-rescue approach (this session's best long-side result) work on
the SHORT side too? Everything mirrored:
  - label: build_labels(..., direction="short") (P(fwd return < -cost))
  - entry filter: near recent HIGH (range_pos_60 > 1-cutoff) + elevated vol,
    cutoffs computed on the symbol's own TRAIN-selected population (same
    discipline as the long side)
  - rescue leg: only opens once a DOWNTREND resumes (ema_slope_20<0 AND
    ret_1<0), mirroring the long side's uptrend-confirmation gate
  - dedicated (not jointly-trained) model per symbol, since that was just
    confirmed this session to be a real, general improvement over joint
    training on the long side

Usage:
    python scripts/short_side_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from quant_bot.backtest.engine import buy_and_hold
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HORIZON = 10
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
EXTENSION_CAP = 40
CAPITAL = 10_000.0
RISK_PCT = 0.01
THRESHOLDS_TO_TRY = [0.55, 0.60, 0.65, 0.70, 0.75]


def simulate_short_trend_rescue(close_arr: np.ndarray, entry_mask: np.ndarray,
                                 ema_slope: np.ndarray, ret_1: np.ndarray, extension_cap: int) -> dict:
    """Mirror of simulate_trend_rescue (hypothesis_tests.py) for shorts:
    profit = entry_price/exit_price - 1 (price falling = profit). Rescue
    leg opens once a downtrend resumes (ema_slope<0 and ret_1<0), same idea
    as the long side's uptrend gate but inverted."""
    n = len(close_arr)
    notional = CAPITAL * RISK_PCT
    pnls, is_rescued = [], []

    i = 0
    while i < n - HORIZON - extension_cap - 1:
        if not entry_mask[i]:
            i += 1
            continue

        entry_price = close_arr[i]
        base_exit_price = close_arr[i + HORIZON]
        base_return = (entry_price / base_exit_price - 1.0) - COST_PCT

        if base_return >= 0:
            pnls.append(notional * base_return)
            is_rescued.append(False)
            i += HORIZON
            continue

        target = entry_price  # take-profit: price back down to original entry
        leg2_opened, entry_price2 = False, None
        exit_offset = HORIZON + extension_cap
        exit_price = close_arr[i + exit_offset]
        rescued = False
        for j in range(HORIZON, HORIZON + extension_cap + 1):
            p = close_arr[i + j]
            if p <= target:
                exit_price, exit_offset, rescued = p, j, leg2_opened
                break
            if not leg2_opened and ema_slope[i + j] < 0 and ret_1[i + j] < 0:
                leg2_opened, entry_price2 = True, p
        leg1_pnl = notional * ((entry_price / exit_price - 1.0) - COST_PCT)
        if leg2_opened:
            leg2_pnl = notional * ((entry_price2 / exit_price - 1.0) - COST_PCT)
            combined = leg1_pnl + leg2_pnl
        else:
            combined = leg1_pnl
        pnls.append(combined)
        is_rescued.append(rescued)
        i += exit_offset

    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gl = -losses.sum()
    return {
        "n_trades": len(pnls),
        "win_rate_pct": round((pnls > 0).mean() * 100, 2),
        "profit_factor": round(float(wins.sum() / gl), 3) if gl > 0 else float("inf"),
        "total_return_pct_of_capital": round(float(pnls.sum() / CAPITAL * 100), 3),
        "n_rescued": int(sum(is_rescued)),
    }


def run_symbol(symbol: str):
    print("=" * 80)
    print(f"  SHORT-SIDE TEST — {symbol} (dedicated model, mirrored entry filter + rescue)")
    print("=" * 80)

    train_df = load_split(symbol, "train", verbose=True)
    train_feats = build_feature_matrix(train_df)
    y_train = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="short")
    print(f"Short-label positive rate on TRAIN: {y_train.mean()*100:.2f}%")

    kept, _ = prune_redundant(train_feats, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(
        train_feats.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.")

    val_df = load_split(symbol, "validation", verbose=True)
    val_feats = build_feature_matrix(val_df)
    val_close = val_df["close"]
    y_val = build_labels(val_close, HORIZON, COST_THRESHOLD_PCT, direction="short")
    proba_val = model.predict_proba(val_feats)
    valid = proba_val.notna() & y_val.notna()
    if y_val[valid].nunique() < 2:
        print("Not enough label variety on VALIDATION for AUC -- skipping.")
        return
    auc = roc_auc_score(y_val[valid], proba_val[valid])
    bh = buy_and_hold(val_close)
    print(f"Short model AUC on VALIDATION: {auc:.4f}")
    print(f"Buy & hold (long) over VALIDATION: {bh['total_return_pct']:+.2f}% "
          f"(a short-only strategy's natural edge shows up when this is very negative)\n")

    close_arr = val_close.to_numpy()
    ema_slope_arr = val_feats["ema_slope_20"].to_numpy()
    ret_1_arr = val_feats["ret_1"].to_numpy()

    print(f"{'threshold':>10}{'n_filtered_entries':>20}{'n_trades':>10}{'win%':>8}"
          f"{'PF':>8}{'total_ret%':>12}")
    print("-" * 70)
    for thresh in THRESHOLDS_TO_TRY:
        train_proba = model.predict_proba(train_feats)
        train_selected = train_proba > thresh
        if train_selected.sum() < 20:
            print(f"{thresh:>10.2f}{'(train pop < 20)':>20}")
            continue
        range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
        vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()

        filtered_mask = (
            (proba_val > thresh)
            & (val_feats["range_pos_60"] > range_pos_cut)  # mirrored: near recent HIGH, not low
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()

        m = simulate_short_trend_rescue(close_arr, filtered_mask, ema_slope_arr, ret_1_arr, EXTENSION_CAP)
        if m.get("n_trades", 0) == 0:
            print(f"{thresh:>10.2f}{int(filtered_mask.sum()):>20}{'no trades':>10}")
            continue
        print(f"{thresh:>10.2f}{int(filtered_mask.sum()):>20}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
              f"{m['profit_factor']:>8.3f}{m['total_return_pct_of_capital']:>12.3f}")
    print()


def main():
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        run_symbol(symbol)


if __name__ == "__main__":
    main()
