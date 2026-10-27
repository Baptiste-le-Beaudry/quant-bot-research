"""Exp 61 data: Binance USDT-M 1m klines (data.binance.vision monthly archives, daily archives as
fallback for a month not yet published) for the preregistered Solana tokens.

Output (new folder, never overwrites docs/_full_data_cache or other data/ files):
  <out>/raw/<SYM>/<SYM>-1m-YYYY-MM.zip     archives as downloaded
  <out>/<SYM>_full.pkl                     same format as docs/_full_data_cache/<SYM>_full.pkl:
      index 'timestamp' (UTC bar open), float64 open/high/low/close/volume/taker_buy_volume/
      taker_sell_volume (= volume - taker_buy_volume), truncated at --end (exclusive).

  python scripts/agents/exp61_download.py --out C:/AAProjet/quant_bot_v1/data/exp61
"""
from __future__ import annotations

import argparse
import io
import re
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

SYMBOLS = ("JUPUSDT", "JTOUSDT", "PYTHUSDT", "RAYUSDT", "WIFUSDT", "1000BONKUSDT")
LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
BASE = "https://data.binance.vision/"
REQ = ["open", "high", "low", "close", "volume", "taker_buy_volume", "taker_sell_volume"]
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
        "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
END = pd.Timestamp("2026-08-18", tz="UTC")


def list_keys(prefix: str) -> list[str]:
    keys, marker = [], None
    while True:
        params = {"prefix": prefix, "delimiter": "/"}
        if marker:
            params["marker"] = marker
        r = requests.get(LIST_URL, params=params, timeout=60)
        r.raise_for_status()
        page = re.findall(r"<Key>([^<]*\.zip)</Key>", r.text)
        keys += page
        if "<IsTruncated>true</IsTruncated>" not in r.text or not page:
            return keys
        marker = page[-1]


def parse_zip(blob: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        raw = z.read(z.namelist()[0]).decode()
    df = pd.read_csv(io.StringIO(raw), header=0 if raw.startswith("open_time") else None)
    df.columns = COLS
    return df


def frame_from_parts(parts: list[pd.DataFrame], end: pd.Timestamp = END) -> pd.DataFrame:
    df = pd.concat(parts).drop_duplicates("open_time").sort_values("open_time")
    df.index = pd.DatetimeIndex(pd.to_datetime(df.open_time.astype("int64"), unit="ms", utc=True),
                                name="timestamp")
    df["taker_sell_volume"] = df.volume - df.taker_buy_volume
    df = df[REQ].astype(float)
    return df[df.index < end]


def fetch_symbol(sym: str, out: Path, end: pd.Timestamp = END) -> pd.DataFrame:
    raw_dir = out / "raw" / sym
    raw_dir.mkdir(parents=True, exist_ok=True)
    monthly = list_keys(f"data/futures/um/monthly/klines/{sym}/1m/")
    months = {k.rsplit("-1m-", 1)[1][:7]: k for k in monthly}
    last_needed = (end - pd.Timedelta(minutes=1)).strftime("%Y-%m")
    keys = [k for m, k in sorted(months.items()) if m <= last_needed]
    if last_needed not in months:   # month not yet published: daily archives
        daily = list_keys(f"data/futures/um/daily/klines/{sym}/1m/")
        keys += [k for k in sorted(daily) if k.rsplit("-1m-", 1)[1][:7] == last_needed]
    parts = []
    for k in keys:
        path = raw_dir / k.rsplit("/", 1)[1]
        if not path.exists():
            r = requests.get(BASE + k, timeout=120)
            r.raise_for_status()
            path.write_bytes(r.content)
            time.sleep(0.2)
        parts.append(parse_zip(path.read_bytes()))
    return frame_from_parts(parts, end)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--symbols", nargs="*", default=list(SYMBOLS))
    a = ap.parse_args()
    out = Path(a.out)
    for sym in a.symbols:
        dest = out / f"{sym}_full.pkl"
        if dest.exists():
            print(sym, "exists, skipped", flush=True)
            continue
        df = fetch_symbol(sym, out)
        gaps = df.index.to_series().diff().dt.total_seconds().div(60).gt(1)
        print(f"{sym}: {len(df)} bars {df.index[0]} -> {df.index[-1]}, gaps>1m {int(gaps.sum())}, "
              f"largest gap {df.index.to_series().diff().max()}", flush=True)
        df.to_pickle(dest)


if __name__ == "__main__":
    main()
