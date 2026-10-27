"""Continuous, public-data-only Strategy A forward paper runner.

This executable contains no exchange credentials and no order submission path.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import time

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant_bot.forward.binance_public import BinancePublicMarketData
from quant_bot.forward.runner import ForwardPaperRunner
from quant_bot.forward.signal_engine import FrozenStrategyASignalEngine, load_bundle
from quant_bot.forward.store import ForwardStateStore


DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
                   "ADAUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT")


def recovery_cursor(store: ForwardStateStore, symbols: tuple[str, ...]) -> pd.Timestamp | None:
    rows = store.connection.execute(
        "SELECT symbol,MAX(close_time) AS close_time FROM bars GROUP BY symbol"
    ).fetchall()
    latest = {row["symbol"]: pd.Timestamp(row["close_time"]) for row in rows}
    # A global MAX could skip a lagging/reconnecting symbol. Fetch from the
    # earliest per-symbol cursor; persisted duplicates are harmless/idempotent.
    if any(symbol not in latest for symbol in symbols):
        return None
    return min(latest[symbol] for symbol in symbols)


def run_cycle(runner: ForwardPaperRunner, adapter: BinancePublicMarketData,
              store: ForwardStateStore, symbols: tuple[str, ...], interval: str) -> int:
    cursor = recovery_cursor(store, symbols)
    funding = adapter.funding_events(symbols, since=cursor)
    bars = adapter.finalized_bars(symbols, interval, since=cursor)
    # Replay chronologically so a historical position is present exactly when
    # a crossed funding settlement is applied. Bars closing at the settlement
    # timestamp are processed first; their entries occur after that close and
    # therefore correctly do not owe the just-settled funding event.
    timeline = ([(bar.close_time, 0, bar) for bar in bars]
                + [(event.funding_time, 1, event) for event in funding])
    for _, kind, item in sorted(timeline, key=lambda row: (row[0], row[1])):
        if kind == 0:
            runner.process_bar(item)
        else:
            runner.process_funding(item)
    return len(bars)


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper-only forward runner (never submits orders)")
    parser.add_argument("--bundle", default="docs/forward_paper/strategy_a_bundle.pkl")
    parser.add_argument("--state", default="docs/forward_paper/forward_state.sqlite3")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    bundle = load_bundle(args.bundle)
    symbols = tuple(symbol.upper() for symbol in args.symbols)
    unknown = set(symbols) - set(bundle.configs)
    if unknown:
        raise SystemExit(f"symbols absent from frozen bundle: {sorted(unknown)}")
    adapter = BinancePublicMarketData()
    store = ForwardStateStore(Path(args.state))
    runner = ForwardPaperRunner(adapter, FrozenStrategyASignalEngine(bundle), store)
    logging.info("PAPER ONLY: profiles=normal,aggressive,max-risk symbols=%s", ",".join(symbols))
    try:
        while True:
            try:
                count = run_cycle(runner, adapter, store, symbols, args.interval)
                logging.info("processed/found %d finalized bars; signals=%d", count, store.signal_count())
            except (OSError, TimeoutError) as exc:
                store.record_data_event("SYSTEM", None, "API_RECONNECT", (type(exc).__name__,), str(exc))
                logging.exception("market-data failure; state preserved, retrying")
            except Exception as exc:
                # Persist the failure before failing closed. An operator can
                # restart from the same SQLite state without replaying signals.
                store.record_data_event("SYSTEM", None, "RUNNER_FAILURE", (type(exc).__name__,), str(exc))
                logging.exception("runner failed closed")
                if args.once:
                    raise
            if args.once:
                break
            time.sleep(max(1.0, args.poll_seconds))
    finally:
        store.close()


if __name__ == "__main__":
    main()
