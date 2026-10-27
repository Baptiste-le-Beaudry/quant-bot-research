"""
simple_engine.py — Phase 3 no-AI baseline evaluator (SPEC.md section 1's
"before any AI, know if the data even contains an edge").

This is NOT the real backtest engine (that's quant_bot.backtest's walk-
forward engine, built once a rule/model family shows something worth
protecting against overfitting — SPEC.md section 8). This one answers a
narrower, cheaper question: for a given entry condition, does holding for a
fixed horizon produce a return distribution that beats costs and beats a
buy-and-hold/random baseline — on the TRAIN slice only.

Known simplification, on purpose for a first-pass screen: overlapping
positions are not modeled (if the signal fires on consecutive bars, this
does not account for shared capital) — this measures "is the entry
condition predictive," not "what would a funded account actually earn."
That distinction is exactly why this stays out of quant_bot.backtest proper.
"""

import numpy as np
import pandas as pd

from quant_bot.config import ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST

COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST


def evaluate_signal(close: pd.Series, signal: pd.Series, horizon_min: int) -> dict:
    """signal: +1 (long), -1 (short), 0 (flat/no trade) per bar, same index as close."""
    fwd = close.shift(-horizon_min) / close - 1.0
    active = signal[signal != 0].index
    if len(active) == 0:
        return {"n_trades": 0}
    trade_returns = (signal.loc[active] * fwd.loc[active] - COST_PCT).dropna()
    if len(trade_returns) == 0:
        return {"n_trades": 0}

    wins = trade_returns[trade_returns > 0]
    losses = trade_returns[trade_returns <= 0]
    gross_profit = wins.sum()
    gross_loss = -losses.sum()

    return {
        "n_trades": int(len(trade_returns)),
        "win_rate_pct": round(len(wins) / len(trade_returns) * 100, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else float("inf"),
        "expectancy_pct": round(trade_returns.mean() * 100, 5),
        "total_naive_return_pct": round(trade_returns.sum() * 100, 2),  # naive sum, not
                                                                          # compounded/sized —
                                                                          # a screening signal,
                                                                          # not a P&L claim
        "sharpe_like": round(trade_returns.mean() / trade_returns.std(), 4) if trade_returns.std() > 0 else 0.0,
    }


def buy_and_hold_return_pct(close: pd.Series) -> float:
    return float(close.iloc[-1] / close.iloc[0] - 1.0) * 100.0


def null_baseline(close: pd.Series, n_signals: int, horizon_min: int, seed: int = 42) -> dict:
    """Random entries, random direction, same count as the rule being compared
    against — the honest bar a real signal has to clear (SPEC.md section 10's
    spirit: don't trust a number without a null to compare it to)."""
    rng = np.random.default_rng(seed)
    valid_idx = close.index[: -horizon_min] if horizon_min > 0 else close.index
    if len(valid_idx) < n_signals:
        n_signals = len(valid_idx)
    chosen = rng.choice(valid_idx, size=n_signals, replace=False)
    signal = pd.Series(0, index=close.index)
    signal.loc[chosen] = rng.choice([-1, 1], size=n_signals)
    return evaluate_signal(close, signal, horizon_min)
