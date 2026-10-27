"""Pre-HOLDOUT market-return correlation for an explicit asset universe."""
import argparse
import glob
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quant_bot.config import DATA_DIR
from quant_bot.data.splits import assert_pre_holdout, holdout_start
from scripts.reproduce_adopted_portfolio import BOUNDARY_GUARD_ROWS, TOTAL_BARS


ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = tuple(TOTAL_BARS)


def daily_returns(frame: pd.DataFrame) -> pd.Series:
    """UTC close-to-close returns; no forward/backward filling across gaps."""
    close = frame["close"].resample("1D").last().dropna()
    return close.pct_change(fill_method=None).dropna()


def load_safe_close(symbol: str) -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")))
    if not paths:
        raise FileNotFoundError(symbol)
    first = pd.read_csv(paths[-1], usecols=["timestamp"], parse_dates=["timestamp"], nrows=1)
    first_timestamp = pd.to_datetime(first.iloc[0, 0], utc=True)
    # A continuous-minute upper bound is fail-safe when source data has gaps:
    # it can only stop earlier than intended, never cross the locked boundary.
    nrows = int((holdout_start(symbol) - first_timestamp) / pd.Timedelta(minutes=1)) - BOUNDARY_GUARD_ROWS
    if nrows <= 0:
        raise ValueError(f"no safe pre-HOLDOUT rows for {symbol}")
    frame = pd.read_csv(paths[-1], usecols=["timestamp", "close"], parse_dates=["timestamp"], nrows=nrows)
    frame = frame.set_index("timestamp").sort_index()
    frame.index = pd.to_datetime(frame.index, utc=True)
    assert_pre_holdout(frame, symbol)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(TOTAL_BARS))
    parser.add_argument("--prefix", default="validation_market_return")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    symbols = tuple(value.strip().upper() for value in args.symbols.split(",") if value.strip())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    returns = {}
    for symbol in symbols:
        print(f"daily returns {symbol}", flush=True)
        returns[symbol] = daily_returns(load_safe_close(symbol))
    panel = pd.DataFrame(returns)
    panel.corr(min_periods=90).to_csv(args.out_dir / f"{args.prefix}_correlation.csv")
    panel.count().rename("daily_observations").to_csv(args.out_dir / f"{args.prefix}_observations.csv")
    print(panel.corr(min_periods=90).round(3).to_string())


if __name__ == "__main__":
    main()
