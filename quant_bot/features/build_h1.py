"""
build_h1.py — H1 (hourly) variant of quant_bot.features.build, for the
autonomous-session H1 strategy across BTCUSDT/ETHUSDT/NQUSD
(quant_bot.data.h1_loader). Windows are re-derived for hourly bars, not
just copy-pasted from the 1-minute version's numbers:

  1-min window        H1 equivalent         reasoning
  60min  (1h)      -> 24h    (1 day)
  240min (4h)      -> 168h   (1 week)
  120min (2h)      -> 72h    (3 days)
  20/50/200min     -> 20/50/200h (kept literal -- already sensible on H1)
  1/5/15/60min ret -> 1/4/12/24h ret

taker_imbalance is DROPPED here: the H1 datasets (carried over from
confluence_ai_v3, and NQUSD via yfinance) don't have taker buy/sell volume,
unlike quant_bot's own 1-min Binance downloader.
"""

import numpy as np
import pandas as pd

from quant_bot.features.basics import ema, atr, rolling_vwap, rolling_autocorr_lag1, rolling_hurst, realized_vol


def build_feature_matrix_h1(df: pd.DataFrame) -> pd.DataFrame:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    out = pd.DataFrame(index=df.index)

    # -- Mean-reversion / VWAP --
    vwap24 = rolling_vwap(df, 24)
    vwap_dist = close - vwap24
    out["vwap_dist_z_24"] = vwap_dist / vwap_dist.rolling(24).std()
    vwap168 = rolling_vwap(df, 168)
    vwap_dist_168 = close - vwap168
    out["vwap_dist_z_168"] = vwap_dist_168 / vwap_dist_168.rolling(168).std()

    # -- DSP / regime --
    out["autocorr_24"] = rolling_autocorr_lag1(close, 24)
    out["autocorr_168"] = rolling_autocorr_lag1(close, 168)
    out["hurst_72"] = rolling_hurst(close, 72)

    # -- Momentum / trend --
    out["ret_1"] = close.pct_change(1)
    out["ret_4"] = close.pct_change(4)
    out["ret_12"] = close.pct_change(12)
    out["ret_24"] = close.pct_change(24)
    ema20, ema50, ema200 = ema(close, 20), ema(close, 50), ema(close, 200)
    a = atr(df, 14)
    out["dist_ema20_atr"] = (close - ema20) / a
    out["dist_ema50_atr"] = (close - ema50) / a
    out["dist_ema200_atr"] = (close - ema200) / a
    out["ema_slope_20"] = ema20.diff(5) / a

    # -- Structure --
    high_24, low_24 = high.rolling(24).max(), low.rolling(24).min()
    out["dist_high_24_atr"] = (high_24 - close) / a
    out["dist_low_24_atr"] = (close - low_24) / a
    out["range_pos_24"] = (close - low_24) / (high_24 - low_24).replace(0, np.nan)

    # -- Volatility / regime --
    out["atr_norm"] = a / close
    out["realized_vol_24"] = realized_vol(close, 24)
    out["realized_vol_ratio"] = realized_vol(close, 24) / realized_vol(close, 168).replace(0, np.nan)
    range_bar = (high - low) / close
    out["range_expansion"] = range_bar / range_bar.rolling(24).mean()

    # -- Volume (no taker buy/sell split available on H1 datasets) --
    out["rel_volume_24"] = volume / volume.rolling(24).mean().replace(0, np.nan)
    out["volume_accel"] = volume.pct_change(4)
    out["volume_to_vol_ratio"] = volume.rolling(24).mean() / (realized_vol(close, 24) + 1e-9)

    # H1 datasets (esp. NQUSD futures, thin/holiday sessions) can have exact-
    # zero ATR or volume stretches that 1-min crypto data never produced --
    # divisions above can yield inf, which breaks sklearn/downstream fits.
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def build_labels_h1(close: pd.Series, horizon_hours: int, cost_threshold_pct: float,
                     direction: str = "long") -> pd.Series:
    # BUGFIX (2026-08-24, found during scientific-validation code audit, Task B): same class as
    # quant_bot/features/build.py's build_labels -- pandas comparisons map NaN to False, so the
    # final horizon_hours rows (where fwd is NaN, no future bar exists yet) would silently become
    # class 0 instead of staying an excluded/missing label. build_labels already guards against
    # this (.where(fwd.notna())); this sibling function was missing the same guard. Verified via
    # grep that no reported/adopted experiment in docs/research_plan_status.md ever cited this
    # function's callers (scripts/h1_dedicated_model.py, scripts/h1_multi_asset_test.py) -- no
    # historical result is affected. Fixed proactively (this H1/multi-asset infrastructure could
    # be reused for future work).
    fwd = close.shift(-horizon_hours) / close - 1.0
    if direction == "short":
        label = (fwd < -cost_threshold_pct).astype(float)
    else:
        label = (fwd > cost_threshold_pct).astype(float)
    return label.where(fwd.notna())


def build_regression_label_h1(close: pd.Series, horizon_hours: int) -> pd.Series:
    return close.shift(-horizon_hours) / close - 1.0
