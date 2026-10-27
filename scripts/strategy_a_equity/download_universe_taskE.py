"""scripts/strategy_a_equity/download_universe_taskE.py -- Task E
independent confirmation universe (docs/strategy_a_equity/
STRATEGY_A_EQUITY_TASKS_A_E.md), 16 symbols, frozen before any download or
result exists on them. Same Dukascopy pull + reformat logic as
download_universe.py, separate module so the discovery-sample download
script/output is never touched.

Usage:
    python scripts/strategy_a_equity/download_universe_taskE.py
    python scripts/strategy_a_equity/download_universe_taskE.py --symbol AMZN
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

# Dukascopy code, per-symbol start, per SPEC's Task E table (16 symbols,
# post-liquidity-screen: SNAP/PFE dropped 2026-08-29)
UNIVERSE = {
    "AMZN": ("AMZN.US-USD", "2017-01-01"), "BA": ("BA.US-USD", "2017-01-01"),
    "BABA": ("BABA.US-USD", "2017-01-01"), "MU": ("MU.US-USD", "2017-01-01"),
    "C": ("C.US-USD", "2017-01-01"), "CRM": ("CRM.US-USD", "2017-01-01"),
    "ADBE": ("ADBE.US-USD", "2017-01-01"), "QCOM": ("QCOM.US-USD", "2017-01-01"),
    "TXN": ("TXN.US-USD", "2017-01-01"), "AVGO": ("AVGO.US-USD", "2017-01-01"),
    "CSCO": ("CSCO.US-USD", "2017-01-01"), "V": ("V.US-USD", "2017-01-01"),
    "MA": ("MA.US-USD", "2017-01-01"), "PEP": ("PEP.US-USD", "2017-01-01"),
    "MCD": ("MCD.US-USD", "2017-01-01"), "COST": ("COST.US-USD", "2017-01-01"),
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
    parser.add_argument("--symbol", default=None)
    args = parser.parse_args()

    symbols = [args.symbol.upper()] if args.symbol else list(UNIVERSE.keys())
    os.makedirs(RAW_DIR, exist_ok=True)

    for i, symbol in enumerate(symbols, 1):
        code, start = UNIVERSE[symbol]
        raw_path = os.path.join(RAW_DIR, f"{symbol}_1m_raw.csv")
        out_path = os.path.join(DATA_DIR, f"{symbol}_1m_{start.replace('-', '')}_{END.replace('-', '')}.csv")
        print(f"\n[{i}/{len(symbols)}] {symbol} code={code} start={start}")
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
