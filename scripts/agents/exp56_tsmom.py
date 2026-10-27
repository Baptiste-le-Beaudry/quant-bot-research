"""Exp 56 (preregistered 0b3aade): daily time-series momentum long/cash on BTC/ETH/SOL."""
import json, sys
import numpy as np, pandas as pd
CACHE = "docs/_full_data_cache"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

def daily_close(sym):
    df = pd.read_pickle(f"{CACHE}/{sym}_full.pkl")
    if not isinstance(df.index, pd.DatetimeIndex):
        tcol = [c for c in df.columns if "time" in c.lower()][0]
        df = df.set_index(pd.to_datetime(df[tcol], utc=True))
    if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    # close of the 1m bar ending at 00:00 UTC == last close of the previous UTC day
    return df["close"].resample("1D", label="right", closed="right").last().dropna()

closes = pd.concat({s: daily_close(s) for s in SYMS}, axis=1)
rets = closes.pct_change()

def run(lookback, cost_rt, start, end, cost_btceth=None):
    sig = (closes.shift(1) / closes.shift(1 + lookback) - 1 > 0).astype(float)  # known at 00:00 of day J
    w = sig / 3.0
    turn = w.diff().abs()
    costs = pd.DataFrame({s: turn[s] * ((cost_btceth if (cost_btceth and s != "SOLUSDT") else cost_rt) / 2) for s in SYMS})
    strat = (w.shift(0) * rets).sum(axis=1) - costs.sum(axis=1)
    # holding decided at 00:00 day J earns return from close(J-1)->close(J)? rets indexed at J = close(J)/close(J-1)-1
    # signal uses close(J-1)/close(J-8): decided at 00:00 day J (close of day J-1 known) and earns day J return.
    bh = (rets / 3.0).sum(axis=1)
    m = (strat.index >= start) & (strat.index <= end)
    return strat[m].dropna(), bh[m].dropna()

def stats(r):
    eq = (1 + r).cumprod(); yrs = len(r) / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    sh = r.mean() / r.std() * np.sqrt(365.25) if r.std() > 0 else np.nan
    return dict(cagr=round(cagr * 100, 2), maxdd=round(dd * 100, 2), sharpe=round(sh, 3), total=round((eq.iloc[-1] - 1) * 100, 1), n_days=len(r))

out = {}
for lb in (7, 14, 28):
    for label, ck in (("cost005", None), ("stress_btceth020", 0.002)):
        s, b = run(lb, 0.0005, "2020-10-01", "2025-03-27", ck)
        mid = s.index[len(s) // 2]
        h1, h2 = s[s.index < mid], s[s.index >= mid]
        bull_s, bull_b = s["2023-01-01":], b["2023-01-01":]
        late_s, late_b = run(lb, 0.0005, "2025-04-01", "2026-08-17", ck)
        out[f"lb{lb}_{label}"] = dict(
            strat=stats(s), basket=stats(b),
            half1_total=round(((1 + h1).prod() - 1) * 100, 1), half2_total=round(((1 + h2).prod() - 1) * 100, 1),
            bull_strat_total=round(((1 + bull_s).prod() - 1) * 100, 1), bull_basket_total=round(((1 + bull_b).prod() - 1) * 100, 1),
            late_strat=stats(late_s) if len(late_s) > 30 else None, late_basket=stats(late_b) if len(late_b) > 30 else None)
print("data:", closes.index.min(), closes.index.max(), closes.notna().sum().to_dict())
print(json.dumps(out, indent=1))
