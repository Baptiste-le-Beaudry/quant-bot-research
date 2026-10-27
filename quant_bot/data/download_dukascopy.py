"""
quant_bot/data/download_dukascopy.py — 1-minute historical OHLCV from
Dukascopy's public JSON candle API (no auth needed), for the multi-asset
expansion plan (indices, forex, US stocks/ETFs -- everything except
crypto, which stays on Binance via download_klines.py).

Endpoint and instrument-code mapping: see
docs/dukascopy_instrument_metadata.json (1499 instruments) and the
persistent-memory note `dukascopy_data_access` for how this was found (the
obvious raw .bi5-endpoint symbol guesses all failed; the real API and code
mapping came from reading the open-source dukascopy-node client's source).

One JSON document per calendar day: GET
https://jetta.dukascopy.com/v1/candles/minute/<code>/BID/<year>/<month 1-idx>/<day>
Response is DELTA-encoded (not flat OHLC) -- decode_day() below replicates
dukascopy-node's normaliseCandles algorithm exactly (same running
openUnits/highUnits/lowUnits/closeUnits accumulators, same shared
previousCloseUnits carry-forward). Deliberately SKIPS the reference
implementation's synthetic flat-fill for time gaps (e.g. market-closed
periods) -- for quant_bot's purposes those gaps are real information
(session boundaries, overnight gaps -- see the multi-asset plan's Phase 4)
and must NOT be papered over with fabricated flat bars.

Usage:
    python -m quant_bot.data.download_dukascopy --code USATECH.IDX-USD --from 2019-01-01 --to 2025-08-01 --out data/indices/NASDAQ100_1m.csv
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

API_ROOT = "https://jetta.dukascopy.com/v1"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
REQUEST_DELAY_SEC = 0.15  # conservative pacing -- this is an unofficial, undocumented endpoint


def _price_scale(multiplier: float) -> int:
    s = f"{multiplier:.10f}".rstrip("0")
    if "." not in s:
        return 0
    return len(s.split(".")[1])


def fetch_day(code: str, date: datetime) -> dict | None:
    url = f"{API_ROOT}/candles/minute/{code}/BID/{date.year}/{date.month}/{date.day}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code == 404:
        return None  # no data that day (weekend/holiday/before listing start) -- not an error
    resp.raise_for_status()
    data = resp.json()
    if not data.get("times"):
        return None
    return data


def decode_day(data: dict) -> list[dict]:
    """Replicates dukascopy-node's normaliseCandles delta-decoding, minus the
    synthetic flat-fill for gaps (see module docstring)."""
    scale = _price_scale(data["multiplier"])
    mult = data["multiplier"]
    timestamp = data["timestamp"]
    open_u = round(data["open"] / mult)
    high_u = round(data["high"] / mult)
    low_u = round(data["low"] / mult)
    close_u = round(data["close"] / mult)
    shift = data["shift"]

    rows = []
    for i, time_delta in enumerate(data["times"]):
        timestamp += time_delta * shift
        open_u += data["opens"][i]
        high_u += data["highs"][i]
        low_u += data["lows"][i]
        close_u += data["closes"][i]
        volume = data["volumes"][i] * 1_000_000  # raw units, matches library's default volumeUnit
        rows.append({
            "timestamp": timestamp,
            "open": round(open_u * mult, scale),
            "high": round(high_u * mult, scale),
            "low": round(low_u * mult, scale),
            "close": round(close_u * mult, scale),
            "volume": volume,
        })
    return rows


def download_full_history(code: str, start: datetime, end: datetime, out_path: str,
                           fetch_until: datetime | None = None, finalize: bool = True) -> pd.DataFrame:
    """fetch_until: stop fetching at this date even if `end` (the TRUE target) is later --
    for resumable, short-lived invocations. finalize=False leaves the .partial.csv/.marker
    files in place (not yet converted to the final indexed CSV) so a later call can resume."""
    ckpt_path = out_path + ".partial.csv"
    marker_path = out_path + ".marker"
    header_written = os.path.exists(ckpt_path) and os.path.getsize(ckpt_path) > 0

    current = start
    if os.path.exists(marker_path):
        with open(marker_path) as f:
            current = datetime.fromisoformat(f.read().strip())
        print(f"Resuming {code} from {current:%Y-%m-%d}")

    stop_at = min(end, fetch_until) if fetch_until else end
    n_days_fetched, n_rows = 0, 0
    while current < stop_at:
        try:
            data = fetch_day(code, current)
            if data:
                rows = decode_day(data)
                with open(ckpt_path, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
                    if not header_written:
                        writer.writeheader()
                        header_written = True
                    writer.writerows(rows)
                n_rows += len(rows)
            n_days_fetched += 1
            current += timedelta(days=1)
            with open(marker_path + ".tmp", "w") as f:
                f.write(current.isoformat())
            os.replace(marker_path + ".tmp", marker_path)
            if n_days_fetched % 50 == 0:
                print(f"\r  [{code}] {current:%Y-%m-%d} | {n_days_fetched} days fetched | {n_rows:,} bars", end="", flush=True)
            time.sleep(REQUEST_DELAY_SEC)
        except requests.exceptions.RequestException as e:
            print(f"\n  Request error: {e} -- pausing 5s"); time.sleep(5)
    print()

    if not finalize:
        print(f"  Stopped at {current:%Y-%m-%d} (target end {end:%Y-%m-%d}) -- checkpoint preserved, rerun to continue.")
        return pd.DataFrame()

    if not os.path.exists(ckpt_path):
        print("  No data downloaded.")
        return pd.DataFrame()

    df = pd.read_csv(ckpt_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index().drop_duplicates()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path)
    os.remove(ckpt_path)
    if os.path.exists(marker_path):
        os.remove(marker_path)
    print(f"  Saved {len(df):,} bars -> {out_path}")
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True, help="Dukascopy instrument code, e.g. USATECH.IDX-USD")
    parser.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", required=True, help="output CSV path")
    parser.add_argument("--max-days", type=int, default=None,
                         help="stop after fetching this many NEW days this invocation (for resumable, "
                              "short-lived runs in environments that kill long background processes)")
    args = parser.parse_args()

    start = datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    if args.max_days:
        marker_path = args.out + ".marker"
        current = start
        if os.path.exists(marker_path):
            with open(marker_path) as f:
                current = datetime.fromisoformat(f.read().strip())
        fetch_until = current + timedelta(days=args.max_days)
        finalize = fetch_until >= end
        download_full_history(args.code, start, end, args.out, fetch_until=fetch_until, finalize=finalize)
    else:
        download_full_history(args.code, start, end, args.out)


if __name__ == "__main__":
    main()
