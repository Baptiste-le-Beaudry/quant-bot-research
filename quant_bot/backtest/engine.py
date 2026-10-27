"""
engine.py — the real backtest engine (SPEC.md section 8), used once Phase 6
promotes a specific model+threshold configuration worth spending the
one-time HOLDOUT evaluation on.

Unlike quant_bot.backtest.simple_engine (Phase 3's cheap screening tool,
which fires on every signal independently, overlap and all), this enforces
one position at a time — SPEC.md section 11's risk rule — and compounds a
real equity curve, giving Sharpe/Sortino/max drawdown alongside profit
factor/win rate. These are the numbers a go/no-go decision should be based
on, not the screening tool's naive unsized sum.
"""

import numpy as np
import pandas as pd

from quant_bot.config import ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, MAKER_FEE_PCT

COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
MAKER_COST_PCT = MAKER_FEE_PCT * 2 + SLIPPAGE_PCT_EST  # both legs as limit orders


def simulate(close: pd.Series, proba: pd.Series, horizon_min: int, threshold: float,
             capital: float = 10_000.0, risk_pct: float = 0.01, cost_pct: float = COST_PCT,
             direction: str = "long") -> dict:
    """One position at a time, fixed-horizon exit (matches the label
    definition exactly, SPEC.md section 6 — no stop-loss concept exists in
    this design, so risk_pct is capital ALLOCATED per trade, not
    risk-to-a-stop; document this if you compare to confluence_ai_v3's
    ATR-based sizing, which meant something different).

    direction='short': proba should come from a model trained on the
    mirrored short label (quant_bot.features.build.build_labels with
    direction='short') — this function just flips the P&L sign, it doesn't
    change what proba means.

    Operates on plain numpy arrays internally — pandas .iloc scalar access
    in a tight Python loop was slow enough (minutes on ~200k+ rows) to be
    fragile against this environment's apparent background-task time
    limits; this is materially faster for the same logic."""
    sign = 1.0 if direction == "long" else -1.0
    close_arr = close.to_numpy()
    proba_arr = proba.to_numpy()
    index_arr = close.index
    n = len(close_arr)

    equity = capital
    equity_curve = [{"time": index_arr[0], "equity": equity}]
    trade_returns = []
    trade_entry_times = []

    i = 0
    while i < n - horizon_min:
        p = proba_arr[i]
        if not np.isnan(p) and p > threshold:
            entry_price = close_arr[i]
            exit_price = close_arr[i + horizon_min]
            net_return = sign * (exit_price / entry_price - 1.0) - cost_pct
            notional = equity * risk_pct
            pnl = notional * net_return
            equity += pnl
            trade_returns.append(net_return)
            trade_entry_times.append(index_arr[i])
            equity_curve.append({"time": index_arr[i + horizon_min], "equity": equity})
            i += horizon_min  # no overlap: next look-for-entry starts after this trade exits
        else:
            i += 1

    if not trade_returns:
        return {"n_trades": 0}

    returns = np.array(trade_returns)
    wins, losses = returns[returns > 0], returns[returns <= 0]
    gross_profit, gross_loss = wins.sum(), -losses.sum()

    eq_series = pd.Series([e["equity"] for e in equity_curve])
    running_max = eq_series.cummax()
    drawdown = (eq_series - running_max) / running_max
    max_dd_pct = float(drawdown.min() * 100)

    downside = returns[returns < 0]
    sharpe_like = returns.mean() / returns.std() if returns.std() > 0 else 0.0
    sortino_like = returns.mean() / downside.std() if len(downside) > 0 and downside.std() > 0 else 0.0

    return {
        "n_trades": len(returns),
        "win_rate_pct": round(len(wins) / len(returns) * 100, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else float("inf"),
        "total_return_pct": round((equity / capital - 1.0) * 100, 2),
        "final_equity": round(equity, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "sharpe_like": round(float(sharpe_like), 4),
        "sortino_like": round(float(sortino_like), 4),
        "expectancy_pct": round(float(returns.mean() * 100), 5),
        "equity_curve": equity_curve,
        "trade_returns": returns,
        "trade_entry_times": trade_entry_times,
    }


def simulate_combined(close: pd.Series, long_proba: pd.Series, short_proba: pd.Series,
                       horizon_min: int, long_threshold: float, short_threshold: float,
                       capital: float = 10_000.0, risk_pct: float = 0.01,
                       cost_pct: float = COST_PCT) -> dict:
    """One position at a time across BOTH directions for the same symbol —
    at each free bar, take whichever side clears its threshold (long
    preferred on a tie; ties are rare with independently-fit models).
    Tests whether combining the long and short signals (each shown
    individually near breakeven, docs/phase6_tier2_results.md) gets a
    single symbol to a reliable, adequately-sampled edge without needing
    new discovered signal."""
    close_arr = close.to_numpy()
    long_arr = long_proba.to_numpy()
    short_arr = short_proba.to_numpy()
    index_arr = close.index
    n = len(close_arr)

    equity = capital
    equity_curve = [{"time": index_arr[0], "equity": equity}]
    trade_returns = []
    trade_directions = []

    i = 0
    while i < n - horizon_min:
        lp, sp = long_arr[i], short_arr[i]
        take_long = not np.isnan(lp) and lp > long_threshold
        take_short = not np.isnan(sp) and sp > short_threshold
        if take_long or take_short:
            sign = 1.0 if (take_long and (not take_short or lp >= sp)) else -1.0
            entry_price = close_arr[i]
            exit_price = close_arr[i + horizon_min]
            net_return = sign * (exit_price / entry_price - 1.0) - cost_pct
            notional = equity * risk_pct
            pnl = notional * net_return
            equity += pnl
            trade_returns.append(net_return)
            trade_directions.append("LONG" if sign > 0 else "SHORT")
            equity_curve.append({"time": index_arr[i + horizon_min], "equity": equity})
            i += horizon_min
        else:
            i += 1

    if not trade_returns:
        return {"n_trades": 0}

    returns = np.array(trade_returns)
    wins, losses = returns[returns > 0], returns[returns <= 0]
    gross_profit, gross_loss = wins.sum(), -losses.sum()

    eq_series = pd.Series([e["equity"] for e in equity_curve])
    running_max = eq_series.cummax()
    drawdown = (eq_series - running_max) / running_max

    n_long = sum(1 for d in trade_directions if d == "LONG")
    return {
        "n_trades": len(returns),
        "n_long": n_long,
        "n_short": len(returns) - n_long,
        "win_rate_pct": round(len(wins) / len(returns) * 100, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else float("inf"),
        "total_return_pct": round((equity / capital - 1.0) * 100, 2),
        "final_equity": round(equity, 2),
        "max_drawdown_pct": round(float(drawdown.min() * 100), 2),
        "sharpe_like": round(float(returns.mean() / returns.std()), 4) if returns.std() > 0 else 0.0,
        "expectancy_pct": round(float(returns.mean() * 100), 5),
    }


def buy_and_hold(close: pd.Series, capital: float = 10_000.0) -> dict:
    ret = close.iloc[-1] / close.iloc[0] - 1.0
    eq_series = close / close.iloc[0] * capital
    running_max = eq_series.cummax()
    drawdown = (eq_series - running_max) / running_max
    return {
        "total_return_pct": round(ret * 100, 2),
        "final_equity": round(capital * (1 + ret), 2),
        "max_drawdown_pct": round(float(drawdown.min() * 100), 2),
    }
