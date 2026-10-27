"""scripts/strategy_b/funding/cheap_screen_bfunding2_persistent.py —
STRATEGY_ID = B_FUNDING, Experiment BF2: persistent funding regime
(3-settlement rolling mean, ~24h) instead of BF1's single-point extreme.
See docs/strategy_b/funding/STRATEGY_B_FUNDING_SPEC.md REVISION 1.
Structurally identical to BF1 otherwise (event-driven, TRAIN-only
thresholds, per-direction TRAIN exit calibration) -- only the value
tested against the threshold changes (rolling(3).mean() vs raw rate).

Usage:
    python scripts/strategy_b/funding/cheap_screen_bfunding2_persistent.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import numpy as np
import pandas as pd

from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.strategy_b.funding.funding_lib import (
    load_funding, train_only_thresholds, find_entry_indices,
    build_short_trades,
)
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_long_trades

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = 0.0005
BASE_SLIP_PER_SIDE = 0.0001

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
REJECT_PF_THRESHOLD = 1.0
MIN_N_FOR_VERDICT = 30
P_LOW, P_HIGH = 0.10, 0.90
ROLLING_N = 3


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


def calibrate(trades):
    if len(trades) < 10:
        return None
    maes = np.abs([t["mae"] for t in trades])
    stop_distance = float(np.percentile(maes, STOP_PCT_PERCENTILE))
    mfes_pos = [t["mfe"] for t in trades if t["mfe"] > 0]
    activate_at = float(np.percentile(mfes_pos, 50)) if mfes_pos else stop_distance * 0.5
    trail_dist = stop_distance * 0.5
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    return {"stop_distance": stop_distance, "activate_at": activate_at, "trail_dist": trail_dist,
            "leverage": leverage, "protective": protective, "liq_move": liq_move,
            "n_train_trades": len(trades)}


def resolve_all(trades, calib):
    fee_slip = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
    returns, forced = [], 0
    for t in trades:
        ret, was_forced, _ = resolve_trailing(t["close_path"], calib["protective"], calib["activate_at"],
                                               calib["trail_dist"], fee_slip)
        returns.append(ret)
        forced += int(was_forced and calib["liq_move"] <= calib["stop_distance"])
    return np.array(returns), forced


def screen_symbol(symbol: str) -> dict:
    train_df = load_split(symbol, "train", verbose=True)
    val_df = load_split(symbol, "validation", verbose=True)
    funding_raw = load_funding(symbol)
    # Causal: rolling(3) uses only settlements up to and including the current one.
    funding = funding_raw.rolling(ROLLING_N).mean().dropna()
    funding.name = "fundingRate"

    train_funding_slice = funding[(funding.index >= train_df.index[0]) & (funding.index <= train_df.index[-1])]
    p_low, p_high = train_only_thresholds(train_funding_slice, P_LOW, P_HIGH)
    print(f"{symbol}: TRAIN-only rolling-{ROLLING_N} funding thresholds: p{int(P_LOW*100)}={p_low:.6f}  "
          f"p{int(P_HIGH*100)}={p_high:.6f}  (from {len(train_funding_slice)} TRAIN events)")

    train_long_mask, train_short_mask, train_log = find_entry_indices(train_df.index, funding, p_low, p_high)
    val_long_mask, val_short_mask, val_log = find_entry_indices(val_df.index, funding, p_low, p_high)
    print(f"{symbol}: TRAIN entries: long={train_long_mask.sum()} short={train_short_mask.sum()}  "
          f"VALIDATION entries: long={val_long_mask.sum()} short={val_short_mask.sum()}")

    for direction in ["LONG", "SHORT"]:
        sub = val_log[val_log["direction"] == direction].head(2)
        print(f"  --- sanity check ({symbol} {direction}, first {len(sub)} signals) ---")
        for _, row in sub.iterrows():
            print(f"  funding_time={row['funding_time']} rolling3_rate={row['funding_rate']:.6f} "
                  f"entry_bar_time={row['entry_bar_time']} "
                  f"(entry_bar_time >= funding_time: {row['entry_bar_time'] >= row['funding_time']})")

    train_close = train_df["close"].to_numpy()
    z_train = np.zeros(len(train_df))
    train_long_trades = build_long_trades(train_close, train_long_mask, z_train, z_train)
    train_short_trades = build_short_trades(train_close, train_short_mask, z_train, z_train)

    calib_long = calibrate(train_long_trades)
    calib_short = calibrate(train_short_trades)
    print(f"{symbol}: LONG calib={calib_long}")
    print(f"{symbol}: SHORT calib={calib_short}")

    val_close = val_df["close"].to_numpy()
    z_val = np.zeros(len(val_df))

    all_returns, total_forced, n_long, n_short = [], 0, 0, 0
    if calib_long is not None:
        val_long_trades = build_long_trades(val_close, val_long_mask, z_val, z_val)
        r, f = resolve_all(val_long_trades, calib_long)
        all_returns.append(r)
        total_forced += f
        n_long = len(r)
    if calib_short is not None:
        val_short_trades = build_short_trades(val_close, val_short_mask, z_val, z_val)
        r, f = resolve_all(val_short_trades, calib_short)
        all_returns.append(r)
        total_forced += f
        n_short = len(r)

    if not all_returns or (n_long + n_short) == 0:
        return {"symbol": symbol, "status": "NO_VALIDATION_TRADES", "n_long_train": len(train_long_trades),
                "n_short_train": len(train_short_trades)}

    returns = np.concatenate(all_returns)
    wins, losses = returns[returns > 0], returns[returns <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    win_rate = float((returns > 0).mean() * 100)
    total_return_pct = float(returns.sum() * 100)
    return {
        "symbol": symbol, "status": "OK", "n_trades": len(returns), "n_long": n_long, "n_short": n_short,
        "pf": round(pf, 3), "win_rate_pct": round(win_rate, 1),
        "total_return_pct_unlevered": round(total_return_pct, 3), "forced_liq": total_forced,
    }


def main():
    print("=" * 100)
    print("  STRATEGY B_FUNDING -- Experiment BF2: persistent funding regime cheap screen (BTC/ETH)")
    print(f"  params: rolling_n={ROLLING_N} p_low={P_LOW} p_high={P_HIGH} (TRAIN-only), event-driven")
    print("=" * 100)
    results = [screen_symbol(s) for s in SYMBOLS]
    for r in results:
        print(f"\n{r}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "strategy_b", "funding", "bfunding2_persistent_cheap_screen_btc_eth.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    ok = [r for r in results if r.get("status") == "OK"]
    n_total = sum(r["n_trades"] for r in ok)
    all_pf_le_1 = all(r["pf"] <= REJECT_PF_THRESHOLD for r in ok) if ok else True
    print("\n" + "=" * 100)
    print("  PRE-REGISTERED REJECTION CHECK (STRATEGY_B_FUNDING_SPEC.md REVISION 1)")
    print("=" * 100)
    print(f"  n_total (BTC+ETH combined) = {n_total}  (floor = {MIN_N_FOR_VERDICT})")
    for r in ok:
        print(f"  {r['symbol']}: PF={r['pf']}  n={r['n_trades']} (long={r['n_long']}/short={r['n_short']})  forced_liq={r['forced_liq']}")
    if n_total < MIN_N_FOR_VERDICT:
        print(f"  VERDICT: INSUFFICIENT SAMPLE (n={n_total} < {MIN_N_FOR_VERDICT}) -- cannot conclude yet.")
    elif all_pf_le_1:
        print("  VERDICT: REJECT per pre-registered criterion (PF<=1.0 on BOTH symbols).")
    else:
        print("  VERDICT: does NOT trigger the pre-registered REJECT criterion -- proceed to walk-forward.")


if __name__ == "__main__":
    main()
