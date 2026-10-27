"""scripts/strategy_a_equity/download_universe.py -- STRATEGY_ID = A-EQUITY,
Phase 2/4 data acquisition (docs/strategy_a_equity/STRATEGY_A_EQUITY_SPEC.md
Sections 4-5). Pulls 1-minute bars for the frozen 17-symbol primary universe
(+ TSLA/NVDA as the labeled, non-independent secondary check) from
Dukascopy's free JSON candle API via the already-existing, tested
quant_bot.data.download_dukascopy.download_full_history.

Reformats each symbol's raw Dukascopy CSV (timestamp,open,high,low,close,
volume) into the project's standard klines schema (index=timestamp,
open/high/low/close/volume/taker_buy_volume/taker_sell_volume) so
quant_bot.features.build.build_feature_matrix and the existing
multi_crypto_walkforward.py-style loaders work unmodified. Equities have no
buy/sell-side split -- taker_buy_volume = taker_sell_volume = volume/2,
same disclosed convention as scripts/strategy_a/download_transfer_universe.py.

Does not touch scripts/strategy_a/, scripts/multi_crypto_walkforward.py, or
any quant_bot/ frozen module. No cost, no auth, no purchase approval needed.

Usage:
    python scripts/strategy_a_equity/download_universe.py
    python scripts/strategy_a_equity/download_universe.py --symbol NIO
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd

from quant_bot.data.download_dukascopy import download_full_history

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

END = "2026-08-27"

# Dukascopy code, per-symbol start (catalog startDayForMinuteCandles / real
# listing, per SPEC.md Section 5 -- avoids walking years of guaranteed-empty
# pre-listing days), primary(P)/secondary(S). 15 primary, post-liquidity-
# screen: F/NIO dropped 2026-08-27, see spec Amendments.
UNIVERSE = {
    "AMD": ("AMD.US-USD", "2017-01-01", "P"), "PLTR": ("PLTR.US-USD", "2020-10-01", "P"),
    "UBER": ("UBER.US-USD", "2020-10-01", "P"), "INTC": ("INTC.US-USD", "2017-01-01", "P"),
    "BAC": ("BAC.US-USD", "2017-01-01", "P"), "FB": ("FB.US-USD", "2017-01-01", "P"),
    "NFLX": ("NFLX.US-USD", "2017-01-01", "P"), "GOOGL": ("GOOGL.US-USD", "2017-01-01", "P"),
    "PYPL": ("PYPL.US-USD", "2017-01-01", "P"), "DIS": ("DIS.US-USD", "2017-01-01", "P"),
    "JNJ": ("JNJ.US-USD", "2017-01-01", "P"), "PG": ("PG.US-USD", "2017-01-01", "P"),
    "KO": ("KO.US-USD", "2017-01-01", "P"), "XOM": ("XOM.US-USD", "2017-01-01", "P"),
    "WMT": ("WMT.US-USD", "2017-01-01", "P"),
    "TSLA": ("TSLA.US-USD", "2017-01-01", "S"), "NVDA": ("NVDA.US-USD", "2017-01-01", "S"),
}

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "_dukascopy_raw")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def reformat(raw_path: str, out_path: str) -> int:
    df = pd.read_csv(raw_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    out = pd.DataFrame(index=df.index)
    out.index.name = "timestamp"
    out["open"] = df["open"]
    out["high"] = df["high"]
    out["low"] = df["low"]
    out["close"] = df["close"]
    out["volume"] = df["volume"]
    out["taker_buy_volume"] = df["volume"] / 2.0
    out["taker_sell_volume"] = df["volume"] / 2.0
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.to_csv(out_path)
    return len(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None, help="single ticker (default: full universe)")
    args = parser.parse_args()

    symbols = [args.symbol.upper()] if args.symbol else list(UNIVERSE.keys())
    os.makedirs(RAW_DIR, exist_ok=True)

    for i, symbol in enumerate(symbols, 1):
        code, start, kind = UNIVERSE[symbol]
        raw_path = os.path.join(RAW_DIR, f"{symbol}_1m_raw.csv")
        out_path = os.path.join(DATA_DIR, f"{symbol}_1m_{start.replace('-', '')}_{END.replace('-', '')}.csv")
        print(f"\n[{i}/{len(symbols)}] {symbol} ({kind}) code={code} start={start}")
        if os.path.exists(out_path):
            print(f"  already reformatted -> {out_path}")
            continue
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(END, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        download_full_history(code, start_dt, end_dt, raw_path)
        if not os.path.exists(raw_path):
            print(f"  WARNING: no raw file produced for {symbol} -- skipping")
            continue
        n = reformat(raw_path, out_path)
        print(f"  reformatted {n:,} bars -> {out_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
