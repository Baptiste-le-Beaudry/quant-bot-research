"""scripts/download_phase_a_candidates.py — Strategy A Phase A (2026-08-23):
download 1m Binance USDT-M Futures klines for the Phase A new-crypto
shortlist (ETCUSDT, TRXUSDT, DOTUSDT), same pipeline/format as every prior
symbol (quant_bot/data/download_klines.py, unmodified). Sequential, resumable.

STRATEGY_ID = A (this is Strategy A's cautious-expansion Phase A, not
Strategy B).

Usage:
    python scripts/download_phase_a_candidates.py
"""
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

NEW_SYMBOLS = ["ETCUSDT", "TRXUSDT", "DOTUSDT"]
# Probed directly (startTime=0&limit=1, 2026-08-23), same discipline as download_multi_crypto.py.
FIRST_BAR = {"ETCUSDT": "2020-01-16", "TRXUSDT": "2020-01-15", "DOTUSDT": "2020-08-22"}


def main():
    now = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    for symbol in NEW_SYMBOLS:
        start = datetime.strptime(FIRST_BAR[symbol], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        download_full_history(symbol, start, now, DATA_DIR, interval="1m")


if __name__ == "__main__":
    main()
