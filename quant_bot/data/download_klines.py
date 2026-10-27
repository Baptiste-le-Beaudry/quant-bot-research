"""
download_klines.py — historical 1-minute klines from Binance USDT-M Futures.

Adapted from confluence_ai_v3/download_history.py (same chunked-pagination
approach, proven there) but targets the Futures API (not spot) and keeps
taker_buy_volume so we get a free order-flow-imbalance proxy per SPEC.md
section 3, instead of discarding it like the old downloader did.

Usage:
    python -m quant_bot.data.download_klines --symbol BTCUSDT --days 730
    python -m quant_bot.data.download_klines --symbol BTCUSDT --from 2023-01-01 --to 2025-01-01
"""

import argparse
import csv
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

FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "1h": 3_600_000, "4h": 14_400_000}
CHUNK_LIMIT = 1500  # Futures API max per request (spot API max is 1000)


def download_chunk(symbol: str, start_ms: int, end_ms: int, interval: str = "1m") -> list:
    params = {
        "symbol": symbol, "interval": interval,
        "startTime": start_ms, "endTime": end_ms, "limit": CHUNK_LIMIT,
    }
    resp = requests.get(FUTURES_KLINES_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


RAW_COLUMNS = [
    "timestamp", "open", "high", "low", "close", "volume",
    "close_time", "quote_vol", "n_trades", "taker_buy_base",
    "taker_buy_quote", "ignore",
]


def _migrate_or_read_last_ts(ckpt_path: str) -> tuple:
    """One-time (per process start, not per chunk) scan of the checkpoint
    file to find the last saved bar's open-time and row count -- used to
    seed the resume marker on first run against an existing checkpoint
    (fresh start, or migrating from the old whole-file-rewrite format)."""
    last_ts, n_bars = None, 0
    with open(ckpt_path, "r", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if not row:
                continue
            n_bars += 1
            last_ts = int(float(row[0]))  # old checkpoint format wrote this column as float
    return last_ts, n_bars


def download_full_history(
    symbol: str, start_dt: datetime, end_dt: datetime,
    save_dir: str, interval: str = "1m",
) -> pd.DataFrame:
    os.makedirs(save_dir, exist_ok=True)
    bar_ms = INTERVAL_MS[interval]
    start_ms, end_ms = int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)

    fname = f"{symbol}_{interval}_{start_dt:%Y%m%d}_{end_dt:%Y%m%d}.csv"
    fpath = os.path.join(save_dir, fname)
    ckpt_path = fpath + ".partial.raw.csv"
    marker_path = ckpt_path + ".resume"

    print(f"\n{'='*60}\nBinance USDT-M Futures — {symbol} {interval}")
    print(f"  {start_dt:%Y-%m-%d} -> {end_dt:%Y-%m-%d}\n{'='*60}")

    # Checkpointing strategy: append each chunk's raw rows to ckpt_path
    # immediately (O(chunk size), not O(total downloaded so far) -- the
    # previous version rewrote the ENTIRE accumulated dataset every 200
    # chunks, which got slower and more memory-hungry as it grew into the
    # millions of rows, and repeatedly coincided with this environment's
    # background-task kills right around that same point. A tiny separate
    # "resume marker" file (just the next timestamp to fetch) is written
    # atomically after each chunk so a restart never needs to re-read the
    # (potentially huge) checkpoint file at all, except once at the very
    # end when the final CSV is assembled.
    current = start_ms
    n_bars = 0
    header_written = os.path.exists(ckpt_path) and os.path.getsize(ckpt_path) > 0
    if os.path.exists(marker_path):
        with open(marker_path) as f:
            current = int(f.read().strip())
        if header_written:
            with open(ckpt_path, "r", newline="") as f:
                n_bars = sum(1 for _ in f) - 1
        resume_dt = datetime.fromtimestamp(current / 1000, tz=timezone.utc)
        print(f"  Resuming from checkpoint: {n_bars:,} bars already downloaded, "
              f"continuing from {resume_dt:%Y-%m-%d %H:%M}")
    elif header_written:
        last_ts, n_bars = _migrate_or_read_last_ts(ckpt_path)
        if last_ts is not None:
            current = last_ts + bar_ms
            resume_dt = datetime.fromtimestamp(current / 1000, tz=timezone.utc)
            print(f"  Migrating checkpoint: {n_bars:,} bars already downloaded, "
                  f"continuing from {resume_dt:%Y-%m-%d %H:%M}")

    chunk_num = 0
    while current < end_ms:
        chunk_end = min(current + CHUNK_LIMIT * bar_ms, end_ms)
        chunk_num += 1
        try:
            data = download_chunk(symbol, current, chunk_end, interval)
            if not data:
                current = chunk_end
                continue

            with open(ckpt_path, "a", newline="") as f:
                writer = csv.writer(f)
                if not header_written:
                    writer.writerow(RAW_COLUMNS)
                    header_written = True
                writer.writerows(data)
            n_bars += len(data)
            current = data[-1][0] + bar_ms

            tmp_marker = marker_path + ".tmp"
            with open(tmp_marker, "w") as f:
                f.write(str(current))
            os.replace(tmp_marker, marker_path)  # atomic on POSIX and Windows

            pct = min((current - start_ms) / (end_ms - start_ms) * 100, 100)
            dt = datetime.fromtimestamp(data[-1][0] / 1000, tz=timezone.utc)
            print(f"\r  [{pct:5.1f}%] {chunk_num} chunks | last bar {dt:%Y-%m-%d %H:%M} | "
                  f"{n_bars:,} bars", end="", flush=True)
            time.sleep(0.1)
        except requests.exceptions.HTTPError as e:
            print(f"\n  HTTP error: {e} -- pausing 5s"); time.sleep(5)
        except Exception as e:
            print(f"\n  Error: {e} -- pausing 3s"); time.sleep(3)
    print()

    if n_bars == 0:
        print("  No data downloaded.")
        return pd.DataFrame()

    df = pd.read_csv(ckpt_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index().drop_duplicates()
    df = df[["open", "high", "low", "close", "volume", "taker_buy_base"]].astype(float)
    df = df.rename(columns={"taker_buy_base": "taker_buy_volume"})
    df["taker_sell_volume"] = df["volume"] - df["taker_buy_volume"]

    df.to_csv(fpath)
    os.remove(ckpt_path)
    if os.path.exists(marker_path):
        os.remove(marker_path)
    print(f"\n{symbol}: {len(df):,} bars saved -> {fpath}")
    print(f"  {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d} | "
          f"{os.path.getsize(fpath)/1024/1024:.1f} MB")
    return df


def main():
    from quant_bot.config import DATA_DIR, SYMBOLS

    parser = argparse.ArgumentParser(description="Binance USDT-M Futures historical klines downloader")
    parser.add_argument("--symbol", default=None, help="e.g. BTCUSDT (default: all of quant_bot.config.SYMBOLS)")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="YYYY-MM-DD")
    parser.add_argument("--interval", default="1m", choices=list(INTERVAL_MS.keys()))
    parser.add_argument("--dir", default=DATA_DIR)
    args = parser.parse_args()

    now = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    if args.date_from and args.date_to:
        start = datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(args.date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end, start = now, now - timedelta(days=args.days)

    symbols = [args.symbol.upper()] if args.symbol else SYMBOLS
    for symbol in symbols:
        download_full_history(symbol, start, end, args.dir, interval=args.interval)


if __name__ == "__main__":
    main()
