from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

import pandas as pd


def utc_timestamp(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return timestamp.tz_convert("UTC")


@dataclass(frozen=True)
class FinalizedBar:
    symbol: str
    interval: str
    open_time: pd.Timestamp
    close_time: pd.Timestamp
    exchange_timestamp: pd.Timestamp
    receive_timestamp: pd.Timestamp
    processing_timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    taker_buy_volume: float = 0.0
    taker_sell_volume: float = 0.0
    is_final: bool = True

    def __post_init__(self):
        for name in ("open_time", "close_time", "exchange_timestamp",
                     "receive_timestamp", "processing_timestamp"):
            object.__setattr__(self, name, utc_timestamp(getattr(self, name)))
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    exchange_timestamp: pd.Timestamp
    receive_timestamp: pd.Timestamp
    processing_timestamp: pd.Timestamp
    bid: float
    ask: float
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None

    def __post_init__(self):
        for name in ("exchange_timestamp", "receive_timestamp", "processing_timestamp"):
            object.__setattr__(self, name, utc_timestamp(getattr(self, name)))
        object.__setattr__(self, "symbol", self.symbol.upper())

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 10_000


@dataclass(frozen=True)
class FundingEvent:
    symbol: str
    funding_time: pd.Timestamp
    rate: float
    mark_price: float | None = None

    def __post_init__(self):
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "funding_time", utc_timestamp(self.funding_time))


@dataclass(frozen=True)
class SignalEvent:
    strategy_id: str
    symbol: str
    side: str
    bar_timestamp: pd.Timestamp
    signal_generated_at: pd.Timestamp
    signal_received_at: pd.Timestamp
    probability: float
    expected_entry_backtest: float
    stop_distance: float
    leverage_safe: float
    max_holding_bars: int
    trailing_activate: float = 0.0063
    trailing_distance: float = 0.0080

    def __post_init__(self):
        for name in ("bar_timestamp", "signal_generated_at", "signal_received_at"):
            object.__setattr__(self, name, utc_timestamp(getattr(self, name)))
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "side", self.side.upper())
        if self.side not in {"LONG", "SHORT"}:
            raise ValueError("side must be LONG or SHORT")
        if not 0 <= self.probability <= 1:
            raise ValueError("probability must be in [0,1]")
        if self.stop_distance <= 0 or self.leverage_safe <= 0 or self.max_holding_bars <= 0:
            raise ValueError("invalid stop/leverage/holding parameters")

    @property
    def signal_id(self) -> str:
        identity = {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "bar_timestamp": self.bar_timestamp.isoformat(),
        }
        return sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()

    def payload(self) -> dict:
        out = asdict(self)
        out["signal_id"] = self.signal_id
        for key in ("bar_timestamp", "signal_generated_at", "signal_received_at"):
            out[key] = out[key].isoformat()
        return out
