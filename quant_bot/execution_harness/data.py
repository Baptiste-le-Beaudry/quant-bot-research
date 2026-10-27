"""Read-only access to cached 1m OHLC bars.

The cache (``docs/_full_data_cache/<SYMBOL>_full.pkl``) is git-ignored, so a
worktree usually does not have it. Resolution order for the directory:
explicit argument > env ``QB_BAR_CACHE`` > ``<repo>/docs/_full_data_cache``.
This module never writes.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]


def cache_dir(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("QB_BAR_CACHE")
    if env:
        return Path(env)
    return REPO / "docs" / "_full_data_cache"


@lru_cache(maxsize=2)
def _load(path: str) -> pd.DataFrame:
    df = pd.read_pickle(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"{path}: index is not a DatetimeIndex")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    return df[["open", "high", "low", "close"]]


def load_bars(symbol: str, directory: str | os.PathLike | None = None) -> pd.DataFrame:
    path = cache_dir(directory) / f"{symbol}_full.pkl"
    if not path.exists():
        raise FileNotFoundError(f"no cached bars for {symbol} at {path} (set QB_BAR_CACHE)")
    return _load(str(path))
