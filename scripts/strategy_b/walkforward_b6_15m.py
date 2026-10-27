"""scripts/strategy_b/walkforward_b6_15m.py — STRATEGY_ID = B, Experiment
B6: real walk-forward (expanding TRAIN, fixed 3-month TEST, 3-month step,
same fold construction as Strategy A's scripts/walk_forward_engine.py,
reused as shared infrastructure per STRATEGY_B_SPEC.md Section 10) for
the B5 entry concept (15-minute bars, breakout N=60 + vol_ratio>1.5 +
volume_ratio>1.5 + hurst_120>0.5 trend gate), frozen/untuned across folds
-- only TRAIN-derived stop/activate/trail/leverage are recalibrated per
fold (same discipline as Strategy A), the ENTRY RULE itself never
changes. HOLDOUT is never touched (folds bounded by SAFE_END = min(BTC,
ETH HOLDOUT_START), imported from walk_forward_engine.py, not
re-derived).

Usage:
    python scripts/strategy_b/walkforward_b6_15m.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix
from scripts.phase3_baseline import _load_full
from scripts.walk_forward_engine import build_folds, HOLDOUT_START, SAFE_END
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESAMPLE_RULE = "15min"
BREAKOUT_LOOKBACK = 60
VOL_EXPANSION_RATIO = 1.5
VOLUME_RATIO = 1.5
HURST_TREND_GATE = 0.5
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = 0.0005
BASE_SLIP_PER_SIDE = 0.0001

SYMBOLS = ["BTCUSDT", "ETHUSDT"]


def resample_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    for extra_sum_col in ("taker_buy_volume", "taker_sell_volume", "quote_volume", "trades"):
        if extra_sum_col in df.columns:
            agg[extra_sum_col] = "sum"
    out = df.resample(RESAMPLE_RULE).agg(agg).dropna(subset=["open", "high", "low", "close", "volume"])
    return out


def compute_entries(df: pd.DataFrame, feats: pd.DataFrame) -> np.ndarray:
    breakout_level = df["high"].rolling(BREAKOUT_LOOKBACK).max().shift(1)
    breakout = df["close"] > breakout_level
    vol_ok = feats["realized_vol_ratio"] > VOL_EXPANSION_RATIO
    volume_ok = feats["rel_volume_20"] > VOLUME_RATIO
    trend_ok = feats["hurst_120"] > HURST_TREND_GATE
    return (breakout.to_numpy() & vol_ok.to_numpy() & volume_ok.to_numpy() & trend_ok.to_numpy())


def resolve_trailing(path: np.ndarray, protective: float, activate_at: float, trail_dist: float, fee_slip: float):
    peak, activated = -np.inf, False
    for j, x in enumerate(path):
        if x <= -protective:
            return -protective - fee_slip, True, j
        if x > peak:
            peak = x
        if not activated and peak >= activate_at:
            activated = True
        if activated:
            stop_level = peak - trail_dist
            if x <= stop_level:
                return stop_level - fee_slip, False, j
    return path[-1] - fee_slip, False, len(path) - 1


def run_fold(symbol: str, full_df: pd.DataFrame, data_start, train_end, test_end) -> dict:
    train_df = resample_ohlcv(full_df.loc[(full_df.index >= data_start) & (full_df.index < train_end)])
    test_df = resample_ohlcv(full_df.loc[(full_df.index >= train_end) & (full_df.index < test_end)])
    if len(train_df) < 500 or len(test_df) < 20:
        return {"symbol": symbol, "train_end": train_end, "test_end": test_end, "status": "INSUFFICIENT_BARS"}

    train_feats = build_feature_matrix(train_df)
    test_feats = build_feature_matrix(test_df)
    train_entries = compute_entries(train_df, train_feats)
    test_entries = compute_entries(test_df, test_feats)

    train_close = train_df["close"].to_numpy()
    train_trades = build_trades(train_close, train_entries, train_feats["ema_slope_20"].to_numpy(), train_feats["ret_1"].to_numpy())
    if len(train_trades) < 10:
        return {"symbol": symbol, "train_end": train_end, "test_end": test_end, "status": "INSUFFICIENT_TRAIN_TRADES", "n_train_trades": len(train_trades)}

    maes = np.abs([t["mae"] for t in train_trades])
    stop_distance = float(np.percentile(maes, STOP_PCT_PERCENTILE))
    mfes_pos = [t["mfe"] for t in train_trades if t["mfe"] > 0]
    activate_at = float(np.percentile(mfes_pos, 50)) if mfes_pos else stop_distance * 0.5
    trail_dist = stop_distance * 0.5
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    fee_slip = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2

    test_close = test_df["close"].to_numpy()
    test_trades = build_trades(test_close, test_entries, test_feats["ema_slope_20"].to_numpy(), test_feats["ret_1"].to_numpy())
    if len(test_trades) == 0:
        return {"symbol": symbol, "train_end": train_end, "test_end": test_end, "status": "NO_TEST_TRADES"}

    returns, forced = [], 0
    for t in test_trades:
        ret, was_forced, _ = resolve_trailing(t["close_path"], protective, activate_at, trail_dist, fee_slip)
        returns.append(ret)
        forced += int(was_forced and liq_move <= stop_distance)
    returns = np.array(returns)
    wins, losses = returns[returns > 0], returns[returns <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {
        "symbol": symbol, "train_end": str(train_end.date()), "test_end": str(test_end.date()),
        "status": "OK", "n_trades": len(returns), "pf": round(pf, 3),
        "win_rate_pct": round(float((returns > 0).mean() * 100), 1),
        "total_return_pct_unlevered": round(float(returns.sum() * 100), 3),
        "forced_liq": forced, "leverage": round(leverage, 2),
    }


def main():
    print("=" * 100)
    print("  STRATEGY B -- Experiment B6: 15-min walk-forward (frozen B5 entry concept)")
    print("=" * 100)

    full = {s: _load_full(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)
    print(f"  {len(folds)} folds, data_start={data_start.date()}, SAFE_END={SAFE_END.date()}")
    for s in SYMBOLS:
        print(f"  HOLDOUT_START[{s}]={HOLDOUT_START[s].date()}")

    all_results = []
    for (ds, te, tend) in folds:
        for symbol in SYMBOLS:
            r = run_fold(symbol, full[symbol], ds, te, tend)
            all_results.append(r)
            print(f"  fold train_end={te.date()} test_end={tend.date()} {symbol}: {r}")

    df_res = pd.DataFrame(all_results)
    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "strategy_b", "strategy_b_walkforward_b6_15m.csv")
    df_res.to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    print("\n" + "=" * 100)
    print("  WALK-FORWARD SUMMARY (Experiment B6)")
    print("=" * 100)
    ok = df_res[df_res["status"] == "OK"]
    for symbol in SYMBOLS:
        sub = ok[ok["symbol"] == symbol]
        if len(sub) == 0:
            print(f"  {symbol}: no OK folds")
            continue
        median_pf = sub["pf"].median()
        pct_folds_pf_gt1 = (sub["pf"] > 1.0).mean() * 100
        n_total = sub["n_trades"].sum()
        total_forced = sub["forced_liq"].sum()
        print(f"  {symbol}: n_folds={len(sub)}  median_PF={median_pf:.3f}  %folds_PF>1={pct_folds_pf_gt1:.1f}%  "
              f"n_total_trades={n_total}  forced_liq={total_forced}")


if __name__ == "__main__":
    main()
