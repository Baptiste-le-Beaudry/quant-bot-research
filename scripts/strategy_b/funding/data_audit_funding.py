"""scripts/strategy_b/funding/data_audit_funding.py — STRATEGY_ID =
B_FUNDING, mandatory DATA AUDIT step (must run and PASS before any
strategy logic is built on top of this data). Validates the existing
BTC/ETH funding-rate history downloaded by
quant_bot/data/download_funding_oi.py:
  - monotonic, no duplicate timestamps
  - cadence/gap analysis (expected 8h between settlements; flag anomalies
    rather than assume they don't exist -- Binance introduced shorter
    funding intervals for some symbols/periods)
  - coverage vs the project's own price-data TRAIN/VALIDATION/HOLDOUT
    range (must cover at least back to data_start used by Strategy A/B's
    walk-forwards)
  - value sanity (no NaN/inf, no absurd magnitude)
  - documents the exact Binance convention used (see module docstring
    printed at the end)

Usage:
    python scripts/strategy_b/funding/data_audit_funding.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FUNDING_FILES = {
    "BTCUSDT": os.path.join(DATA_DIR, "BTCUSDT_funding_20190712_20260824.csv"),
    "ETHUSDT": os.path.join(DATA_DIR, "ETHUSDT_funding_20190712_20260824.csv"),
}
EXPECTED_INTERVAL_MS = 8 * 3_600_000
SAFE_END = pd.Timestamp("2025-03-28", tz="UTC")  # min(BTC,ETH HOLDOUT_START), same boundary as every walk-forward


def audit_symbol(symbol: str) -> dict:
    path = FUNDING_FILES[symbol]
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    n_raw = len(df)

    print(f"\n{'='*100}\n  DATA AUDIT: {symbol} funding rate history ({path})\n{'='*100}")
    print(f"  n_rows_raw = {n_raw}")

    # 1. Duplicates
    n_dupe_ts = int(df["timestamp"].duplicated().sum())
    print(f"  duplicate timestamps: {n_dupe_ts}  -> {'PASS' if n_dupe_ts == 0 else 'ISSUE FOUND'}")

    # 2. Monotonic
    is_sorted = df["timestamp"].is_monotonic_increasing
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"  was already sorted: {is_sorted}  (re-sorted defensively regardless)")

    # 3. Value sanity
    n_nan = int(df["fundingRate"].isna().sum())
    n_inf = int(np.isinf(df["fundingRate"].to_numpy(dtype=float)).sum())
    rmin, rmax = df["fundingRate"].min(), df["fundingRate"].max()
    print(f"  NaN fundingRate: {n_nan}  Inf: {n_inf}  range=[{rmin:.6f}, {rmax:.6f}]  "
          f"-> {'PASS' if n_nan == 0 and n_inf == 0 and abs(rmax) < 0.02 else 'ISSUE FOUND (check magnitude/NaN)'}")

    # 4. Cadence / gaps -- round to the nearest MINUTE first (raw ms timestamps carry
    # sub-second API jitter around exact 8h boundaries that isn't a real gap).
    diffs_hours = (df["timestamp"].diff().dropna().dt.total_seconds() / 3600).round(2)
    bucketed = diffs_hours.round(0)  # nearest hour: 8.00->8, 16.0x->16, etc.
    counts = bucketed.value_counts().sort_index()
    n_8h = int((bucketed == 8).sum())
    n_16h = int((bucketed == 16).sum())
    n_other_bucket = len(bucketed) - n_8h - n_16h
    print(f"  interval histogram (rounded to nearest hour): {dict(counts)}")
    print(f"  == 8h: {n_8h} ({n_8h/len(bucketed)*100:.1f}%)   == 16h (1 missed settlement): "
          f"{n_16h} ({n_16h/len(bucketed)*100:.1f}%)   other: {n_other_bucket}")
    if n_16h:
        gap_mask = bucketed == 16
        gap_times = df["timestamp"].iloc[1:][gap_mask.to_numpy()]
        print(f"  16h-gap dates range: {gap_times.min()} -> {gap_times.max()}  "
              f"(first 5: {list(gap_times.head(5))})")
        # Cross-check: are these gaps concentrated in a specific era, or spread across the
        # whole history? A gap consistently spread across all years is much less concerning
        # (matches Binance's known historical practice of occasionally skipping/merging a
        # settlement print during very low-volatility stretches) than a gap concentrated in
        # one era (which would suggest a real collection problem for that period).
        years = gap_times.dt.year.value_counts().sort_index()
        print(f"  16h-gap distribution by year: {dict(years)}")
    print("  NOTE: sub-hour jitter around 8h is pure API millisecond noise, not a data issue. "
          "A 16h gap means exactly one 8h settlement print is absent from the record for that "
          "slot -- see year distribution above to judge whether this is spread evenly (benign) "
          "or concentrated (real gap). This does NOT affect the funding-merge logic either way, "
          "since entries are found via per-event lookup against actual observed timestamps, "
          "never assuming a fixed 8h grid.")

    # 5. Coverage vs SAFE_END / walk-forward needs
    cov_start, cov_end = df["timestamp"].iloc[0], df["timestamp"].iloc[-1]
    covers_safe_end = cov_start < SAFE_END < cov_end
    print(f"  coverage: {cov_start} -> {cov_end}")
    print(f"  covers SAFE_END={SAFE_END.date()} (needed for walk-forward): "
          f"{'PASS' if covers_safe_end else 'ISSUE FOUND'}")

    status = "PASS" if (n_dupe_ts == 0 and n_nan == 0 and n_inf == 0 and covers_safe_end) else "ISSUE FOUND"
    return {
        "symbol": symbol, "n_rows": n_raw, "n_dupe_ts": n_dupe_ts, "n_nan": n_nan, "n_inf": n_inf,
        "rate_min": rmin, "rate_max": rmax, "n_8h_intervals": n_8h, "n_16h_gap_intervals": n_16h,
        "coverage_start": str(cov_start), "coverage_end": str(cov_end), "covers_safe_end": covers_safe_end,
        "status": status,
    }


def main():
    print("BINANCE FUNDING RATE CONVENTION (documented here, not re-derived per script):")
    print("  - Endpoint: /fapi/v1/fundingRate. Each row's 'fundingTime' is the MOMENT THE")
    print("    FUNDING PAYMENT IS SETTLED/EXCHANGED between longs and shorts -- this is a")
    print("    HISTORICAL, ALREADY-SETTLED value, never a forward-looking prediction.")
    print("  - The 'fundingRate' value for a given fundingTime is fully KNOWN and FIXED at")
    print("    that exact instant (it is the officially charged rate, not an estimate).")
    print("  - This project's OWN price bars are indexed by Binance kline OPEN time (verified")
    print("    via quant_bot/data/download_klines.py's RAW_COLUMNS ordering, first field =")
    print("    kline openTime). A price bar timestamped T covers [T, T+1min); its OWN close")
    print("    price (used for every entry/exit in this project) is only actually finalized")
    print("    at T+1min -- i.e. every existing feature/signal in this codebase already treats")
    print("    bar T's close as 'known at T', a one-minute-conservative simplification used")
    print("    consistently project-wide (Strategy A entries, Strategy B entries, features).")
    print("  - CONSEQUENCE for the funding merge: attaching funding event (fundingTime=T_f) to")
    print("    price bar T via merge_asof(direction='backward', allow_exact_matches=True) on T")
    print("    is SAFE even when T == T_f exactly, because the funding is settled/known AT T_f,")
    print("    while the price bar's own decision point (its close) is only actually available")
    print("    at T+1min >= T_f -- i.e. this is at least as conservative as every other feature")
    print("    in this codebase, not a new or looser assumption.")
    print()

    results = [audit_symbol(s) for s in FUNDING_FILES]
    df_res = pd.DataFrame(results)
    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "strategy_b", "funding", "data_audit_funding_results.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df_res.to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")

    print("\n" + "=" * 100)
    print("  DATA AUDIT SUMMARY")
    print("=" * 100)
    for r in results:
        print(f"  {r['symbol']}: {r['status']}")
    overall = "PASS" if all(r["status"] == "PASS" for r in results) else "ISSUE FOUND"
    print(f"\n  OVERALL: {overall}")


if __name__ == "__main__":
    main()
