"""
binance_adapter.py — Binance USDT-M Futures implementation of
ExchangeAdapter.

get_ohlcv() is real and safe: it's a read-only public endpoint, no account
needed, no legal exposure — this is what the research/backtest pipeline
uses today.

Every order/account method deliberately raises NotImplementedError with an
explanation, rather than silently working: Binance withdrew from Canada in
2023 and cannot legally onboard Canadian residents for trading (Quebec
included; see SPEC.md section 2). Do not remove these guards to "just get it
working" — implement a confirmed-compliant adapter instead, or come back to
this once execution venue legality is actually verified.
"""

from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from quant_bot.live.exchange_adapter import ExchangeAdapter, Position, OrderResult

_NOT_LEGAL_FOR_LIVE = (
    "BinanceFuturesAdapter does not support live order execution: Binance is "
    "not a confirmed-legal trading venue for Canadian residents (withdrew "
    "from Canada in 2023; see SPEC.md section 2). Implement a compliant "
    "ExchangeAdapter for your actual execution venue instead of removing "
    "this guard."
)


class BinanceFuturesAdapter(ExchangeAdapter):
    name = "binance_usdm_futures"
    BASE_URL = "https://fapi.binance.com"

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret

    def get_ohlcv(self, symbol: str, interval: str,
                   start: datetime, end: datetime) -> pd.DataFrame:
        """Thin live-fetch wrapper (no CSV I/O — for that, historical bulk
        downloads use quant_bot.data.download_klines, which this method does
        not duplicate). Single request, caller chunks if needed."""
        params = {
            "symbol": symbol, "interval": interval,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
            "limit": 1500,
        }
        resp = requests.get(f"{self.BASE_URL}/fapi/v1/klines", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "n_trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").sort_index()
        df = df[["open", "high", "low", "close", "volume", "taker_buy_base"]].astype(float)
        df = df.rename(columns={"taker_buy_base": "taker_buy_volume"})
        df["taker_sell_volume"] = df["volume"] - df["taker_buy_volume"]
        return df

    def get_balance(self, asset: str = "USDT") -> float:
        raise NotImplementedError(_NOT_LEGAL_FOR_LIVE)

    def get_position(self, symbol: str) -> Position:
        raise NotImplementedError(_NOT_LEGAL_FOR_LIVE)

    def place_order(self, symbol: str, side: str, size: float,
                     order_type: str = "MARKET",
                     price: Optional[float] = None) -> OrderResult:
        raise NotImplementedError(_NOT_LEGAL_FOR_LIVE)

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        raise NotImplementedError(_NOT_LEGAL_FOR_LIVE)

    def close_position(self, symbol: str) -> Optional[OrderResult]:
        raise NotImplementedError(_NOT_LEGAL_FOR_LIVE)
