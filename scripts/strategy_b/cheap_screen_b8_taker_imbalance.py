"""scripts/strategy_b/cheap_screen_b8_taker_imbalance.py — STRATEGY_ID = B,
Experiment B8: order-flow imbalance continuation, a structurally NEW
hypothesis (not a breakout-family variant) -- see docs/strategy_b/
STRATEGY_B_SPEC.md REVISION 1 (2026-08-24). Entry uses taker_imbalance_20
(already-existing feature) in its own top-decile (240-bar rolling
percentile) PLUS rel_volume_20>1.5, with NO price-breakout condition at
all. Exit mechanics/TRAIN-calibration identical to the B1 family (shared
infrastructure).

Usage:
    python scripts/strategy_b/cheap_screen_b8_taker_imbalance.py
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

IMBALANCE_PCTILE_WINDOW = 240
IMBALANCE_PCTILE_MIN = 0.90
VOLUME_RATIO = 1.5
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = 0.0005
BASE_SLIP_PER_SIDE = 0.0001

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
REJECT_PF_THRESHOLD = 1.0
MIN_N_FOR_VERDICT = 30


def compute_entries(feats: pd.DataFrame):
    imb_pctile = feats["taker_imbalance_20"].rolling(IMBALANCE_PCTILE_WINDOW).rank(pct=True)
    imb_ok = imb_pctile > IMBALANCE_PCTILE_MIN
    volume_ok = feats["rel_volume_20"] > VOLUME_RATIO
    entries = (imb_ok.to_numpy() & volume_ok.to_numpy())
    return entries, imb_pctile


def sanity_check(symbol, df, feats, entries, imb_pctile, n_examples=3):
    idxs = np.flatnonzero(entries)[:n_examples]
    print(f"\n  --- B8 manual sanity check ({symbol}, first {len(idxs)} signals) ---")
    for i in idxs:
        ts = df.index[i]
        window = feats["taker_imbalance_20"].iloc[max(0, i - IMBALANCE_PCTILE_WINDOW):i]
        manual_pctile = float((window < feats["taker_imbalance_20"].iloc[i]).mean()) if len(window) else float("nan")
        print(f"  signal at {ts} idx={i}: close={df['close'].iloc[i]:.4f} "
              f"taker_imbalance_20={feats['taker_imbalance_20'].iloc[i]:.4f} "
              f"pctile={imb_pctile.iloc[i]:.3f} (must be >{IMBALANCE_PCTILE_MIN}) "
              f"volume_ratio={feats['rel_volume_20'].iloc[i]:.2f}")
        print(f"    independent recheck: manual pctile-of-window = {manual_pctile:.3f} "
              f"vs vectorized rank = {imb_pctile.iloc[i]:.3f} -> "
              f"{'MATCH' if abs(manual_pctile - imb_pctile.iloc[i]) < 0.02 else 'MISMATCH!!'}")
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

    if "taker_imbalance_20" not in train_feats.columns:
        return {"symbol": symbol, "status": "NO_TAKER_IMBALANCE_COLUMN"}

    train_entries, train_pctile = compute_entries(train_feats)
    val_entries, val_pctile = compute_entries(val_feats)
    print(f"{symbol}: TRAIN entries={train_entries.sum()}  VALIDATION entries={val_entries.sum()}")

    sanity_check(symbol, val_df, val_feats, val_entries, val_pctile)

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
    print("  STRATEGY B -- Experiment B8: order-flow imbalance continuation cheap screen (BTC/ETH)")
    print(f"  params: imbalance_pctile>{IMBALANCE_PCTILE_MIN} (window={IMBALANCE_PCTILE_WINDOW}) volume_ratio>{VOLUME_RATIO}")
    print("=" * 100)
    results = [screen_symbol(s) for s in SYMBOLS]
    for r in results:
        print(f"\n{r}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "strategy_b", "strategy_b_cheap_screen_b8_taker_imbalance.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    ok = [r for r in results if r.get("status") == "OK"]
    n_total = sum(r["n_trades"] for r in ok)
    all_pf_le_1 = all(r["pf"] <= REJECT_PF_THRESHOLD for r in ok) if ok else True
    print("\n" + "=" * 100)
    print("  PRE-REGISTERED REJECTION CHECK (Experiment B8 card, STRATEGY_B_RESEARCH_LOG.md)")
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
