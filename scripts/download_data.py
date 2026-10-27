"""
scripts/download_data.py — thin CLI wrapper: klines + funding + open
interest in one call.

Usage:
    python scripts/download_data.py --symbol BTCUSDT --days 730
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta, timezone

from quant_bot.config import DATA_DIR, SYMBOLS
from quant_bot.data.download_klines import download_full_history
from quant_bot.data.download_funding_oi import download_funding_history, download_open_interest_history


def main():
    parser = argparse.ArgumentParser(description="Download klines + funding + open interest")
    parser.add_argument("--symbol", default=None, help="default: all of quant_bot.config.SYMBOLS")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--skip-funding", action="store_true")
    parser.add_argument("--skip-oi", action="store_true")
    args = parser.parse_args()

    now = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(days=args.days)
    symbols = [args.symbol.upper()] if args.symbol else SYMBOLS

    for symbol in symbols:
        download_full_history(symbol, start, now, DATA_DIR, interval=args.interval)
        if not args.skip_funding:
            download_funding_history(symbol, start, now, DATA_DIR)
        if not args.skip_oi:
            download_open_interest_history(symbol, args.days, DATA_DIR)


if __name__ == "__main__":
    main()
