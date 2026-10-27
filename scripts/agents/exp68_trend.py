"""Exp 68 (preregistered, docs/agents/hypotheses/Exp-68.md): multi-horizon Donchian trend, long/cash, BTC/ETH/SOL.

Library (pure functions, no I/O except `build_daily`). The runner is scripts/agents/exp68_run.py.

Rule, as written in the preregistration:
  * daily closes at 00:00 UTC (Binance 1m cache);
  * per asset and n in LB: state=1 if close > max(close of the n previous days);
    back to 0 if close < (max+min)/2 of the n last closes (today included); else state kept;
  * signal_i = mean of the 9 states;
  * w_i = signal_i * min(1, 0.25/sigma_i) / 3, sigma_i = std(daily returns, 60 d) * sqrt(365);
    sum of weights <= 1, rest in USDC;
  * decision at close J, held over J+1.

Corrections vs. the reference `run_spot` (docs/agents/research/H-R15_scripts/trend.py), see the commit log:
  1. weight: the reference computes clip(signal * 0.25/sigma, 0, 1)/3 = min(1, signal*0.25/sigma)/3,
     which is NOT the written signal * min(1, 0.25/sigma)/3 (they differ whenever sigma < 0.25 and
     0 < signal < 1; the reference is then larger). The written formula is used here.
  2. daily close: the reference resamples with closed='right', so the close of day J is the close of the
     1m bar *opening* at 00:00 (i.e. 00:00:59). The written rule says close at 00:00 UTC, i.e. the close of
     the bar opening at 23:59. closed='left', label='right' is used here (label D = close at D 00:00).
  3. turnover: the reference charges |w_J - w_{J-1}| and ignores weight drift, while its PnL
     (sum w * r every day) assumes a daily rebalance back to target. The cost here is charged on the
     real rebalance |w_J - w_drift_J| (conservative; the reference turnover is reported too).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LB = (5, 10, 20, 30, 60, 90, 150, 250, 360)
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
TV = 0.25
VOL_WIN = 60
ANN = 365  # sigma annualisation of the rule (sqrt(365))
ANN_STATS = 365.25  # reporting annualisation, as in the reference `stats`


# ---------------------------------------------------------------- data
def daily_from_minutes(bars: pd.DataFrame, end: str | None = None) -> pd.DataFrame:
    """Daily close/high/low labelled D = window [D-1 00:00, D 00:00) of 1m bars indexed by OPEN time.

    close[D] = close of the last 1m bar opening before D 00:00 (the 23:59 bar) = price at 00:00 UTC.
    The result is reindexed on a complete calendar; days without any bar get close forward-filled
    (return 0 that day) and `n_bars` = 0.
    """
    r = bars.resample("1D", label="right", closed="left")
    d = pd.DataFrame({"close": r["close"].last(), "high": r["high"].max(), "low": r["low"].min(),
                      "n_bars": r["close"].count()})
    d = d[d["n_bars"] > 0]
    full = pd.date_range(d.index.min(), d.index.max(), freq="1D", tz=d.index.tz)
    d = d.reindex(full)
    d["n_bars"] = d["n_bars"].fillna(0).astype(int)
    d["close"] = d["close"].ffill()
    d["high"] = d["high"].fillna(d["close"])
    d["low"] = d["low"].fillna(d["close"])
    if end is not None:
        d = d[d.index <= pd.Timestamp(end, tz=d.index.tz)]
    return d


# ---------------------------------------------------------------- signal
def states(c: pd.Series, n: int) -> pd.Series:
    """Long/flat Donchian state for one horizon, causal (uses closes up to t only)."""
    c = c.dropna()
    hi = c.rolling(n).max().shift(1)                       # max of the n PREVIOUS closes
    mid = (c.rolling(n).max() + c.rolling(n).min()) / 2    # n last closes, today included
    st = np.zeros(len(c))
    cur = 0
    cv, hv, mv = c.values, hi.values, mid.values
    for t in range(len(c)):
        if np.isnan(hv[t]):
            st[t] = 0
            continue
        if cur == 0:
            if cv[t] > hv[t]:
                cur = 1
        elif cv[t] < mv[t]:
            cur = 0
        st[t] = cur
    return pd.Series(st, index=c.index)


def signal(C: pd.DataFrame, lbs=LB) -> pd.DataFrame:
    out = {s: pd.concat([states(C[s], n) for n in lbs], axis=1).mean(axis=1) for s in C.columns}
    return pd.DataFrame(out).reindex(C.index)


def vol(C: pd.DataFrame) -> pd.DataFrame:
    return C.pct_change().rolling(VOL_WIN).std() * np.sqrt(ANN)


def target_weights(C: pd.DataFrame, tv: float = TV, reference: bool = False) -> pd.DataFrame:
    """Target weights decided at the close of each day (row J), to be held over J+1."""
    sig = signal(C)
    sv = vol(C)
    k = len(C.columns)
    if reference:  # exact formula of the reference run_spot (kept only to report the difference)
        w = (sig * (tv / sv)).clip(0, 1.0).div(k)
    else:          # written rule: signal * min(1, tv/sigma) / 3
        w = sig * np.minimum(1.0, tv / sv) / k
    w = w.fillna(0.0)
    tot = w.sum(axis=1)
    return w.div(tot.clip(lower=1.0), axis=0)


# ---------------------------------------------------------------- backtest
def backtest(C: pd.DataFrame, w: pd.DataFrame, cost_rt, cash_apy=None, drift_turnover: bool = True) -> pd.DataFrame:
    """Daily net returns. Row J: return from close J-1 to close J with weights decided at close J-1.

    cost_rt: scalar or dict sym -> round-trip cost (fraction). Cost per side = cost_rt/2, charged on the
             trade done at close J, booked in row J+1 (reference convention).
    cash_apy: None (0) or Series indexed like C, APY known at close J and applied to the cash held over J+1.
    """
    R = C.pct_change().fillna(0.0)
    wl = w.shift(1).fillna(0.0)
    contrib = wl * R
    gross = contrib.sum(axis=1)
    if cash_apy is None:
        cash_rate = pd.Series(0.0, index=C.index)
    else:
        cash_rate = ((1 + cash_apy.reindex(C.index)) ** (1 / 365) - 1).shift(1).fillna(0.0)
    cash = (1 - wl.sum(axis=1)) * cash_rate
    port = gross + cash
    if drift_turnover:
        pre = wl.mul(1 + R).div(1 + port, axis=0)        # weights just before the rebalance at close J
        trade = (w - pre).abs()
    else:
        trade = w.diff().abs().fillna(w.abs())
    if isinstance(cost_rt, dict):
        cvec = pd.Series(cost_rt).reindex(C.columns)
    else:
        cvec = pd.Series(float(cost_rt), index=C.columns)
    cost_asset = (trade * cvec / 2).shift(1).fillna(0.0)
    net = port - cost_asset.sum(axis=1)
    out = pd.DataFrame({"net": net, "gross": gross, "cash": cash, "cost": cost_asset.sum(axis=1),
                        "expo": wl.sum(axis=1), "turnover": trade.sum(axis=1).shift(1).fillna(0.0)})
    for s in C.columns:
        out[f"w_{s}"] = wl[s]
        out[f"contrib_{s}"] = contrib[s] - cost_asset[s]
        out[f"trade_{s}"] = trade[s].shift(1).fillna(0.0)
    return out


def basket(C: pd.DataFrame, start: str, end: str):
    """1/3 basket: daily rebalanced (reference) and buy-and-hold from `start` (no cost)."""
    R = C.pct_change().fillna(0.0)
    m = period_mask(R.index, start, end)
    reb = (R / len(C.columns)).sum(axis=1)[m]
    g = (1 + R[m]).cumprod()
    eq = g.mean(axis=1)
    bh = eq.pct_change()
    bh.iloc[0] = eq.iloc[0] - 1
    return reb, bh


# ---------------------------------------------------------------- stats
def period_mask(idx, start, end):
    tz = idx.tz
    return (idx >= pd.Timestamp(start, tz=tz)) & (idx <= pd.Timestamp(end, tz=tz))


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / ANN_STATS
    eq0 = pd.concat([pd.Series([1.0]), eq.reset_index(drop=True)])  # start at 1: first-day loss counts in DD
    sd = r.std()
    return dict(
        n_days=int(len(r)),
        cagr=float(eq.iloc[-1] ** (1 / yrs) - 1),
        vol=float(sd * np.sqrt(ANN_STATS)),
        sharpe=float(r.mean() / sd * np.sqrt(ANN_STATS)) if sd > 0 else float("nan"),
        maxdd=float((eq0 / eq0.cummax() - 1).min()),
        total=float(eq.iloc[-1] - 1),
        worst_day=float(r.min()),
        worst_day_date=str(r.idxmin().date()),
    )


def verdict(sh: float, maxdd: float, cagr: float, sh_basket: float) -> dict:
    c = {"sharpe_ge_0.5": sh >= 0.5, "maxdd_ge_-15pct": maxdd >= -0.15, "cagr_gt_0": cagr > 0,
         "sharpe_gt_basket": sh > sh_basket}
    rej = {"sharpe_le_0": sh <= 0, "maxdd_lt_-20pct": maxdd < -0.20}
    if all(c.values()):
        v = "PASS"
    elif any(rej.values()):
        v = "REJET"
    else:
        v = "INCERTAIN"
    return {"pass_conditions": c, "reject_conditions": rej, "verdict": v}
