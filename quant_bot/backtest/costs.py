"""
costs.py — the cost waterfall SPEC.md section 9 calls for and that hadn't
been built yet: gross edge -> after fees -> after fees+slippage -> after
fees+slippage+funding, computed separately so it's possible to tell "weak
signal that doesn't survive costs" apart from "no real signal at all."

Funding was downloaded (quant_bot.data.download_funding_oi) but never
applied to any backtest P&L until this file — every prior result in this
project's docs/ used fees+slippage only.
"""

import os
import glob

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR, TAKER_FEE_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, MAKER_FEE_PCT

MAKER_ROUND_TRIP_PCT = MAKER_FEE_PCT * 2


def load_funding(symbol: str) -> pd.Series:
    pattern = os.path.join(DATA_DIR, f"{symbol}_funding_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No funding CSV for {symbol} in {DATA_DIR}")
    df = pd.read_csv(files[-1], index_col=0)
    df.index = pd.to_datetime(df.index, utc=True, format="ISO8601")
    return df["fundingRate"].sort_index()


def funding_cost_per_bar(close_index: pd.DatetimeIndex, funding: pd.Series) -> pd.Series:
    """Cumulative funding rate reindexed onto the 1-min bar index — a
    trade's total funding cost between bar i and bar j is
    cum[j] - cum[i] (sign-adjusted for direction by the caller). Vectorized:
    avoids a per-trade timestamp-matching loop over what can be thousands
    of trades."""
    # funding timestamps won't exactly match 1-min bar timestamps in general
    # (funding events carry a few ms of jitter in the raw API data), so map
    # each funding event onto the nearest bar at-or-after it rather than an
    # exact-match reindex.
    at_bar = pd.Series(0.0, index=close_index)
    idx_pos = close_index.searchsorted(funding.index)
    valid = idx_pos < len(close_index)
    at_bar.iloc[idx_pos[valid]] = funding.values[valid]
    return at_bar.cumsum()


def waterfall(close: pd.Series, entry_mask: pd.Series, horizon_min: int, direction: str,
              funding: pd.Series | None = None) -> dict:
    """For every bar where entry_mask is True, compute the forward return at
    four cost levels. Does NOT enforce one-trade-at-a-time (SPEC.md section
    11's rule) on purpose — this is a diagnostic on the raw selected
    population's edge, not a portfolio simulation; quant_bot.backtest.engine
    is still what a go/no-go decision should use for the tradeable version."""
    sign = 1.0 if direction == "long" else -1.0
    fwd = sign * (close.shift(-horizon_min) / close - 1.0)
    selected = fwd[entry_mask.reindex(fwd.index, fill_value=False) & fwd.notna()]

    if len(selected) == 0:
        return {"n_trades": 0}

    gross = selected
    after_fees = gross - ROUND_TRIP_FEE_PCT
    after_fees_slip = gross - ROUND_TRIP_FEE_PCT - SLIPPAGE_PCT_EST

    if funding is not None:
        cum_funding = funding_cost_per_bar(close.index, funding)
        entry_idx = close.index.get_indexer(selected.index)
        exit_idx = np.clip(entry_idx + horizon_min, 0, len(close.index) - 1)
        funding_cost = sign * (cum_funding.values[exit_idx] - cum_funding.values[entry_idx])
        after_all = pd.Series(after_fees_slip.values - funding_cost, index=selected.index)
    else:
        after_all = after_fees_slip
        funding_cost = np.zeros(len(selected))

    def _pf(returns: pd.Series) -> float:
        wins, losses = returns[returns > 0], returns[returns <= 0]
        gp, gl = wins.sum(), -losses.sum()
        return float(gp / gl) if gl > 0 else float("inf")

    return {
        "n_trades": len(selected),
        "gross_mean_pct": round(float(gross.mean() * 100), 5),
        "after_fees_mean_pct": round(float(after_fees.mean() * 100), 5),
        "after_fees_slip_mean_pct": round(float(after_fees_slip.mean() * 100), 5),
        "after_all_mean_pct": round(float(after_all.mean() * 100), 5),
        "avg_funding_pct": round(float(np.mean(funding_cost) * 100), 6),
        "pf_gross": round(_pf(gross), 3),
        "pf_after_fees_slip": round(_pf(after_fees_slip), 3),
        "pf_after_all": round(_pf(after_all), 3),
        "win_rate_after_all_pct": round(float((after_all > 0).mean() * 100), 2),
        "avg_win_pct": round(float(after_all[after_all > 0].mean() * 100), 5) if (after_all > 0).any() else 0.0,
        "avg_loss_pct": round(float(after_all[after_all <= 0].mean() * 100), 5) if (after_all <= 0).any() else 0.0,
    }
