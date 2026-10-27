"""scripts/strategy_a/build_regime_context.py — STRATEGY_ID = A
diagnostic infrastructure (PHASE 10 mandate, 2026-08-24): builds a daily
regime-context table (BTC trend/volatility/drawdown, 9-symbol breadth,
cross-crypto correlation) for merging onto Strategy A's executed trade
log. SHADOW/ANALYTICAL ONLY -- does not touch or modify the frozen
baseline in any way.

HOLDOUT DISCIPLINE: each symbol's own price series is truncated at that
symbol's own HOLDOUT_START (quant_bot/data/splits.py, read-only,
Codex-owned canonical guard) BEFORE any computation -- a symbol simply
stops contributing to breadth/correlation/BTC-regime once its own lock
boundary is reached, rather than reading forbidden data. This means
regime fields for trades entered after BTC's own HOLDOUT_START
(2025-03-28) will correctly come out NaN for BTC-specific fields (BTC
regime/trend/drawdown), not a silently wrong value.

Usage:
    python scripts/strategy_a/build_regime_context.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR
from quant_bot.data.splits import HOLDOUT_START as _HOLDOUT_START_RAW

HOLDOUT_START = {k: pd.Timestamp(v, tz="UTC") for k, v in _HOLDOUT_START_RAW.items()}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT"]
BREADTH_LOOKBACK_DAYS = 7
CORR_WINDOW_DAYS = 30
BTC_TREND_LOOKBACK_DAYS = 30
BTC_VOL_WINDOW_DAYS = 30
BTC_VOL_PCTILE_WINDOW_DAYS = 365


def load_daily_close(symbol: str) -> pd.Series:
    pattern = os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")
    files = sorted(glob.glob(pattern))
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    daily = df["close"].resample("1D").last().dropna()
    cutoff = HOLDOUT_START[symbol]
    daily = daily[daily.index < cutoff]  # NEVER read at/after this symbol's own lock
    return daily


def main():
    print("=" * 100)
    print("  STRATEGY A diagnostic infra -- build_regime_context.py (SHADOW/ANALYTICAL, no baseline change)")
    print("=" * 100)

    closes = {}
    for sym in UNIVERSE:
        s = load_daily_close(sym)
        closes[sym] = s
        print(f"  {sym}: {len(s)} daily bars, {s.index[0].date()} -> {s.index[-1].date()}  "
              f"(truncated at own HOLDOUT_START={HOLDOUT_START[sym].date()})")

    price = pd.DataFrame(closes)  # union of all dates; NaN where a symbol hasn't started or has been truncated
    daily_ret = price.pct_change()

    # -- BTC-specific regime (NaN beyond BTC's own HOLDOUT_START, by construction of load_daily_close) --
    btc = price["BTCUSDT"]
    btc_trend = btc / btc.rolling(BTC_TREND_LOOKBACK_DAYS).mean() - 1.0  # >0 = above its own 30d MA (uptrend)
    btc_daily_ret = daily_ret["BTCUSDT"]
    btc_vol_30d = btc_daily_ret.rolling(BTC_VOL_WINDOW_DAYS).std()
    btc_vol_pctile = btc_vol_30d.rolling(BTC_VOL_PCTILE_WINDOW_DAYS, min_periods=60).rank(pct=True)
    btc_running_max = btc.cummax()
    btc_drawdown = (btc - btc_running_max) / btc_running_max

    # -- Breadth: fraction of the (still-active, non-truncated) universe with positive trailing-7d return --
    trailing_ret = price / price.shift(BREADTH_LOOKBACK_DAYS) - 1.0
    breadth = (trailing_ret > 0).sum(axis=1) / trailing_ret.notna().sum(axis=1).replace(0, np.nan)

    # -- Cross-crypto correlation: mean pairwise correlation of daily returns, trailing window --
    def mean_pairwise_corr(window_df: pd.DataFrame) -> float:
        c = window_df.corr()
        vals = c.to_numpy()
        iu = np.triu_indices_from(vals, k=1)
        pair_vals = vals[iu]
        pair_vals = pair_vals[~np.isnan(pair_vals)]
        return float(pair_vals.mean()) if len(pair_vals) else np.nan

    cross_corr = pd.Series(index=price.index, dtype=float)
    for i in range(CORR_WINDOW_DAYS, len(price)):
        window = daily_ret.iloc[i - CORR_WINDOW_DAYS:i]
        cross_corr.iloc[i] = mean_pairwise_corr(window)

    regime = pd.DataFrame({
        "btc_close": btc, "btc_trend_30d": btc_trend, "btc_vol_30d": btc_vol_30d,
        "btc_vol_pctile": btc_vol_pctile, "btc_drawdown_pct": btc_drawdown * 100,
        "breadth_7d_pct": breadth * 100, "cross_corr_30d": cross_corr,
    })

    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "strategy_a", "regime_context_daily.csv")
    regime.to_csv(out_path)
    print(f"\n  Regime context: {len(regime)} daily rows, {regime.index[0].date()} -> {regime.index[-1].date()}")
    print(f"  NaN counts: {regime.isna().sum().to_dict()}")
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
