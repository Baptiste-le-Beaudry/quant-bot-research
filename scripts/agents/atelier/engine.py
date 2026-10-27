"""T-073 atelier -- common backtest engine (no data access here: callers pass series obtained via loader.py).

Conventions (fixed before any discovery run, D-09 sec. 7, conservative reading):
  * Signals/weights decided at the close of day t, traded at the close of t+1, first return on t+2
    (lag=2, the Exp 74 convention).  For monthly series lag=1 (decided at month end, held next month).
  * Portfolio return  r = rf + sum_i w_i (r_i - rf) - max(gross-1, 0) * SPREAD  - COST * sum_i |dw_i|
    - COST * monthly drift turnover.
    SPREAD = 1.8 %/yr over the T-bill on every unit of gross exposure above 1.  This is the cost
    measured for a 2x ETF in Exp 74 / T-069 (0.95 % fee + 0.84 pt gap of the synthetic vs SSO),
    which is higher than "T-bill + 1 %": the more conservative of the two D-09 figures.
  * COST = 0.10 % of the traded notional (each |dw|), plus the same rate on the turnover needed at
    each month end to bring drifted weights back to target (charged to the rule only).
  * Reference (D-09 sec. 5): S&P 500 TR x L constant, same SPREAD on L-1, no trading cost, with L
    solved so that its volatility equals the rule's on the same period.
  * Sharpe = mean(r - rf) / sd(r - rf) * sqrt(ppy).  CAGR on calendar time (daily) or months/12.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SPREAD = 0.018
COST = 0.001
TARGET_VOL = 0.20


# ------------------------------------------------------------------------------------------- bonds
def par_bond_price(y: np.ndarray, coupon: np.ndarray, maturity: float, freq: int = 2) -> np.ndarray:
    """Price (per 1 of face) of a bullet bond with annual `coupon` (decimal) at yield `y` (decimal)."""
    n = maturity * freq
    yy = np.where(np.abs(y) < 1e-9, 1e-9, y) / freq
    annuity = (1 - (1 + yy) ** (-n)) / yy
    return coupon / freq * annuity + (1 + yy) ** (-n)


def bond_tr_from_yield(y_pct: pd.Series, maturity: float = 10.0, freq: int = 2,
                       monthly: bool = False) -> pd.Series:
    """Total return of a constant-maturity par bond rebought every period (Swinkels-type proxy).
    r_t = carry + P(y_t; coupon = y_{t-1}, maturity) - 1, carry = y_{t-1} * elapsed time.
    Ageing of the bond within the period is ignored (tiny)."""
    y = y_pct.astype(float).dropna() / 100.0
    y0 = y.shift(1)
    if monthly:
        dt = pd.Series(1.0 / 12.0, index=y.index)
    else:
        dt = pd.Series(y.index, index=y.index).diff().dt.days / 365.25
    price = par_bond_price(y.values, y0.values, maturity, freq)
    r = y0 * dt + (price - 1.0)
    return r.iloc[1:].rename(f"bond{maturity:g}")


# ------------------------------------------------------------------------------------------- sim
def simulate(target_w: pd.DataFrame, rets: pd.DataFrame, rf: pd.Series, lag: int = 2,
             cost: float = COST, spread: float = SPREAD, ppy: int = 252, drift_cost: bool = True) -> pd.DataFrame:
    """target_w: weights decided at each index date (NaN = keep previous).  rets: total returns of the
    same assets.  Returns DataFrame [ret, gross, turnover, orders]."""
    idx = rets.index
    w = target_w.reindex(columns=rets.columns).reindex(idx).ffill().shift(lag).fillna(0.0)
    ex = rets.sub(rf, axis=0)
    gross = w.abs().sum(axis=1)
    r = rf + (w * ex.fillna(0.0)).sum(axis=1) - (gross - 1).clip(lower=0) * spread / ppy
    dw = w.diff().abs()
    dw.iloc[0] = w.iloc[0].abs()
    turnover = dw.sum(axis=1)
    orders = (dw > 1e-9).sum(axis=1).astype(float)
    r = r - cost * turnover
    if drift_cost:
        key = idx.to_period("M") if isinstance(idx, pd.DatetimeIndex) else idx
        grp = (1 + rets.fillna(0.0)).groupby(key).prod() - 1
        rfm = (1 + rf).groupby(key).prod() - 1
        wm = w.groupby(key).last()
        rp = (wm * grp).sum(axis=1) + (1 - wm.sum(axis=1)) * rfm
        drifted = wm.mul(1 + grp).div(1 + rp, axis=0)
        dabs = (drifted - wm).abs()
        dturn = dabs.sum(axis=1)
        last_day = pd.Series(idx, index=idx).groupby(key).last()
        charge = pd.Series(0.0, index=idx)
        charge.loc[last_day.values] = cost * dturn.values
        r = r - charge
        # month-end drift rebalancing orders: assets whose weight drifted by more than 0.5 pt
        drift_orders = pd.Series(0.0, index=idx)
        drift_orders.loc[last_day.values] = (dabs > 0.005).sum(axis=1).values
        orders = orders + drift_orders
    return pd.DataFrame({"ret": r, "gross": gross, "turnover": turnover, "orders": orders})


def ref_returns(L: float, r_mkt: pd.Series, rf: pd.Series, spread: float = SPREAD, ppy: int = 252) -> pd.Series:
    return rf + L * (r_mkt - rf) - max(L - 1.0, 0.0) * spread / ppy


def ann_vol(r: pd.Series, ppy: int = 252) -> float:
    return float(r.std(ddof=1) * np.sqrt(ppy))


def solve_L(target_vol: float, r_mkt: pd.Series, rf: pd.Series, spread: float = SPREAD, ppy: int = 252) -> float:
    lo, hi = 0.0, 20.0
    for _ in range(80):
        mid = (lo + hi) / 2
        v = ann_vol(ref_returns(mid, r_mkt, rf, spread, ppy), ppy)
        lo, hi = (mid, hi) if v < target_vol else (lo, mid)
    return (lo + hi) / 2


def sharpe(r: pd.Series, rf: pd.Series, ppy: int = 252) -> float:
    ex = (r - rf).dropna()
    return float(ex.mean() / ex.std(ddof=1) * np.sqrt(ppy))


def cagr(r: pd.Series, ppy: int = 252) -> float:
    g = float((1 + r).prod())
    if isinstance(r.index, pd.DatetimeIndex):
        yrs = (r.index[-1] - r.index[0]).days / 365.25 + 1.0 / ppy
    else:
        yrs = len(r) / ppy
    return g ** (1 / yrs) - 1


def max_dd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax().clip(lower=1.0) - 1).min())


def stats(r: pd.Series, rf: pd.Series, ppy: int = 252) -> dict:
    return {"cagr": cagr(r, ppy), "vol": ann_vol(r, ppy), "sharpe": sharpe(r, rf, ppy), "maxdd": max_dd(r)}


def evaluate(r: pd.Series, rf: pd.Series, r_mkt: pd.Series, ppy: int = 252, spread: float = SPREAD) -> dict:
    """Rule vs constant-leverage reference at equal volatility, same sample."""
    df = pd.concat([r.rename("r"), rf.rename("rf"), r_mkt.rename("m")], axis=1).dropna()
    s = stats(df["r"], df["rf"], ppy)
    L = solve_L(s["vol"], df["m"], df["rf"], spread, ppy)
    ref = ref_returns(L, df["m"], df["rf"], spread, ppy)
    sr = stats(ref, df["rf"], ppy)
    return {**s, "L_ref": L, "ref_cagr": sr["cagr"], "ref_sharpe": sr["sharpe"], "ref_maxdd": sr["maxdd"],
            "dsharpe": s["sharpe"] - sr["sharpe"], "n": len(df)}


def scale_to_vol(target_w: pd.DataFrame, rets: pd.DataFrame, rf: pd.Series, target: float = TARGET_VOL,
                 window: tuple | None = None, **kw) -> tuple[float, pd.DataFrame]:
    """Constant multiplier k so that the rule's realised vol on `window` equals `target` (k is then a
    frozen parameter).  Iterated because costs/spread are not linear in k."""
    k = 1.0
    for _ in range(4):
        sim = simulate(target_w * k, rets, rf, **kw)
        x = sim["ret"] if window is None else sim["ret"].loc[window[0]:window[1]]
        v = ann_vol(x, kw.get("ppy", 252))
        if v <= 0:
            break
        k *= target / v
    return k, simulate(target_w * k, rets, rf, **kw)
