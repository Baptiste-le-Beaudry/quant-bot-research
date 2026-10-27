"""scripts/strategy_a/download_transfer_universe.py — STRATEGY_ID = A,
transfer-validation data acquisition (docs/strategy_a/
STRATEGY_A_TRANSFER_VALIDATION.md's pre-registered Phase 2 universe).

Pre-registered universe (frozen BEFORE any Strategy A backtest on these
assets, chosen on exogenous criteria only: liquidity, high realized
volatility, sufficient history, reliable consolidated-tape coverage):
  - High-vol liquid single stocks: TSLA, NVDA, MSTR
  - 2-3x leveraged ETFs: TQQQ, SOXL, SPXL

Databento EQUS.MINI, schema=ohlcv-1m (aggregated 1-min bars, NOT tick
trades/quotes — much lighter than the earlier Strategy C tick-data
pulls). Cost confirmed via metadata.get_cost BEFORE this script was
approved to run: $1.67 total for all 6 symbols, within the remaining
Databento free credit (no new purchase/subscription). Window:
2023-03-28 (EQUS.MINI's own earliest available date for this schema —
verified via a 422 error on an earlier start date, not a choice) to
today. Small enough (~170MB total) to use the streaming API directly
rather than a batch job.

Output CSV schema matches the existing crypto klines convention exactly
(data/{SYMBOL}_1m_*.csv: index=timestamp (UTC), columns open/high/low/
close/volume/taker_buy_volume/taker_sell_volume) so the FROZEN
`scripts/multi_crypto_walkforward.py`'s `_load_full_cached` loader and
`quant_bot/features/build.py`'s `build_feature_matrix` work unmodified.
Equities have no taker buy/sell split (that's a crypto futures-specific
field) — taker_buy_volume/taker_sell_volume are each set to volume/2,
making `taker_imbalance_20` a constant 0 (neutral/uninformative, not
NaN — NaN would zero out every row via prune_redundant's all-columns-
notna validity mask). This is disclosed explicitly, not a silent
approximation.

Usage:
    python scripts/strategy_a/download_transfer_universe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv

load_dotenv()

import databento as db
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATASET = "EQUS.MINI"
SCHEMA = "ohlcv-1m"
SYMBOLS = ["TSLA", "NVDA", "MSTR", "TQQQ", "SOXL", "SPXL"]
START = "2023-03-28"
END = "2026-08-26"

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def get_client():
    return db.Historical(os.environ["DATABENTO_API_KEY"])


def download_symbol(client, symbol: str) -> pd.DataFrame:
    store = client.timeseries.get_range(
        dataset=DATASET, symbols=[symbol], schema=SCHEMA, start=START, end=END,
    )
    df = store.to_df()
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "timestamp"
    df = df.sort_index()
    out = pd.DataFrame(index=df.index)
    out["open"] = df["open"]
    out["high"] = df["high"]
    out["low"] = df["low"]
    out["close"] = df["close"]
    out["volume"] = df["volume"]
    out["taker_buy_volume"] = df["volume"] / 2.0
    out["taker_sell_volume"] = df["volume"] / 2.0
    return out


def main():
    client = get_client()
    os.makedirs(DATA_DIR, exist_ok=True)
    for symbol in SYMBOLS:
        out_path = os.path.join(DATA_DIR, f"{symbol}_1m_{START.replace('-', '')}_{END.replace('-', '')}.csv")
        if os.path.exists(out_path):
            print(f"  {symbol}: already downloaded -> {out_path}")
            continue
        print(f"Downloading {symbol}...")
        df = download_symbol(client, symbol)
        df.to_csv(out_path)
        print(f"  {symbol}: {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
