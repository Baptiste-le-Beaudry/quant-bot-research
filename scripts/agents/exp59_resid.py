"""Exp 59 (A-JUP-RESID-001, H-R04) -- executed to the letter of docs/agents/hypotheses/Exp-59.md (commit 402efb4).

Population: Exp 57 candidates (SOL/BTC/ETH; P1 = pre-HOLDOUT ledger, P2 = Exp 50 entries), deployed rule
(entry next open, time exit 50 bars, NO stop), cost jupiter_build, net per trade at the 33 % / 500 CAD
notional (net_ret_at_size, as Exp 57 per-trade table). All `ok` candidates (not only account-taken ones),
as the Exp 57 per-trade criteria.

Variable (computed per signal, data strictly prior to the decision):
  r_15(x, t)  = close_x[t] / close_x[t - 15 min] - 1, t = signal bar (signal at its close); NaN if either
                bar is missing.
  market      = equally weighted mean of the two OTHER symbols: r_15(mkt) = mean of their r_15;
                1-min market return = mean of their 1-min returns (both required).
  beta        = cov / var of 1-min close returns (symbol vs market) over bars with open time in
                [t - 30 days, t) -- the signal bar itself is EXCLUDED ("strictement anterieures");
                a 1-min return is defined only between two consecutive minutes.
  R = r_15(sym) - beta * r_15(mkt) ; S = R / r_15(sym) (NaN if r_15(sym) == 0).
  Reported without effect: market = BTC only (SOL, ETH).

Points not fixed by the preregistration -- fixed HERE, before any computation:
  * Terciles: computed within each (population, symbol) on S ranks (method "first"), so the pooled
    tercile = union of the per-symbol terciles (no symbol-composition effect; SOL dominates counts).
  * Delta = mean net (top S tercile) - mean net (bottom S tercile), in points of %.
  * PASS (strict reading, PROPOSED verdict): pooled Delta >= 0.10 in P1 AND in P2, and per-symbol
    Delta > 0 for 3/3 symbols in P1 AND in P2.
    Lenient reading (reported): pooled Delta >= 0.10 in P1, pooled Delta > 0 in P2, per-symbol Delta > 0
    for 3/3 symbols in P1 and in P2.
    REJET otherwise. Inverse result (pooled Delta <= -0.10 in P1 and < 0 in P2): reported as "inverse".
  * S NaN (missing bars / r_15 == 0): trade dropped from the tercile table, count reported.

Harness v1.2.0 (run_trades / apply_costs, unchanged v1.1 behaviour). Bars read-only from --cache-dir.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.execution_harness import (VERSION, USD_PER_CAD, ExitRule, apply_costs, load_bars,  # noqa: E402
                                         profit_factor, run_trades)

SYMS = ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
POPS = {"P1": ROOT / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv",
        "P2": ROOT / "docs" / "experiment50_trades.csv"}
RULE = ExitRule(max_bars=50)
INITIAL_CAD, FRACTION, PLATFORM = 500.0, 0.33, "jupiter_build"
R_WIN, BETA_DAYS, DELTA_MIN = 15, 30, 0.10
OUT = ROOT / "docs" / "agents" / "results"


# ---------------------------------------------------------------- population (= Exp 57)
def candidates(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["entry_time"])
    d = d[d.symbol.isin(SYMS)]
    return pd.DataFrame({"symbol": d.symbol.values, "signal_time": pd.to_datetime(d.entry_time.values, utc=True),
                         "side": 1})


def population(cache_dir) -> dict:
    """{pop: (sim with net_ret_at_size, period)} -- run_trades as Exp 52/57, costs at the 33 % notional."""
    loader = lambda s: load_bars(s, cache_dir)  # noqa: E731
    notional = INITIAL_CAD * USD_PER_CAD.value * FRACTION
    out = {}
    for pop, path in POPS.items():
        sim = run_trades(candidates(path), RULE, PLATFORM, loader, entry_mode="next_open")
        ok_all = sim[sim.status == "ok"]
        period = (ok_all.signal_time.min(), ok_all.exit_time.max())
        out[pop] = (apply_costs(sim, PLATFORM, notional_usd=notional), sim, period)
    return out


# ---------------------------------------------------------------- causal variables (tested)
def minute_returns(close: pd.Series) -> pd.Series:
    """1-min close return, defined only when the previous bar is exactly one minute earlier."""
    r = close.pct_change()
    gap = close.index.to_series().diff() != pd.Timedelta(minutes=1)
    r[gap.to_numpy()] = np.nan
    return r


def r_window(close: pd.Series, times: pd.DatetimeIndex, minutes: int = R_WIN) -> np.ndarray:
    """close[t] / close[t - minutes] - 1 at the given bar times (NaN if a bar is missing)."""
    now = close.reindex(times).to_numpy(float)
    past = close.reindex(times - pd.Timedelta(minutes=minutes)).to_numpy(float)
    return now / past - 1.0


class RollingBeta:
    """beta of y on x over pairs with time in [t - days, t) via cumulative sums (both finite)."""

    def __init__(self, y: pd.Series, x: pd.Series, days: int = BETA_DAYS):
        d = pd.concat([y.rename("y"), x.rename("x")], axis=1, join="inner").dropna()
        self.idx = d.index
        yv, xv = d.y.to_numpy(float), d.x.to_numpy(float)
        z = lambda a: np.r_[0.0, np.cumsum(a)]  # noqa: E731
        self.cy, self.cx, self.cxy, self.cxx = z(yv), z(xv), z(xv * yv), z(xv * xv)
        self.win = pd.Timedelta(days=days)

    def at(self, times: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
        lo = self.idx.searchsorted(times - self.win, side="left")
        hi = self.idx.searchsorted(times, side="left")  # excludes the bar at t itself
        n = (hi - lo).astype(float)
        sx, sy = self.cx[hi] - self.cx[lo], self.cy[hi] - self.cy[lo]
        sxy, sxx = self.cxy[hi] - self.cxy[lo], self.cxx[hi] - self.cxx[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            cov = sxy - sx * sy / n
            var = sxx - sx * sx / n
            beta = np.where((n >= 2) & (var > 0), cov / var, np.nan)
        return beta, n


def residual_share(r_sym: np.ndarray, r_mkt: np.ndarray, beta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    R = r_sym - beta * r_mkt
    with np.errstate(invalid="ignore", divide="ignore"):
        S = np.where(r_sym != 0, R / r_sym, np.nan)
    return R, S


def tercile(s: pd.Series) -> pd.Series:
    """1 (low) / 2 / 3 (high) on ranks (method 'first'); NaN stays NaN."""
    out = pd.Series(np.nan, index=s.index)
    v = s.dropna()
    if len(v) >= 3:
        out[v.index] = pd.qcut(v.rank(method="first"), 3, labels=[1, 2, 3]).astype(float)
    return out


def compute_signal_vars(cache_dir, signals: pd.DataFrame) -> pd.DataFrame:
    """signals: symbol, signal_time (unique). Adds r15_sym, r15_mkt, beta, n_beta, R, S (+ BTC-only variant)."""
    close = {s: load_bars(s, cache_dir)["close"].astype(float) for s in SYMS}
    ret1 = {s: minute_returns(close[s]) for s in SYMS}
    rows = []
    for sym in SYMS:
        others = [o for o in SYMS if o != sym]
        g = signals[signals.symbol == sym].copy()
        t = pd.DatetimeIndex(g.signal_time)
        mkt1 = pd.concat([ret1[o] for o in others], axis=1, join="inner").mean(axis=1, skipna=False)
        rb = RollingBeta(ret1[sym], mkt1)
        beta, n = rb.at(t)
        r_s = r_window(close[sym], t)
        r_m = np.vstack([r_window(close[o], t) for o in others]).mean(axis=0)  # NaN if either is missing
        R, S = residual_share(r_s, r_m, beta)
        g["r15_sym"], g["r15_mkt"], g["beta"], g["n_beta"], g["R"], g["S"] = r_s, r_m, beta, n, R, S
        if sym != "BTCUSDT":  # variant: market = BTC only
            rbb = RollingBeta(ret1[sym], ret1["BTCUSDT"])
            bb, nb = rbb.at(t)
            r_b = r_window(close["BTCUSDT"], t)
            _, Sb = residual_share(r_s, r_b, bb)
            g["beta_btc"], g["S_btc"] = bb, Sb
        else:
            g["beta_btc"], g["S_btc"] = np.nan, np.nan
        rows.append(g)
        del rb
    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------- tables / criteria
def tercile_table(df: pd.DataFrame, s_col: str, net_col: str = "net_pct") -> pd.DataFrame:
    """df: population, symbol, s_col, net_col. Terciles per (population, symbol)."""
    d = df.copy()
    d["terc"] = d.groupby(["population", "symbol"])[s_col].transform(tercile)
    rows = []
    for pop, gp in d.groupby("population"):
        for sym in SYMS + ["POOLED"]:
            x = gp if sym == "POOLED" else gp[gp.symbol == sym]
            if x.empty:
                continue
            row = {"population": pop, "symbol": sym, "s_col": s_col, "n_all": len(x),
                   "n_nan_S": int(x.terc.isna().sum())}
            for k in (1, 2, 3):
                y = x[x.terc == k][net_col]
                row[f"n_T{k}"] = len(y)
                row[f"net_T{k}_pct"] = float(y.mean()) if len(y) else np.nan
                row[f"pf_T{k}"] = profit_factor(y / 100) if len(y) else np.nan
                row[f"S_max_T{k}"] = float(x[x.terc == k][s_col].max()) if len(y) else np.nan
            row["delta_T3_minus_T1"] = row["net_T3_pct"] - row["net_T1_pct"]
            y1, y3 = x[x.terc == 1][net_col], x[x.terc == 3][net_col]
            se = np.sqrt(y1.var(ddof=1) / len(y1) + y3.var(ddof=1) / len(y3)) if len(y1) > 1 and len(y3) > 1 else np.nan
            row["delta_se"] = float(se)
            rows.append(row)
    return pd.DataFrame(rows)


def verdict(tab: pd.DataFrame, delta_min: float = DELTA_MIN) -> dict:
    t = tab.set_index(["population", "symbol"])["delta_T3_minus_T1"]
    pooled = {p: float(t[(p, "POOLED")]) for p in ("P1", "P2")}
    sym_pos = {p: {s: bool(t[(p, s)] > 0) for s in SYMS} for p in ("P1", "P2")}
    syms_ok = all(all(v.values()) for v in sym_pos.values())
    strict = pooled["P1"] >= delta_min and pooled["P2"] >= delta_min and syms_ok
    lenient = pooled["P1"] >= delta_min and pooled["P2"] > 0 and syms_ok
    inverse = pooled["P1"] <= -delta_min and pooled["P2"] < 0
    return {"pooled_delta": pooled, "symbol_delta_positive": sym_pos,
            "verdict_strict": "PASS" if strict else "REJET", "verdict_lenient": "PASS" if lenient else "REJET",
            "inverse_result": bool(inverse)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--date", default="2026-10-07")
    args = ap.parse_args(argv)
    pops = population(args.cache_dir)
    trades = []
    for pop, (t, _, _) in pops.items():
        ok = t[t.status == "ok"].copy()
        ok["population"] = pop
        ok["net_pct"] = 100 * ok.net_ret_at_size
        trades.append(ok[["population", "symbol", "signal_time", "entry_time", "net_pct", "gross_ret"]])
    trades = pd.concat(trades, ignore_index=True)
    # repro check vs Exp 57 per-trade (principal cost)
    e57 = pd.read_csv(OUT / "Exp-57_2026-10-07_per_trade.csv")
    e57 = e57[e57.cost == "principal_build"].set_index(["population", "symbol"])
    repro = {f"{p}_{s}": [int(len(g)), float(g.net_pct.mean()), int(e57.loc[(p, s), "n"]),
                          float(e57.loc[(p, s), "mean_net_pct_at_size"])]
             for (p, s), g in trades.groupby(["population", "symbol"])}
    sig = trades[["symbol", "signal_time"]].drop_duplicates()
    v = compute_signal_vars(args.cache_dir, sig)
    trades = trades.merge(v, on=["symbol", "signal_time"], how="left")
    tab = tercile_table(trades, "S")
    tab_btc = tercile_table(trades[trades.symbol != "BTCUSDT"], "S_btc")
    res = verdict(tab)
    diag = trades.groupby(["population", "symbol"]).agg(
        n=("S", "size"), share_r15_pos=("r15_sym", lambda x: float((x > 0).mean())),
        median_r15_pct=("r15_sym", lambda x: 100 * float(x.median())), median_beta=("beta", "median"),
        min_n_beta=("n_beta", "min"), median_S=("S", "median"), n_S_nan=("S", lambda x: int(x.isna().sum())),
        corr_S_net=("S", lambda x: np.nan)).reset_index()
    for i, r in diag.iterrows():
        m = (trades.population == r.population) & (trades.symbol == r.symbol)
        diag.loc[i, "corr_S_net"] = float(trades.loc[m, ["S", "net_pct"]].corr(method="spearman").iloc[0, 1])
    out = {"harness_version": VERSION, "platform": PLATFORM, "notional_usd": INITIAL_CAD * USD_PER_CAD.value * FRACTION,
           "periods": {p: [str(a), str(b)] for p, (_, _, (a, b)) in pops.items()},
           "repro_vs_exp57 [n, net, n57, net57]": repro, "criteria": res}
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([tab, tab_btc]).to_csv(OUT / f"Exp-59_{args.date}_terciles.csv", index=False)
    diag.to_csv(OUT / f"Exp-59_{args.date}_diag.csv", index=False)
    trades.to_csv(OUT / f"Exp-59_{args.date}_per_trade.csv", index=False)
    (OUT / f"Exp-59_{args.date}_criteria.json").write_text(json.dumps(out, indent=2, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(tab.round(4).to_string())
    print(tab_btc.round(4).to_string())
    print(diag.round(4).to_string())
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
