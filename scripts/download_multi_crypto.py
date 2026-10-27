"""
scripts/download_multi_crypto.py — Étape 3 of the multi-crypto expansion
plan: download 1m Binance USDT-M Futures klines for the 8-symbol candidate
universe (SOL/BNB/XRP/DOGE/ADA/LINK/AVAX/LTC), same format/pipeline as
BTC/ETH (quant_bot/data/download_klines.py, unmodified). Sequential (not
parallel) to respect Binance's shared rate limit; each symbol's download is
independently resumable via the underlying checkpoint file.

Usage:
    python scripts/download_multi_crypto.py
    python scripts/download_multi_crypto.py --symbol SOLUSDT   # single symbol
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone

from quant_bot.config import DATA_DIR
from quant_bot.data.download_klines import download_full_history

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NEW_SYMBOLS = ["SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT"]

# Actual first-available 1m bar per symbol on Binance USDT-M Futures (probed directly via
# startTime=0&limit=1, 2026-08-20) -- using these instead of BTC/ETH's nominal 2019-07-05 start
# avoids wasting ~1 hour combined hammering the empty pre-listing date range with ~1.1s/request
# (each returns an empty list, no data to write, but still costs a full round trip).
FIRST_BAR = {
    "SOLUSDT": "2020-09-14", "BNBUSDT": "2020-02-10", "XRPUSDT": "2020-01-06",
    "DOGEUSDT": "2020-07-10", "ADAUSDT": "2020-01-31", "LINKUSDT": "2020-01-17",
    "AVAXUSDT": "2020-09-23", "LTCUSDT": "2020-01-09",
}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    args = parser.parse_args()

    end = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    symbols = [args.symbol.upper()] if args.symbol else NEW_SYMBOLS
    for symbol in symbols:
        # Skip symbols already fully downloaded (a completed run leaves ONLY the final CSV --
        # partial.raw.csv/resume marker get deleted on success). Without this guard, re-invoking
        # this script with no --symbol after an interruption would blindly restart already-done
        # symbols from scratch (download_full_history has no "already complete" check of its own,
        # only a mid-download resume marker) and overwrite good data -- this bit us once already
        # (2026-08-20, the background download process was killed by the harness partway through
        # BNBUSDT; SOLUSDT was already done and would have been silently redownloaded).
        existing = glob.glob(os.path.join(DATA_DIR, f"{symbol}_1m_*.csv"))
        finished = [f for f in existing if not f.endswith(".partial.raw.csv")]
        if finished:
            print(f"{symbol}: already downloaded ({finished[-1]}), skipping.")
            continue
        start = datetime.strptime(FIRST_BAR[symbol], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        download_full_history(symbol, start, end, DATA_DIR, interval="1m")


if __name__ == "__main__":
    main()
