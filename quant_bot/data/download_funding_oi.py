"""
download_funding_oi.py — funding rate history (full depth, free) and open
interest history (Binance only retains ~30 days of this via the free
endpoint — see SPEC.md section 3) for Binance USDT-M Futures.

Usage:
    python -m quant_bot.data.download_funding_oi --symbol BTCUSDT --days 730 --funding
    python -m quant_bot.data.download_funding_oi --symbol BTCUSDT --days 30 --oi
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
OI_URL = "https://fapi.binance.com/futures/data/openInterestHist"
FUNDING_INTERVAL_MS = 8 * 3_600_000  # funding settles every 8h


def download_funding_history(symbol: str, start_dt: datetime, end_dt: datetime, save_dir: str) -> pd.DataFrame:
    """Full-depth funding rate history — no retention limit on this endpoint."""
    os.makedirs(save_dir, exist_ok=True)
    start_ms, end_ms = int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)
    all_rows, current = [], start_ms

    print(f"\nFunding rate history: {symbol} {start_dt:%Y-%m-%d} -> {end_dt:%Y-%m-%d}")
    while current < end_ms:
        params = {"symbol": symbol, "startTime": current, "endTime": end_ms, "limit": 1000}
        try:
            resp = requests.get(FUNDING_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            all_rows.extend(data)
            # BUGFIX (2026-08-24, found during Strategy B_FUNDING data audit): advancing by a
            # fixed FUNDING_INTERVAL_MS assumes every settlement is exactly 8h apart. When a
            # response happens to end early relative to that assumption (observed empirically:
            # requesting a narrow window around the skipped point returns a real settlement the
            # bulk download silently missed), jumping by +8h from the last row skips it. Advancing
            # by +1ms instead is always safe (the API is inclusive of startTime, exclusive of
            # nothing) and guarantees no in-between real event is ever skipped, regardless of the
            # true interval structure for that period.
            current = data[-1]["fundingTime"] + 1
            print(f"\r  {len(all_rows)} funding events...", end="", flush=True)
            time.sleep(0.1)
        except Exception as e:
            print(f"\n  Error: {e} -- pausing 3s"); time.sleep(3)
    print()

    if not all_rows:
        print("  No funding data.")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["fundingRate"] = df["fundingRate"].astype(float)
    df = df.set_index("timestamp")[["fundingRate"]].sort_index()
    # BUGFIX (2026-08-24, found during Strategy B_FUNDING data audit): plain .drop_duplicates()
    # on a single-column frame dedupes by VALUE, not by timestamp -- with only "fundingRate" left
    # as a column, any two DIFFERENT settlement events that happen to share the same rate (very
    # common near zero) were being collapsed into one, silently destroying ~40% of real events
    # (verified: 7619 genuinely distinct fetched timestamps collapsed to 4512 unique values).
    # Dedup on the index (timestamp) instead -- this only removes true re-fetched duplicates from
    # overlapping pagination windows, never distinct events that coincidentally share a rate.
    df = df[~df.index.duplicated()]

    fpath = os.path.join(save_dir, f"{symbol}_funding_{start_dt:%Y%m%d}_{end_dt:%Y%m%d}.csv")
    df.to_csv(fpath)
    print(f"{symbol}: {len(df):,} funding events saved -> {fpath}")
    return df


def download_open_interest_history(symbol: str, days: int, save_dir: str, period: str = "1h") -> pd.DataFrame:
    """Open interest history. Binance's free endpoint only retains the last
    ~30 days regardless of what's requested — SPEC.md section 3 flags this;
    for a longer OI history you'd need to run a live collector or a paid
    vendor. This just pulls whatever the endpoint currently has."""
    os.makedirs(save_dir, exist_ok=True)
    end_dt = datetime.now(tz=timezone.utc)
    start_dt = end_dt - timedelta(days=min(days, 30))
    if days > 30:
        print(f"  Note: open interest history is capped at ~30 days by Binance's "
              f"free endpoint — requested {days}, will only get ~30.")

    params = {
        "symbol": symbol, "period": period,
        "startTime": int(start_dt.timestamp() * 1000),
        "endTime": int(end_dt.timestamp() * 1000),
        "limit": 500,
    }
    resp = requests.get(OI_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        print("  No open interest data.")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["sumOpenInterest"] = df["sumOpenInterest"].astype(float)
    df = df.set_index("timestamp")[["sumOpenInterest"]].sort_index()

    fpath = os.path.join(save_dir, f"{symbol}_openinterest_{start_dt:%Y%m%d}_{end_dt:%Y%m%d}.csv")
    df.to_csv(fpath)
    print(f"{symbol}: {len(df):,} open-interest points saved -> {fpath}")
    return df


def main():
    from quant_bot.config import DATA_DIR, SYMBOLS

    parser = argparse.ArgumentParser(description="Binance funding rate / open interest downloader")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--funding", action="store_true")
    parser.add_argument("--oi", action="store_true")
    parser.add_argument("--dir", default=DATA_DIR)
    args = parser.parse_args()

    if not args.funding and not args.oi:
        args.funding = args.oi = True  # default: fetch both

    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=args.days)
    symbols = [args.symbol.upper()] if args.symbol else SYMBOLS

    for symbol in symbols:
        if args.funding:
            download_funding_history(symbol, start, now, args.dir)
        if args.oi:
            download_open_interest_history(symbol, args.days, args.dir)


if __name__ == "__main__":
    main()
