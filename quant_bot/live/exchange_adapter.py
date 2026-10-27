"""
exchange_adapter.py — the venue-agnostic contract (SPEC.md section 2).

Every execution path in quant_bot (backtest fill simulation, paper trading,
eventual live trading) is written against ExchangeAdapter, never against a
specific exchange's SDK. Binance USDT-M Futures is confirmed as the
data/research venue, but it is NOT a confirmed-legal live-execution venue
for Canadian residents (Binance withdrew from Canada in 2023; Canadian
regulators additionally restrict retail derivatives access). Swapping the
execution venue for whatever is confirmed compliant later — a
Canada-registered platform, an MT5 CFD broker as confluence_ai_v3 used, or a
different jurisdiction's account — means writing one new adapter class, not
touching backtest/, risk/, signal/, or management/.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class Position:
    symbol: str
    side: str            # "LONG" | "SHORT" | "FLAT"
    size: float
    entry_price: float
    unrealized_pnl: float = 0.0


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: str             # "BUY" | "SELL"
    size: float
    price: float
    status: str            # "FILLED" | "PENDING" | "REJECTED" | ...


class ExchangeAdapter(ABC):
    """Abstract venue contract. See module docstring."""

    name: str

    @abstractmethod
    def get_ohlcv(self, symbol: str, interval: str,
                   start: datetime, end: datetime) -> pd.DataFrame:
        """Historical OHLCV, indexed by UTC timestamp. Read-only, no
        account/legal exposure — this is the one method the research/backtest
        pipeline actually depends on today."""
        raise NotImplementedError

    @abstractmethod
    def get_balance(self, asset: str = "USDT") -> float:
        raise NotImplementedError

    @abstractmethod
    def get_position(self, symbol: str) -> Position:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, symbol: str, side: str, size: float,
                     order_type: str = "MARKET",
                     price: Optional[float] = None) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def close_position(self, symbol: str) -> Optional[OrderResult]:
        raise NotImplementedError
