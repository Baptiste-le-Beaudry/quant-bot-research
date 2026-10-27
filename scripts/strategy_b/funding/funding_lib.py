"""scripts/strategy_b/funding/funding_lib.py — STRATEGY_ID = B_FUNDING
shared infrastructure: load the (bug-fixed, see STRATEGY_B_FUNDING_SPEC.md)
funding-rate history, compute TRAIN-only extreme thresholds, and find
CAUSAL entry bar indices for each real funding event -- no synthetic
grid, no lookahead. Also provides a short-trade wrapper around the
existing long-only build_trades_with_mae_mfe_fast (negates the path,
does not modify the shared function itself).

Import this from any B_FUNDING script; do not duplicate this logic.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR
from scripts.fast_trades import build_trades_with_mae_mfe_fast

FUNDING_FILES = {
    "BTCUSDT": os.path.join(DATA_DIR, "BTCUSDT_funding_20190712_20260824.csv"),
    "ETHUSDT": os.path.join(DATA_DIR, "ETHUSDT_funding_20190712_20260824.csv"),
}


def load_funding(symbol: str) -> pd.Series:
    df = pd.read_csv(FUNDING_FILES[symbol])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    return df.sort_values("timestamp").set_index("timestamp")["fundingRate"]


def train_only_thresholds(funding_train: pd.Series, p_low=0.10, p_high=0.90) -> tuple:
    """Fixed BEFORE looking at VALIDATION -- percentiles of the TRAIN funding
    population only, exactly the same discipline as Strategy A's entry-filter
    cutoffs (TRAIN-selected population median/percentile, frozen)."""
    return float(funding_train.quantile(p_low)), float(funding_train.quantile(p_high))


def find_entry_indices(price_index: pd.DatetimeIndex, funding: pd.Series, p_low: float, p_high: float):
    """For each REAL funding event with timestamp in [price_index[0], price_index[-1]],
    find the entry bar = first price bar with timestamp >= fundingTime (causal: the
    price bar's own decision point, its close, is only available at +1min, always
    AFTER the funding is known -- see STRATEGY_B_FUNDING_SPEC.md's Logic Audit).
    Returns (long_entry_mask, short_entry_mask, event_log) where event_log is a
    DataFrame of every classified event for independent sanity-checking."""
    n = len(price_index)
    long_mask = np.zeros(n, dtype=bool)
    short_mask = np.zeros(n, dtype=bool)
    in_range = funding[(funding.index >= price_index[0]) & (funding.index <= price_index[-1])]

    rows = []
    price_index_arr = price_index.values
    for ts, rate in in_range.items():
        i = int(np.searchsorted(price_index_arr, np.datetime64(ts), side="left"))
        if i >= n:
            continue
        direction = None
        if rate > p_high:
            short_mask[i] = True
            direction = "SHORT"
        elif rate < p_low:
            long_mask[i] = True
            direction = "LONG"
        rows.append({"funding_time": ts, "funding_rate": rate, "entry_idx": i,
                      "entry_bar_time": price_index[i], "direction": direction})
    return long_mask, short_mask, pd.DataFrame(rows)


def build_short_trades(close_arr, entry_mask, ema_slope, ret_1) -> list:
    """Thin wrapper: reuse the existing long-only trade-path builder, then negate
    the path (and recompute mae/mfe from the negated path) so that 'favorable
    movement' consistently means positive for a SHORT position -- does not modify
    scripts/fast_trades.py, which stays frozen shared infrastructure."""
    long_trades = build_trades_with_mae_mfe_fast(close_arr, entry_mask, ema_slope, ret_1)
    short_trades = []
    for t in long_trades:
        neg_path = -t["close_path"]
        short_trades.append({
            **t, "close_path": neg_path,
            "mae": float(neg_path.min()), "mfe": float(neg_path.max()),
        })
    return short_trades


# ── Automated invariant tests (LOGIC AUDIT, per mandate) ───────────────

def _run_logic_audit_tests():
    print("=" * 100)
    print("  LOGIC AUDIT: automated invariant tests for funding_lib")
    print("=" * 100)
    all_pass = True

    # Test 1: entry bar timestamp is NEVER before the funding event's own timestamp.
    price_index = pd.date_range("2024-01-01", periods=200_000, freq="1min", tz="UTC")
    funding = load_funding("BTCUSDT")
    funding_slice = funding[(funding.index >= price_index[0]) & (funding.index <= price_index[-1])]
    p_low, p_high = train_only_thresholds(funding_slice, 0.10, 0.90)
    long_mask, short_mask, log = find_entry_indices(price_index, funding, p_low, p_high)
    causal_ok = bool((log["entry_bar_time"] >= log["funding_time"]).all())
    print(f"  Test 1 (entry bar always >= funding event time): {'PASS' if causal_ok else 'FAIL'}")
    all_pass &= causal_ok

    # Test 2: independent recomputation of entry_idx via a manual scan, for a sample.
    sample = log.sample(min(20, len(log)), random_state=42)
    mismatches = 0
    for _, row in sample.iterrows():
        manual_idx = None
        for i, t in enumerate(price_index):
            if t >= row["funding_time"]:
                manual_idx = i
                break
        if manual_idx != row["entry_idx"]:
            mismatches += 1
    print(f"  Test 2 (independent manual entry_idx recompute, n={len(sample)}): "
          f"{'PASS' if mismatches == 0 else f'FAIL ({mismatches} mismatches)'}")
    all_pass &= (mismatches == 0)

    # Test 3: TRAIN-only threshold uses ONLY the funding_slice passed in, never full history --
    # verify thresholds change when given a strict TRAIN-only subset vs the full series.
    half = len(funding_slice) // 2
    p_low_half, p_high_half = train_only_thresholds(funding_slice.iloc[:half], 0.10, 0.90)
    differs = (abs(p_low_half - p_low) > 1e-12) or (abs(p_high_half - p_high) > 1e-12)
    print(f"  Test 3 (TRAIN-only subset produces different thresholds than full slice, "
          f"proving no leakage of the excluded portion into the threshold calc): "
          f"{'PASS' if differs else 'FAIL (thresholds identical -- suspicious)'}")
    all_pass &= differs

    # Test 4: short-trade wrapper correctly negates path (mae/mfe swap sign relationship).
    close_arr = np.cumsum(np.random.RandomState(0).normal(0, 1, 5000)) + 100
    mask = np.zeros(5000, dtype=bool)
    mask[100] = True
    mask[500] = True
    ema_slope = np.zeros(5000)
    ret_1 = np.zeros(5000)
    long_t = build_trades_with_mae_mfe_fast(close_arr, mask, ema_slope, ret_1)
    short_t = build_short_trades(close_arr, mask, ema_slope, ret_1)
    ok4 = all(abs(s["close_path"][-1] - (-l["close_path"][-1])) < 1e-9 for s, l in zip(short_t, long_t))
    ok4 = ok4 and all(abs(s["mae"] - (-l["mfe"])) < 1e-9 for s, l in zip(short_t, long_t))
    print(f"  Test 4 (short-trade path is exact negation of long-trade path, mae/mfe swap): "
          f"{'PASS' if ok4 else 'FAIL'}")
    all_pass &= ok4

    print(f"\n  OVERALL LOGIC AUDIT: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ok = _run_logic_audit_tests()
    sys.exit(0 if ok else 1)
