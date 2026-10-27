"""scripts/strategy_a/mechanism/build_index_bars.py — build 1-min OHLC
mid-price bars (+volume, +median spread_pct) for QQQ/SPY from the already
-downloaded, already-audited tick data under data/strategy_c/normalized/
({QQQ,SPY}_{trades,mbp-1}_daily). Processes ONE DAY AT A TIME (memory-
constrained machine). A day is included only if BOTH trades and quotes
exist for it -- this naturally excludes 2026-04-03 (Good Friday: a single
stray quote tick, zero trades), matching Strategy C's own handling.
Crossed quotes (bid>ask) are dropped before computing mid, same fix as
quant_bot/strategy_c/features.py's quote_imbalance/spread_pct.

Read-only w.r.t. data/strategy_c/** (Strategy C is CLOSED) -- writes only
to docs/strategy_a/mechanism/.

Usage:
    python scripts/strategy_a/mechanism/build_index_bars.py
"""
import gc
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
NORMALIZED_DIR = os.path.join(REPO_ROOT, "data", "strategy_c", "normalized")
OUT_DIR = os.path.join(REPO_ROOT, "docs", "strategy_a", "mechanism")
os.makedirs(OUT_DIR, exist_ok=True)
NY_TZ = "America/New_York"
SESSION_OPEN = pd.Timestamp("09:30").time()
SESSION_CLOSE = pd.Timestamp("16:00").time()


def _list_daily_files(daily_dir: str) -> dict:
    if not os.path.isdir(daily_dir):
        return {}
    out = {}
    for fname in os.listdir(daily_dir):
        m = re.match(r"(\d{8})\.parquet$", fname)
        if m:
            out[m.group(1)] = os.path.join(daily_dir, fname)
    return dict(sorted(out.items()))


def build_bars_for_symbol(symbol: str) -> pd.DataFrame:
    trades_dir = os.path.join(NORMALIZED_DIR, f"{symbol}_trades_daily")
    quotes_dir = os.path.join(NORMALIZED_DIR, f"{symbol}_mbp-1_daily")
    trades_files = _list_daily_files(trades_dir)
    quotes_files = _list_daily_files(quotes_dir)
    common_dates = sorted(set(trades_files) & set(quotes_files))
    print(f"{symbol}: {len(common_dates)} common trading days "
          f"(trades-only: {len(set(trades_files) - set(quotes_files))}, "
          f"quotes-only: {len(set(quotes_files) - set(trades_files))})")

    daily_bars = []
    for date_str in common_dates:
        quotes = pd.read_parquet(quotes_files[date_str], columns=["bid_px_00", "ask_px_00"])
        ny_idx = quotes.index.tz_convert(NY_TZ)
        in_session = (ny_idx.time >= SESSION_OPEN) & (ny_idx.time < SESSION_CLOSE)
        quotes = quotes[in_session]
        valid = (quotes["bid_px_00"] > 0) & (quotes["ask_px_00"] > 0) & (quotes["bid_px_00"] <= quotes["ask_px_00"])
        quotes = quotes[valid]
        if len(quotes) == 0:
            del quotes
            gc.collect()
            continue
        mid = (quotes["bid_px_00"] + quotes["ask_px_00"]) / 2.0
        spread_pct = (quotes["ask_px_00"] - quotes["bid_px_00"]) / mid

        ohlc = mid.resample("1min").ohlc()
        spread_med = spread_pct.resample("1min").median().rename("median_spread_pct")

        trades = pd.read_parquet(trades_files[date_str], columns=["price", "size"])
        ny_idx_t = trades.index.tz_convert(NY_TZ)
        in_session_t = (ny_idx_t.time >= SESSION_OPEN) & (ny_idx_t.time < SESSION_CLOSE)
        trades = trades[in_session_t]
        vol = trades["size"].resample("1min").sum().rename("volume")
        n_trades = trades["size"].resample("1min").count().rename("n_trades")

        day_bars = pd.concat([ohlc, vol, n_trades, spread_med], axis=1)
        day_bars = day_bars.dropna(subset=["close"])
        ny_idx_b = day_bars.index.tz_convert(NY_TZ)
        in_session_b = (ny_idx_b.time >= SESSION_OPEN) & (ny_idx_b.time < SESSION_CLOSE)
        day_bars = day_bars[in_session_b]
        day_bars["volume"] = day_bars["volume"].fillna(0.0)
        day_bars["n_trades"] = day_bars["n_trades"].fillna(0.0)
        daily_bars.append(day_bars)

        del quotes, mid, spread_pct, ohlc, spread_med, trades, vol, n_trades, day_bars
        gc.collect()

    bars = pd.concat(daily_bars).sort_index()
    print(f"{symbol}: {len(bars):,} 1-min bars built, {pd.Series(bars.index.tz_convert(NY_TZ).date).nunique()} session-days")
    return bars


def main():
    for symbol in ["QQQ", "SPY"]:
        bars = build_bars_for_symbol(symbol)
        out_path = os.path.join(OUT_DIR, f"{symbol}_1min_bars.parquet")
        bars.to_parquet(out_path)
        print(f"  -> {out_path}")


if __name__ == "__main__":
    main()
