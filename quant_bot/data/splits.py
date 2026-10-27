"""Canonical pre-HOLDOUT boundaries and fail-closed research guards."""
from __future__ import annotations

import pandas as pd


HOLDOUT_START = {
    "BTCUSDT": "2025-03-28", "ETHUSDT": "2025-04-13",
    "XRPUSDT": "2025-04-23", "LTCUSDT": "2025-04-24",
    "LINKUSDT": "2025-04-25", "ADAUSDT": "2025-04-28",
    "BNBUSDT": "2025-04-30", "DOGEUSDT": "2025-05-30",
    "SOLUSDT": "2025-06-13", "AVAXUSDT": "2025-06-14",
}


class HoldoutLockedError(RuntimeError):
    pass


def holdout_start(symbol: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(HOLDOUT_START[symbol.upper()], tz="UTC")
    except KeyError as exc:
        raise KeyError(f"No preregistered HOLDOUT boundary for {symbol}") from exc


def pre_holdout(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Return only rows strictly before the preregistered HOLDOUT boundary."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("data must use a DatetimeIndex")
    index = pd.to_datetime(df.index, utc=True)
    return df.loc[index < holdout_start(symbol)].copy()


def assert_pre_holdout(df: pd.DataFrame, symbol: str) -> None:
    if len(df) and pd.to_datetime(df.index, utc=True).max() >= holdout_start(symbol):
        raise HoldoutLockedError(f"{symbol} frame reaches locked HOLDOUT")


def unlock_holdout(*_args, **_kwargs):
    """No programmatic unlock exists during the current research mandate."""
    raise HoldoutLockedError("HOLDOUT unlock is disabled; a separate explicit user decision is required")
