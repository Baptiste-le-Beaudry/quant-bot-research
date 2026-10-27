"""
basics.py — shared TA/DSP building blocks for quant_bot.features.build.
Promoted from scripts/phase3_baseline.py's throwaway versions now that
Phase 3 (docs/phase3_results.md) justified building a real feature set.
"""

import numpy as np
import pandas as pd


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def rolling_vwap(df: pd.DataFrame, window: int) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    return pv.rolling(window).sum() / df["volume"].rolling(window).sum()


def rolling_autocorr_lag1(close: pd.Series, window: int = 60) -> pd.Series:
    """The one DSP-family feature Phase 3 actually validated (see
    docs/phase3_results.md) — rolling lag-1 autocorrelation of returns.
    Positive = momentum/trending regime, negative = mean-reverting regime."""
    ret = close.pct_change()
    lag1 = ret.shift(1)
    cov = ret.rolling(window).cov(lag1)
    var = lag1.rolling(window).var()
    return (cov / var).clip(-1, 1)


def rolling_hurst(close: pd.Series, window: int = 120) -> pd.Series:
    """Cheap rescaled-range Hurst estimate over a rolling window. H>0.5:
    trending/persistent, H<0.5: mean-reverting, H~0.5: random walk. Research
    from the confluence_ai_v3 session flagged this as a well-evidenced
    regime filter (see that project's memory of the Hurst-exponent
    research) — included here as a candidate feature for the redundancy
    check, not assumed useful without one."""
    log_ret = np.log(close).diff()

    def _hurst(x: np.ndarray) -> float:
        x = x[~np.isnan(x)]
        if len(x) < 20:
            return np.nan
        mean = x.mean()
        dev = np.cumsum(x - mean)
        r = dev.max() - dev.min()
        s = x.std()
        if s == 0 or r == 0:
            return 0.5
        return float(np.log(r / s) / np.log(len(x)))

    return log_ret.rolling(window).apply(_hurst, raw=True)


def realized_vol(close: pd.Series, window: int = 30) -> pd.Series:
    return close.pct_change().rolling(window).std()


def taker_imbalance(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Free order-flow proxy from SPEC.md section 3 — normalized taker
    buy-vs-sell volume imbalance, smoothed."""
    imb = (df["taker_buy_volume"] - df["taker_sell_volume"]) / df["volume"].replace(0, np.nan)
    return imb.rolling(window).mean()
