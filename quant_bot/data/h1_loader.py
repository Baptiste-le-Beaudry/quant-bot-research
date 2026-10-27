"""
h1_loader.py — loads the H1 datasets carried over from confluence_ai_v3
(BTCUSDT/ETHUSDT, 9 years, 2017-2026) and NQUSD (Nasdaq futures via yfinance,
2.4 years) for the H1 strategy variant (autonomous session: "une pour eth,
btc et nasdaq sur 1h"). These are OHLCV only -- no taker buy/sell volume
column (unlike quant_bot's own 1-min Binance downloader), so
quant_bot.features.build_h1 excludes the taker_imbalance feature family.
"""

import os

import pandas as pd

from quant_bot.config import DATA_DIR, TRAIN_FRACTION, VALIDATION_FRACTION

H1_SYMBOLS = {"BTCUSDT": "BTCUSDT_1h_full.csv", "ETHUSDT": "ETHUSDT_1h_full.csv", "NQUSD": "NQUSD_1h_full.csv"}


def load_h1_full(symbol: str) -> pd.DataFrame:
    fname = H1_SYMBOLS.get(symbol)
    if fname is None:
        raise ValueError(f"No H1 dataset registered for {symbol!r}, have: {list(H1_SYMBOLS)}")
    path = os.path.join(DATA_DIR, fname)
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    df = df.set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]].dropna()


def load_h1_split(symbol: str, split: str, verbose: bool = True) -> pd.DataFrame:
    df = load_h1_full(symbol)
    n = len(df)
    train_end = int(n * TRAIN_FRACTION)
    val_end = int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))
    bounds = {"train": (0, train_end), "validation": (train_end, val_end),
              "holdout": (val_end, n), "oos": (train_end, n)}
    if split not in bounds:
        raise ValueError(f"split must be one of {list(bounds)}, got {split!r}")
    start, end = bounds[split]
    out = df.iloc[start:end]
    if verbose:
        print(f"{symbol} H1 [{split.upper()}]: {len(out):,} bars "
              f"({out.index[0]:%Y-%m-%d} -> {out.index[-1]:%Y-%m-%d})")
    return out
