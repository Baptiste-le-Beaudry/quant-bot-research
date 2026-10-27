"""Exp 71 -- Dukascopy 1m BID download for USA30.IDX-USD (-> MYM) and USSC2000.IDX-USD (-> M2K).

Preregistration: docs/agents/hypotheses/Exp-71.md. Same JSON API, same side (BID) and same delta
decoding as the file the Exp 64 engine was validated on (quant_bot/data/download_dukascopy.py
decode_day, volume x 1e6, no synthetic flat-fill).

Resumable: one pickle per (instrument, month) under <data-dir>/raw_exp71/<NAME>/YYYY-MM.pkl, written
only once every day of the month was fetched successfully (atomic replace). Re-running skips the
months already on disk. When all months exist, --assemble writes the final CSV in the same format as
SP500_1m.csv (timestamp,open,high,low,close,volume ; UTC, start-labelled bars).

Dukascopy answers an AWS WAF challenge (HTTP 202, empty body) without a Referer since 2026-10-08
(decision D-08): the Referer header is mandatory and any non-200/404 status is an error (retried).

Never writes SP500_1m.csv / NASDAQ100_1m.csv, never overwrites an existing final CSV.

Usage:
    python scripts/agents/exp71_download.py --data-dir C:/AAProjet/quant_bot_v1/data/indices
    python scripts/agents/exp71_download.py --data-dir C:/AAProjet/quant_bot_v1/data/indices --assemble
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.data.download_dukascopy import decode_day  # noqa: E402  (same decoder as SP500_1m.csv)

API = "https://jetta.dukascopy.com/v1/candles/minute"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
           "Referer": "https://www.dukascopy.com/"}   # D-08
SIDE = "BID"
# name -> (Dukascopy code, first day = catalog startDayForMinuteCandles, output file)
INSTRUMENTS = {
    "DOW30": ("USA30.IDX-USD", "2013-09-30", "DOW30_1m.csv"),
    "RUSSELL2000": ("USSC2000.IDX-USD", "2018-08-08", "RUSSELL2000_1m.csv"),
}
END_DAY = "2026-10-09"           # inclusive (preregistration)
PROTECTED = {"SP500_1m.csv", "NASDAQ100_1m.csv"}
COLS = ["open", "high", "low", "close", "volume"]
DELAY = 0.15
MAX_ATTEMPTS = 10


class WafOrHttpError(RuntimeError):
    pass


def fetch_day(session, code: str, day: pd.Timestamp, sleep=time.sleep) -> pd.DataFrame:
    """One UTC day of 1m BID candles. 404 or empty payload -> empty frame. Anything else than 200
    (notably the WAF 202) is retried with backoff, then raises."""
    url = f"{API}/{code}/{SIDE}/{day.year}/{day.month}/{day.day}"
    last = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return empty_frame()
            if r.status_code != 200:
                raise WafOrHttpError(f"HTTP {r.status_code}")
            data = r.json()
            if not data or not data.get("times"):
                return empty_frame()
            return to_frame(decode_day(data))
        except (requests.RequestException, ValueError, WafOrHttpError) as exc:
            last = exc
            wait = min(120, 2 ** attempt)
            print(f"  {code} {day.date()} attempt {attempt}: {exc} -- retry in {wait}s", flush=True)
            sleep(wait)
    raise RuntimeError(f"giving up on {code} {day.date()}: {last}")


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([], tz="UTC", name="timestamp"), dtype=float)


def to_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["timestamp"] + COLS)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("timestamp"), unit="ms", utc=True), name="timestamp")
    return df.astype(float)


def months_for(start: str, end: str) -> pd.PeriodIndex:
    return pd.period_range(start[:7], end[:7], freq="M")


def download_stream(name: str, data_dir: Path, session=None, end_day: str = END_DAY,
                    sleep=time.sleep, delay: float = DELAY) -> int:
    code, start, _ = INSTRUMENTS[name]
    raw = Path(data_dir) / "raw_exp71" / name
    raw.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()
    n_new = 0
    for m in months_for(start, end_day):
        path = raw / f"{m}.pkl"
        if path.exists():
            continue
        first = max(m.start_time, pd.Timestamp(start))
        last = min(m.end_time.normalize(), pd.Timestamp(end_day))
        frames = []
        for day in pd.date_range(first, last, freq="D"):
            df = fetch_day(session, code, day, sleep=sleep)
            if len(df):
                frames.append(df)
            if delay:
                sleep(delay)
        month_df = pd.concat(frames).sort_index() if frames else empty_frame()
        month_df = month_df[~month_df.index.duplicated(keep="first")]
        tmp = path.with_suffix(".tmp")
        month_df.to_pickle(tmp)
        tmp.replace(path)
        n_new += 1
        print(f"{name} {m}: {len(month_df):,} bars", flush=True)
    return n_new


def assemble(name: str, data_dir: Path, end_day: str = END_DAY) -> Path:
    code, start, fname = INSTRUMENTS[name]
    if fname in PROTECTED:
        raise ValueError(f"refusing to write protected file {fname}")
    out = Path(data_dir) / fname
    if out.exists():
        raise FileExistsError(f"{out} already exists, refusing to overwrite")
    raw = Path(data_dir) / "raw_exp71" / name
    missing = [str(m) for m in months_for(start, end_day) if not (raw / f"{m}.pkl").exists()]
    if missing:
        raise RuntimeError(f"{name}: months missing {missing[:5]}... ({len(missing)})")
    parts = [pd.read_pickle(raw / f"{m}.pkl") for m in months_for(start, end_day)]
    df = pd.concat([p for p in parts if len(p)]).sort_index()
    df = df[~df.index.duplicated(keep="first")][COLS].astype(float)
    df.index.name = "timestamp"
    tmp = out.with_suffix(".csv.tmp")
    df.to_csv(tmp)
    tmp.replace(out)
    print(f"{name}: {len(df):,} bars -> {out}", flush=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--only", choices=list(INSTRUMENTS), default=None)
    a = ap.parse_args(argv)
    names = [a.only] if a.only else list(INSTRUMENTS)
    d = Path(a.data_dir)
    if a.assemble:
        for n in names:
            assemble(n, d)
        return 0
    with ThreadPoolExecutor(max_workers=len(names)) as ex:
        for fut in [ex.submit(download_stream, n, d) for n in names]:
            print("DONE", fut.result(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
