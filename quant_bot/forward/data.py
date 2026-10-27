from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
from typing import Iterable

import pandas as pd

from .types import FinalizedBar, FundingEvent, MarketQuote, utc_timestamp


class ReadOnlyMarketDataAdapter(ABC):
    """Deliberately contains no balance, position, or order methods."""

    @abstractmethod
    def finalized_bars(self, symbols: Iterable[str], interval: str,
                       since: pd.Timestamp | None = None) -> list[FinalizedBar]:
        raise NotImplementedError

    @abstractmethod
    def quote(self, symbol: str) -> MarketQuote:
        raise NotImplementedError

    def funding_events(self, symbols: Iterable[str],
                       since: pd.Timestamp | None = None) -> list[FundingEvent]:
        """Return settled funding events; adapters without funding may return none."""
        return []


@dataclass(frozen=True)
class DataQualityResult:
    accepted: bool
    flags: tuple[str, ...]


class DataIntegrityGuard:
    def __init__(self, interval: str = "1m", max_receive_delay_seconds: float = 120,
                 max_clock_drift_seconds: float = 5, max_gap_fraction: float = 0.25):
        self.interval = pd.Timedelta(interval)
        self.max_receive_delay_seconds = max_receive_delay_seconds
        self.max_clock_drift_seconds = max_clock_drift_seconds
        self.max_gap_fraction = max_gap_fraction
        self._last_open: dict[str, pd.Timestamp] = {}
        self._last_close: dict[str, float] = {}

    def restore(self, symbol: str, open_time, close_price: float) -> None:
        self._last_open[symbol.upper()] = utc_timestamp(open_time)
        self._last_close[symbol.upper()] = float(close_price)

    def check(self, bar: FinalizedBar) -> DataQualityResult:
        flags: list[str] = []
        prices = (bar.open, bar.high, bar.low, bar.close)
        if not bar.is_final:
            flags.append("INCOMPLETE_CANDLE")
        if bar.receive_timestamp < bar.close_time:
            flags.append("BAR_CLOSE_USED_EARLY")
        if bar.processing_timestamp < bar.receive_timestamp:
            flags.append("TIMESTAMP_DISORDER")
        if (bar.receive_timestamp - bar.exchange_timestamp).total_seconds() < -self.max_clock_drift_seconds:
            flags.append("CLOCK_DRIFT")
        delay = (bar.receive_timestamp - bar.close_time).total_seconds()
        if delay > self.max_receive_delay_seconds:
            flags.append("STALE_DATA")
        if any(not math.isfinite(value) or value <= 0 for value in prices):
            flags.append("INVALID_PRICE")
        elif bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close) or bar.low > bar.high:
            flags.append("IMPOSSIBLE_OHLC")
        if not math.isfinite(bar.volume) or bar.volume < 0:
            flags.append("INVALID_VOLUME")

        symbol = bar.symbol.upper()
        previous_time = self._last_open.get(symbol)
        if previous_time is not None:
            delta = bar.open_time - previous_time
            if delta == pd.Timedelta(0):
                flags.append("DUPLICATE_BAR")
            elif delta < pd.Timedelta(0):
                flags.append("TIMESTAMP_DISORDER")
            elif delta > self.interval:
                flags.append("MISSING_BARS")
        previous_close = self._last_close.get(symbol)
        if previous_close and math.isfinite(bar.open):
            if abs(bar.open / previous_close - 1) > self.max_gap_fraction:
                flags.append("UNEXPECTED_GAP")

        accepted = not flags
        if accepted:
            self._last_open[symbol] = bar.open_time
            self._last_close[symbol] = bar.close
        return DataQualityResult(accepted, tuple(dict.fromkeys(flags)))
