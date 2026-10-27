"""Exp 54 (A-COMMOD-001) -- Dukascopy 1m BID+ASK download for the six
pre-registered commodities (docs/agents/hypotheses/Exp-54.md).

Same JSON API and delta decoding as scripts/feasibility_commodities.py
(quant_bot.equity_forward.decode_dukascopy_candles, imported from
paper_trading_bot/). Writes one pickle per (instrument, side, month) under
data/commodities/raw/ (outside git) -- a month file is the checkpoint: it
is written only once every day of that month was fetched successfully.

Downloading data up to 2026-09-30 is NOT reading it: the modelling script
(exp54_commodities.py) drops every bar >= 2025-10-01 (locked HOLDOUT) at
load time and asserts it.

Parallelism: one thread per (instrument, side) stream, i.e. 12 streams,
each paced sequentially.

Usage:
    python scripts/agents/exp54_download.py [--data-root C:/AAProjet/quant_bot_v1/data/commodities]
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
sys.path.insert(0, str(ROOT / "paper_trading_bot"))
from quant_bot.equity_forward import decode_dukascopy_candles  # noqa: E402

# name -> (Dukascopy code, first day to request = max(2012-01-01, catalog startDayForMinuteCandles))
INSTRUMENTS = {
    "XAUUSD": ("XAU-USD", "2012-01-01"),
    "XAGUSD": ("XAG-USD", "2012-01-01"),
    "WTI": ("LIGHT.CMD-USD", "2012-01-01"),
    "BRENT": ("BRENT.CMD-USD", "2012-01-01"),
    "COPPER": ("COPPER.CMD-USD", "2012-03-02"),
    "GAS": ("GAS.CMD-USD", "2012-09-02"),
}
SIDES = ("BID", "ASK")
END_DAY = "2026-09-30"  # inclusive
HEADERS = {"User-Agent": "Mozilla/5.0"}
DELAY = 0.1


def fetch_day(session, code, side, day):
    url = f"https://jetta.dukascopy.com/v1/candles/minute/{code}/{side}/{day.year}/{day.month}/{day.day}"
    for attempt in range(8):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return pd.DataFrame()
            r.raise_for_status()
            data = r.json()
            return decode_dukascopy_candles(data) if data.get("times") else pd.DataFrame()
        except (requests.RequestException, ValueError) as exc:
            wait = min(60, 2 ** attempt)
            print(f"  {code} {side} {day.date()} attempt {attempt}: {exc} -- retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"giving up on {code} {side} {day.date()}")


def stream(name, side, raw_root: Path):
    code, start = INSTRUMENTS[name]
    out_dir = raw_root / f"{name}_{side}"
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    months = pd.period_range(start[:7], END_DAY[:7], freq="M")
    for m in months:
        path = out_dir / f"{m}.pkl"
        if path.exists():
            continue
        first = max(m.start_time, pd.Timestamp(start))
        last = min(m.end_time.normalize(), pd.Timestamp(END_DAY))
        frames = []
        for day in pd.date_range(first, last, freq="D"):
            df = fetch_day(session, code, side, day)
            if len(df):
                frames.append(df)
            time.sleep(DELAY)
        month_df = pd.concat(frames).sort_index() if frames else pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"])
        month_df = month_df[~month_df.index.duplicated(keep="first")]
        tmp = path.with_suffix(".tmp")
        month_df.to_pickle(tmp)
        tmp.replace(path)
        print(f"{name} {side} {m}: {len(month_df):,} bars", flush=True)
    return name, side


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=str(Path("C:/AAProjet/quant_bot_v1/data/commodities")))
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    raw_root = Path(args.data_root) / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    jobs = [(n, s) for n in INSTRUMENTS for s in SIDES]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in [ex.submit(stream, n, s, raw_root) for n, s in jobs]:
            print("DONE", fut.result(), flush=True)


if __name__ == "__main__":
    main()
