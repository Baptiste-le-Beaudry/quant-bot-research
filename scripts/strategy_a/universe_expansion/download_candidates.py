"""RESEARCH_ONLY / NOT_ADOPTED / NOT_FORWARD_PAPER.

Download the preregistered UE-20260825-01 batch from public Binance USD-M
endpoints.  This script never imports or mutates forward-paper components.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from quant_bot.data.download_klines import download_full_history

BATCH = "UE-20260825-01"
LOCK = ROOT / "docs/strategy_a/universe_expansion/candidate_universe_lock.csv"
OUT = ROOT / "outputs/strategy_a/universe_expansion"
DATA = OUT / "data"
METADATA = OUT / "candidate_market_metadata.json"
EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"
TICKER_24H = "https://fapi.binance.com/fapi/v1/ticker/24hr"


def locked_candidates() -> list[dict[str, str]]:
    with LOCK.open(newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["category"] == "NEW_CANDIDATE"]


def public_metadata() -> dict:
    info = requests.get(EXCHANGE_INFO, timeout=20)
    tick = requests.get(TICKER_24H, timeout=20)
    info.raise_for_status()
    tick.raise_for_status()
    symbols = {x["symbol"]: x for x in info.json()["symbols"]}
    tickers = {x["symbol"]: x for x in tick.json()}
    rows = []
    for locked in locked_candidates():
        symbol = locked["symbol"]
        market = symbols.get(symbol, {})
        ticker = tickers.get(symbol, {})
        rows.append({
            "symbol": symbol,
            "contractType": market.get("contractType"),
            "status": market.get("status"),
            "quoteAsset": market.get("quoteAsset"),
            "onboardDate": market.get("onboardDate"),
            "volume_24h_base": ticker.get("volume"),
            "volume_24h_quote": ticker.get("quoteVolume"),
            "count_24h": ticker.get("count"),
            "eligible": market.get("contractType") == "PERPETUAL"
                        and market.get("status") == "TRADING"
                        and market.get("quoteAsset") == "USDT",
        })
    return {
        "research_status": ["RESEARCH_ONLY", "NOT_ADOPTED", "NOT_FORWARD_PAPER"],
        "batch_id": BATCH,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": [EXCHANGE_INFO, TICKER_24H],
        "symbols": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--symbol")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    try:
        metadata = public_metadata()
    except requests.RequestException as exc:
        print(f"NETWORK_BLOCKED: public Binance metadata unavailable: {exc}", file=sys.stderr)
        return 2
    METADATA.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    ineligible = [x["symbol"] for x in metadata["symbols"] if not x["eligible"]]
    if ineligible:
        print(f"DATA_REJECT before download: {', '.join(ineligible)}", file=sys.stderr)
        return 3
    if args.metadata_only:
        return 0

    candidates = locked_candidates()
    if args.symbol:
        candidates = [x for x in candidates if x["symbol"] == args.symbol.upper()]
        if not candidates:
            parser.error("--symbol is not in the frozen candidate batch")
    for item in candidates:
        start = datetime.fromisoformat(item["nominal_first_available_utc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(item["collection_end_exclusive_utc"].replace("Z", "+00:00"))
        download_full_history(item["symbol"], start, end, str(DATA), interval="1m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

