"""
build.py — the candidate feature matrix (SPEC.md section 5), before pruning.

This is the FULL candidate list. quant_bot.features.pipeline.prune_redundant
is what decides which of these actually ship — nothing here is assumed
useful just because it's implemented. Families are ordered by what Phase 3
(docs/phase3_results.md) actually found evidence for: mean-reversion/VWAP
and the autocorrelation regime measure first, momentum/trend second,
everything else last.
"""

import numpy as np
import pandas as pd

from quant_bot.features.basics import (
    ema, atr, rolling_vwap, rolling_autocorr_lag1, rolling_hurst,
    realized_vol, taker_imbalance,
)


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    out = pd.DataFrame(index=df.index)

    # -- Mean-reversion / VWAP family (Phase 3-validated) --
    vwap60 = rolling_vwap(df, 60)
    vwap_dist = close - vwap60
    out["vwap_dist_z_60"] = vwap_dist / vwap_dist.rolling(60).std()
    vwap240 = rolling_vwap(df, 240)
    vwap_dist_240 = close - vwap240
    out["vwap_dist_z_240"] = vwap_dist_240 / vwap_dist_240.rolling(240).std()

    # -- DSP / regime (Phase 3-validated: autocorrelation; Hurst untested but
    #    well-evidenced elsewhere, included as a candidate) --
    out["autocorr_60"] = rolling_autocorr_lag1(close, 60)
    out["autocorr_240"] = rolling_autocorr_lag1(close, 240)
    out["hurst_120"] = rolling_hurst(close, 120)

    # -- Momentum / trend --
    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_15"] = close.pct_change(15)
    out["ret_60"] = close.pct_change(60)
    ema20, ema50, ema200 = ema(close, 20), ema(close, 50), ema(close, 200)
    a = atr(df, 14)
    out["dist_ema20_atr"] = (close - ema20) / a
    out["dist_ema50_atr"] = (close - ema50) / a
    out["dist_ema200_atr"] = (close - ema200) / a
    out["ema_slope_20"] = ema20.diff(5) / a

    # -- Structure --
    high_60, low_60 = high.rolling(60).max(), low.rolling(60).min()
    out["dist_high_60_atr"] = (high_60 - close) / a
    out["dist_low_60_atr"] = (close - low_60) / a
    out["range_pos_60"] = (close - low_60) / (high_60 - low_60).replace(0, np.nan)

    # -- Volatility / regime --
    out["atr_norm"] = a / close
    out["realized_vol_30"] = realized_vol(close, 30)
    out["realized_vol_ratio"] = realized_vol(close, 30) / realized_vol(close, 240).replace(0, np.nan)
    range_bar = (high - low) / close
    out["range_expansion"] = range_bar / range_bar.rolling(60).mean()

    # -- Volume / order-flow proxy --
    out["rel_volume_20"] = volume / volume.rolling(20).mean().replace(0, np.nan)
    out["volume_accel"] = volume.pct_change(5)
    out["taker_imbalance_20"] = taker_imbalance(df, 20)
    out["volume_to_vol_ratio"] = volume.rolling(20).mean() / (realized_vol(close, 20) + 1e-9)

    # Thin/flat stretches (e.g. early-history low-volume futures bars) can
    # make ATR or a rolling volume mean exactly zero, which the divisions
    # above turn into inf and which breaks sklearn/downstream fits.
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def build_labels(close: pd.Series, horizon_min: int, cost_threshold_pct: float,
                  direction: str = "long") -> pd.Series:
    """Binary label matching SPEC.md section 6: 1 if forward return over
    horizon_min clears round-trip cost in the given direction. direction=
    'short' mirrors the long label (1 if forward return < -cost) rather
    than reusing (1 - long_label) — those aren't the same thing: a small
    move that clears neither threshold should be 0 for both, not 1 for one
    of them."""
    fwd = close.shift(-horizon_min) / close - 1.0
    if direction == "short":
        label = (fwd < -cost_threshold_pct).astype(float)
    else:
        label = (fwd > cost_threshold_pct).astype(float)
    # pandas comparisons map NaN to False. Preserve the unavailable future
    # target explicitly so the final horizon rows can never become class 0.
    return label.where(fwd.notna())


def build_regression_label(close: pd.Series, horizon_min: int) -> pd.Series:
    """Raw forward return, no threshold applied — option 2 (see
    docs/phase6_summary.md next-steps): realized_vol_30/atr_norm dominate
    every classifier's feature importance in this project so far, which
    looks like the model mostly learning move *magnitude*. A regression
    target lets it use that relationship directly instead of discarding it
    at a fixed cost-threshold cutoff the way the binary label does."""
    return close.shift(-horizon_min) / close - 1.0
