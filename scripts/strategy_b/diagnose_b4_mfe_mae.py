"""scripts/strategy_b/diagnose_b4_mfe_mae.py — STRATEGY_ID = B, diagnostic
(not a new experiment card): for B4's trend-regime-gated breakout entries
on the VALIDATION split, report the RAW MFE/MAE distribution (the best
and worst excursion available to ANY exit design) before any exit rule is
applied. Purpose: distinguish "dead entry signal" (price doesn't move
favorably even at the best possible exit) from "wrong exit design"
(favorable movement exists but the borrowed trailing-stop mechanic cuts
it short). Does not change any pre-registered verdict by itself.

Usage:
    python scripts/strategy_b/diagnose_b4_mfe_mae.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix
from scripts.phase3_baseline import load_split
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BREAKOUT_LOOKBACK = 60
VOL_EXPANSION_RATIO = 1.5
VOLUME_RATIO = 1.5
HURST_TREND_GATE = 0.5
FEE_PER_SIDE = 0.0005
BASE_SLIP_PER_SIDE = 0.0001
ROUND_TRIP_COST = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2

SYMBOLS = ["BTCUSDT", "ETHUSDT"]


def compute_entries(df: pd.DataFrame, feats: pd.DataFrame) -> np.ndarray:
    breakout_level = df["high"].rolling(BREAKOUT_LOOKBACK).max().shift(1)
    breakout = df["close"] > breakout_level
    vol_ok = feats["realized_vol_ratio"] > VOL_EXPANSION_RATIO
    volume_ok = feats["rel_volume_20"] > VOLUME_RATIO
    trend_ok = feats["hurst_120"] > HURST_TREND_GATE
    return (breakout.to_numpy() & vol_ok.to_numpy() & volume_ok.to_numpy() & trend_ok.to_numpy())


def diagnose(symbol: str) -> dict:
    val_df = load_split(symbol, "validation", verbose=False)
    val_feats = build_feature_matrix(val_df)
    entries = compute_entries(val_df, val_feats)
    val_close = val_df["close"].to_numpy()
    trades = build_trades(val_close, entries, val_feats["ema_slope_20"].to_numpy(), val_feats["ret_1"].to_numpy())
    if len(trades) == 0:
        return {"symbol": symbol, "status": "NO_TRADES"}

    mfe = np.array([t["mfe"] for t in trades])
    mae = np.array([t["mae"] for t in trades])
    final = np.array([t["close_path"][-1] for t in trades])

    return {
        "symbol": symbol, "status": "OK", "n_trades": len(trades),
        "mfe_mean_pct": round(float(mfe.mean()) * 100, 4),
        "mfe_median_pct": round(float(np.median(mfe)) * 100, 4),
        "mae_mean_pct": round(float(mae.mean()) * 100, 4),
        "mae_median_pct": round(float(np.median(mae)) * 100, 4),
        "final_mean_pct": round(float(final.mean()) * 100, 4),
        "final_median_pct": round(float(np.median(final)) * 100, 4),
        "pct_mfe_gt_roundtrip_cost": round(float((mfe > ROUND_TRIP_COST).mean()) * 100, 2),
        "pct_final_positive": round(float((final > 0).mean()) * 100, 2),
        "best_possible_pf": round(float(np.clip(mfe, 0, None).sum() / max(1e-9, np.clip(mae, 0, None).sum())), 3),
        "round_trip_cost_pct": round(ROUND_TRIP_COST * 100, 4),
    }


def main():
    print("=" * 100)
    print("  STRATEGY B -- diagnostic: raw MFE/MAE on B4 entries (VALIDATION), before any exit rule")
    print("=" * 100)
    results = [diagnose(s) for s in SYMBOLS]
    for r in results:
        print(f"\n{r}")
    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "strategy_b", "strategy_b_diagnose_b4_mfe_mae.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
