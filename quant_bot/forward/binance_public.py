"""Public, read-only Binance market-data adapter. It has no order methods."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd
import requests

from .data import ReadOnlyMarketDataAdapter
from .types import FinalizedBar, FundingEvent, MarketQuote


class BinancePublicMarketData(ReadOnlyMarketDataAdapter):
    BASE_URL = "https://fapi.binance.com"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    @staticmethod
    def _now() -> pd.Timestamp:
        return pd.Timestamp(datetime.now(timezone.utc))

    def _get(self, path: str, params: dict):
        response = self.session.get(f"{self.BASE_URL}{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.json(), self._now()

    def finalized_bars(self, symbols: Iterable[str], interval: str,
                       since: pd.Timestamp | None = None) -> list[FinalizedBar]:
        output: list[FinalizedBar] = []
        now = self._now()
        for symbol in symbols:
            params = {"symbol": symbol.upper(), "interval": interval, "limit": 1500}
            if since is not None:
                params["startTime"] = int(pd.Timestamp(since).timestamp() * 1000)
            rows, received = self._get("/fapi/v1/klines", params)
            for row in rows:
                close_time = pd.to_datetime(row[6], unit="ms", utc=True)
                if close_time > received:
                    continue
                output.append(FinalizedBar(
                    symbol=symbol, interval=interval,
                    open_time=pd.to_datetime(row[0], unit="ms", utc=True),
                    close_time=close_time,
                    exchange_timestamp=close_time, receive_timestamp=received,
                    processing_timestamp=now, open=float(row[1]), high=float(row[2]),
                    low=float(row[3]), close=float(row[4]), volume=float(row[5]),
                    taker_buy_volume=float(row[9]),
                    taker_sell_volume=float(row[5]) - float(row[9]), is_final=True,
                ))
        return sorted(output, key=lambda bar: (bar.open_time, bar.symbol))

    def quote(self, symbol: str) -> MarketQuote:
        book, received = self._get("/fapi/v1/ticker/bookTicker", {"symbol": symbol.upper()})
        premium, premium_received = self._get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
        exchange_time = pd.to_datetime(premium.get("time"), unit="ms", utc=True)
        return MarketQuote(
            symbol=symbol, exchange_timestamp=exchange_time,
            receive_timestamp=max(received, premium_received), processing_timestamp=self._now(),
            bid=float(book["bidPrice"]), ask=float(book["askPrice"]),
            mark_price=float(premium["markPrice"]), index_price=float(premium["indexPrice"]),
            funding_rate=float(premium["lastFundingRate"]),
        )

    def funding_events(self, symbols: Iterable[str],
                       since: pd.Timestamp | None = None) -> list[FundingEvent]:
        output = []
        for symbol in symbols:
            params = {"symbol": symbol.upper(), "limit": 1000}
            if since is not None:
                params["startTime"] = int(pd.Timestamp(since).timestamp() * 1000)
            rows, _ = self._get("/fapi/v1/fundingRate", params)
            output.extend(FundingEvent(
                symbol=symbol,
                funding_time=pd.to_datetime(row["fundingTime"], unit="ms", utc=True),
                rate=float(row["fundingRate"]),
                mark_price=float(row["markPrice"]) if row.get("markPrice") else None,
            ) for row in rows)
        return sorted(output, key=lambda event: (event.funding_time, event.symbol))
