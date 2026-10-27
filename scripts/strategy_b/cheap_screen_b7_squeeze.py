"""scripts/strategy_b/cheap_screen_b7_squeeze.py — STRATEGY_ID = B,
Experiment B7: volatility squeeze-then-breakout, 1-minute bars. Same core
filters as B1 (breakout N=60 + realized_vol_ratio>1.5 + rel_volume_20>1.5)
PLUS exactly one new conceptual filter: realized_vol_30's 240-bar rolling
percentile rank, evaluated BREAKOUT_LOOKBACK bars before the signal, was
<0.25 (the range being broken formed during a genuine volatility
compression -- a "coiled spring" setup), distinct from B4's trend-regime
gate. See docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md Experiment B7 card
for the pre-registered rejection criterion (fixed before this ran).

Usage:
    python scripts/strategy_b/cheap_screen_b7_squeeze.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix
from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BREAKOUT_LOOKBACK = 60
VOL_EXPANSION_RATIO = 1.5
VOLUME_RATIO = 1.5
SQUEEZE_PCTILE_WINDOW = 240
SQUEEZE_PCTILE_MAX = 0.25
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = 0.0005
BASE_SLIP_PER_SIDE = 0.0001

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
REJECT_PF_THRESHOLD = 1.0
MIN_N_FOR_VERDICT = 30


def compute_entries(df: pd.DataFrame, feats: pd.DataFrame):
    breakout_level = df["high"].rolling(BREAKOUT_LOOKBACK).max().shift(1)
    breakout = df["close"] > breakout_level
    vol_ok = feats["realized_vol_ratio"] > VOL_EXPANSION_RATIO
    volume_ok = feats["rel_volume_20"] > VOLUME_RATIO
    vol_pctile = feats["realized_vol_30"].rolling(SQUEEZE_PCTILE_WINDOW).rank(pct=True)
    squeeze_ok = vol_pctile.shift(BREAKOUT_LOOKBACK) < SQUEEZE_PCTILE_MAX
    entries = (breakout.to_numpy() & vol_ok.to_numpy() & volume_ok.to_numpy() & squeeze_ok.to_numpy())
    return entries, breakout_level, vol_pctile


def sanity_check(symbol, df, feats, entries, breakout_level, vol_pctile, n_examples=3):
    idxs = np.flatnonzero(entries)[:n_examples]
    print(f"\n  --- B7 manual sanity check ({symbol}, first {len(idxs)} signals) ---")
    for i in idxs:
        ts = df.index[i]
        squeeze_idx = i - BREAKOUT_LOOKBACK
        print(f"  signal at {ts} idx={i}: close={df['close'].iloc[i]:.4f} "
              f"prior_{BREAKOUT_LOOKBACK}bar_high={breakout_level.iloc[i]:.4f} "
              f"vol_ratio={feats['realized_vol_ratio'].iloc[i]:.2f} "
              f"volume_ratio={feats['rel_volume_20'].iloc[i]:.2f} "
              f"vol_pctile@squeeze_check(idx={squeeze_idx})={vol_pctile.iloc[squeeze_idx]:.3f} (must be <{SQUEEZE_PCTILE_MAX})")
        window = df["high"].iloc[max(0, i - BREAKOUT_LOOKBACK):i]
        manual_max = window.max()
        ok = abs(manual_max - breakout_level.iloc[i]) < 1e-9
        print(f"    independent recheck: max(high[{i-BREAKOUT_LOOKBACK}:{i}]) = {manual_max:.4f} "
              f"vs breakout_level={breakout_level.iloc[i]:.4f} -> {'MATCH' if ok else 'MISMATCH!!'}")
    if len(idxs) == 0:
        print("  (no signals in the inspected range)")


def resolve_trailing(path, protective, activate_at, trail_dist, fee_slip):
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


def screen_symbol(symbol: str) -> dict:
    train_df = load_split(symbol, "train", verbose=True)
    val_df = load_split(symbol, "validation", verbose=True)

    train_feats = build_feature_matrix(train_df)
    val_feats = build_feature_matrix(val_df)

    train_entries, train_breakout, train_vp = compute_entries(train_df, train_feats)
    val_entries, val_breakout, val_vp = compute_entries(val_df, val_feats)
    print(f"{symbol}: TRAIN entries={train_entries.sum()}  VALIDATION entries={val_entries.sum()}")

    sanity_check(symbol, val_df, val_feats, val_entries, val_breakout, val_vp)

    train_close = train_df["close"].to_numpy()
    train_trades = build_trades(train_close, train_entries, train_feats["ema_slope_20"].to_numpy(), train_feats["ret_1"].to_numpy())
    if len(train_trades) < 10:
        return {"symbol": symbol, "status": "INSUFFICIENT_TRAIN_SAMPLE", "n_train_trades": len(train_trades)}

    maes = np.abs([t["mae"] for t in train_trades])
    stop_distance = float(np.percentile(maes, STOP_PCT_PERCENTILE))
    mfes_pos = [t["mfe"] for t in train_trades if t["mfe"] > 0]
    activate_at = float(np.percentile(mfes_pos, 50)) if mfes_pos else stop_distance * 0.5
    trail_dist = stop_distance * 0.5
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    fee_slip = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
    print(f"{symbol} TRAIN-derived: stop_distance={stop_distance*100:.3f}%  activate_at={activate_at*100:.3f}%  "
          f"trail_dist={trail_dist*100:.3f}%  leverage={leverage:.2f}x  (n_train_trades={len(train_trades)})")

    val_close = val_df["close"].to_numpy()
    val_trades = build_trades(val_close, val_entries, val_feats["ema_slope_20"].to_numpy(), val_feats["ret_1"].to_numpy())
    if len(val_trades) == 0:
        return {"symbol": symbol, "status": "NO_VALIDATION_TRADES"}

    returns, forced = [], 0
    for t in val_trades:
        ret, was_forced, _ = resolve_trailing(t["close_path"], protective, activate_at, trail_dist, fee_slip)
        returns.append(ret)
        forced += int(was_forced and liq_move <= stop_distance)
    returns = np.array(returns)
    wins, losses = returns[returns > 0], returns[returns <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    win_rate = float((returns > 0).mean() * 100)
    total_return_pct = float(returns.sum() * 100)
    return {
        "symbol": symbol, "status": "OK", "n_trades": len(returns), "pf": round(pf, 3),
        "win_rate_pct": round(win_rate, 1), "total_return_pct_unlevered": round(total_return_pct, 3),
        "forced_liq": forced, "stop_distance_pct": round(stop_distance * 100, 3),
        "leverage": round(leverage, 2),
    }


def main():
    print("=" * 100)
    print("  STRATEGY B -- Experiment B7: volatility squeeze-then-breakout cheap screen (BTC/ETH, 1-min)")
    print(f"  params: N={BREAKOUT_LOOKBACK} vol_ratio>{VOL_EXPANSION_RATIO} volume_ratio>{VOLUME_RATIO} "
          f"squeeze_pctile<{SQUEEZE_PCTILE_MAX} (window={SQUEEZE_PCTILE_WINDOW})")
    print("=" * 100)
    results = [screen_symbol(s) for s in SYMBOLS]
    for r in results:
        print(f"\n{r}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "strategy_b", "strategy_b_cheap_screen_b7_squeeze.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    ok = [r for r in results if r.get("status") == "OK"]
    n_total = sum(r["n_trades"] for r in ok)
    all_pf_le_1 = all(r["pf"] <= REJECT_PF_THRESHOLD for r in ok) if ok else True
    print("\n" + "=" * 100)
    print("  PRE-REGISTERED REJECTION CHECK (Experiment B7 card, STRATEGY_B_RESEARCH_LOG.md)")
    print("=" * 100)
    print(f"  n_total (BTC+ETH combined) = {n_total}  (floor = {MIN_N_FOR_VERDICT})")
    for r in ok:
        print(f"  {r['symbol']}: PF={r['pf']}  n={r['n_trades']}  forced_liq={r['forced_liq']}")
    if n_total < MIN_N_FOR_VERDICT:
        print(f"  VERDICT: INSUFFICIENT SAMPLE (n={n_total} < {MIN_N_FOR_VERDICT}) -- cannot conclude yet.")
    elif all_pf_le_1:
        print("  VERDICT: REJECT per pre-registered criterion (PF<=1.0 on BOTH symbols).")
    else:
        print("  VERDICT: does NOT trigger the pre-registered REJECT criterion -- proceed to walk-forward.")


if __name__ == "__main__":
    main()
