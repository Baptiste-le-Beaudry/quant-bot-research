"""Exp 60 (A-JUP-REGIME-001, H-R09) -- executed to the letter of docs/agents/hypotheses/Exp-60.md (commit 402efb4).

Population: identical to Exp 59 / Exp 57 (SOL/BTC/ETH, P1 and P2, deployed rule, cost jupiter_build,
net per trade at the 33 % / 500 CAD notional). Account: SOL+BTC+ETH, 500 CAD, 33 % of realized equity,
one position per symbol, exposure <= 100 %, period = Exp 57 common period (harness v1.2 sizer hook).

Variable (one): R = 1 if the symbol's previous UTC daily close is above the simple mean of 20 daily closes,
else 0. Definitions fixed HERE, before any computation:
  * daily close of day D = close of the last 1-min bar with open time in day D (UTC); days without bars
    are skipped (the SMA uses the last 20 available daily closes).
  * SMA20 of day D = mean of the daily closes of D-19..D (the 20 closes up to and including D, standard
    close > SMA20(close)); above_D = close_D > SMA20_D (NaN if < 20 closes).
  * A signal at time t on day T uses above_D of the last available day D < T (normally T-1): the SMA20
    is "shifted by one day", only closes known before 00:00 of T are used.
  * Delta = net/trade(R=1) - net/trade(R=0), pooled SOL+BTC+ETH, points of %.
  * P1 chronological halves: split at the median entry time of the pooled P1 trades (Exp 48 convention).
  * Half size: notional = 33 % x realized equity if R=1, 16.5 % if R=0 (sizer); R NaN -> full size
    (deployed behaviour), count reported.
  * MaxDD reduction = MaxDD(half) - MaxDD(full) in points (MaxDD negative); CAGR drop relative =
    (CAGR_full - CAGR_half) / |CAGR_full|.
Criteria (preregistered, applied mechanically):
  PASS    : Delta_P1 >= 0.10, Delta(H1) and Delta(H2) both > 0, Delta_P2 > 0, and in P1 AND P2 the
            half-size account improves MaxDD by >= 5 points with a relative CAGR drop <= 20 %.
  REJET   : Delta_P1 < 0.05, or Delta(H1), Delta(H2) of different signs, or sign(Delta_P2) != sign(Delta_P1).
  INCERTAIN otherwise. Inverse (Delta_P1 <= -0.10): reported, not exploited.
Reported without effect: per-symbol Delta, full exclusion of R=0 (account).
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
from quant_bot.execution_harness import VERSION, USD_PER_CAD, load_bars, profit_factor, simulate_account  # noqa: E402
from scripts.agents.exp59_resid import FRACTION, INITIAL_CAD, OUT, PLATFORM, SYMS, population  # noqa: E402

SMA_DAYS, DELTA_PASS, DELTA_REJECT, DD_POINTS, CAGR_DROP = 20, 0.10, 0.05, 5.0, 0.20


# ---------------------------------------------------------------- causal regime (tested)
def daily_above_sma(close: pd.Series, days: int = SMA_DAYS) -> pd.Series:
    """above_D (1.0 / 0.0 / NaN) indexed by UTC day D, from closes up to the end of D only."""
    daily = close.resample("1D").last().dropna()
    sma = daily.rolling(days, min_periods=days).mean()
    above = (daily > sma).astype(float)
    above[sma.isna()] = np.nan
    return above


def regime_at(above: pd.Series, times: pd.DatetimeIndex) -> np.ndarray:
    """R for signals at `times`: above_D of the last available day D strictly before the signal's day."""
    day = times.floor("D")
    pos = above.index.searchsorted(day, side="left") - 1
    out = np.full(len(times), np.nan)
    ok = pos >= 0
    out[ok] = above.to_numpy()[pos[ok]]
    return out


def make_regime_sizer(regime: dict, scale_r0: float = 0.5):
    """sizer(t, equity, open_pos, base): base if R=1 (or NaN), scale_r0*base if R=0 (0 -> skip)."""
    def sizer(t, equity, open_pos, base_notional):
        r = regime.get((t.symbol, pd.Timestamp(t.signal_time)), np.nan)
        if r == 0:
            return scale_r0 * base_notional, ("r0_scaled" if scale_r0 > 0 else "r0_excluded")
        return base_notional, ("r1_full" if r == 1 else "r_nan_full")
    return sizer


# ---------------------------------------------------------------- tables / criteria
def delta_table(tr: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (pop, part), g0 in tr.groupby(["population", "part"]):
        for sym in SYMS + ["POOLED"]:
            g = g0 if sym == "POOLED" else g0[g0.symbol == sym]
            r1, r0 = g[g.R == 1].net_pct, g[g.R == 0].net_pct
            rows.append({"population": pop, "part": part, "symbol": sym, "n": len(g), "n_R1": len(r1), "n_R0": len(r0),
                         "n_R_nan": int(g.R.isna().sum()), "share_R0": len(r0) / max(len(r1) + len(r0), 1),
                         "net_R1_pct": r1.mean(), "net_R0_pct": r0.mean(),
                         "pf_R1": profit_factor(r1 / 100), "pf_R0": profit_factor(r0 / 100),
                         "delta_R1_minus_R0": r1.mean() - r0.mean(),
                         "delta_se": float(np.sqrt(r1.var(ddof=1) / len(r1) + r0.var(ddof=1) / len(r0)))
                         if len(r1) > 1 and len(r0) > 1 else np.nan})
    return pd.DataFrame(rows)


def criteria(tab: pd.DataFrame, acc: pd.DataFrame) -> dict:
    d = tab[tab.symbol == "POOLED"].set_index(["population", "part"])["delta_R1_minus_R0"]
    dp1, dh1, dh2, dp2 = (float(d[("P1", "all")]), float(d[("P1", "H1")]), float(d[("P1", "H2")]),
                          float(d[("P2", "all")]))
    a = acc.set_index(["population", "variant"])
    acct = {}
    for pop in ("P1", "P2"):
        full, half = a.loc[(pop, "FULL")], a.loc[(pop, "HALF_R0")]
        dd_gain = float(half.max_dd_pct - full.max_dd_pct)
        drop = float((full.cagr_cad_pct - half.cagr_cad_pct) / abs(full.cagr_cad_pct)) if full.cagr_cad_pct != 0 else np.inf
        acct[pop] = {"maxdd_full": float(full.max_dd_pct), "maxdd_half": float(half.max_dd_pct),
                     "maxdd_gain_points": dd_gain, "cagr_full": float(full.cagr_cad_pct),
                     "cagr_half": float(half.cagr_cad_pct), "cagr_drop_rel": drop,
                     "ok": bool(dd_gain >= DD_POINTS and drop <= CAGR_DROP)}
    pass_ = (dp1 >= DELTA_PASS and dh1 > 0 and dh2 > 0 and dp2 > 0 and all(v["ok"] for v in acct.values()))
    reject = dp1 < DELTA_REJECT or np.sign(dh1) != np.sign(dh2) or np.sign(dp2) != np.sign(dp1)
    return {"delta_P1": dp1, "delta_P1_H1": dh1, "delta_P1_H2": dh2, "delta_P2": dp2, "account": acct,
            "reject_delta_lt_0.05": bool(dp1 < DELTA_REJECT), "reject_halves_sign": bool(np.sign(dh1) != np.sign(dh2)),
            "reject_p2_sign": bool(np.sign(dp2) != np.sign(dp1)),
            "mechanical": "PASS" if pass_ else ("REJET" if reject else "INCERTAIN"),
            "inverse_result": bool(dp1 <= -DELTA_PASS)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--date", default="2026-10-07")
    args = ap.parse_args(argv)
    pops = population(args.cache_dir)
    above = {s: daily_above_sma(load_bars(s, args.cache_dir)["close"].astype(float)) for s in SYMS}
    trades, regime = [], {}
    for pop, (t, _, _) in pops.items():
        ok = t[t.status == "ok"].copy()
        ok["population"] = pop
        ok["net_pct"] = 100 * ok.net_ret_at_size
        ok["R"] = np.nan
        for s in SYMS:
            m = ok.symbol == s
            ok.loc[m, "R"] = regime_at(above[s], pd.DatetimeIndex(ok.loc[m, "signal_time"]))
        trades.append(ok)
        for r in ok.itertuples():
            regime[(r.symbol, pd.Timestamp(r.signal_time))] = r.R
    tr = pd.concat(trades, ignore_index=True)
    half = tr.loc[tr.population == "P1", "entry_time"].quantile(0.5)
    parts = [tr.assign(part="all"),
             tr[tr.population == "P1"].assign(part=np.where(tr.loc[tr.population == "P1", "entry_time"] < half, "H1", "H2"))]
    tab = delta_table(pd.concat(parts, ignore_index=True))
    rows = []
    for pop, (t, _, period) in pops.items():
        tt = t.copy()
        for variant, sizer in (("FULL", None), ("HALF_R0", make_regime_sizer(regime, 0.5)),
                               ("EXCL_R0", make_regime_sizer(regime, 0.0))):
            a = simulate_account(tt, PLATFORM, INITIAL_CAD, USD_PER_CAD.value, position_fraction=FRACTION,
                                 max_gross_exposure=1.0, one_position_per_symbol=True, period=period, sizer=sizer)
            led = a["ledger"]
            rows.append({"population": pop, "variant": variant, "period_start": str(period[0]),
                         "period_end": str(period[1]),
                         **{k: v for k, v in a.items() if k not in ("ledger", "equity_minute", "skips")},
                         **{f"skip_{k}": v for k, v in a["skips"].items()},
                         **{f"taken_{k}": v for k, v in led.size_tag.value_counts().to_dict().items()}})
    acc = pd.DataFrame(rows)
    crit = criteria(tab, acc)
    e57 = pd.read_csv(OUT / "Exp-57_2026-10-07_accounts.csv")
    e57 = e57[(e57.cost == "principal_build") & (e57.account == "SOL_BTC_ETH")].set_index("population")
    repro = {p: [int(r.n_trades), float(r.cagr_cad_pct), float(r.max_dd_pct), int(e57.loc[p, "n_trades"]),
                 float(e57.loc[p, "cagr_cad_pct"]), float(e57.loc[p, "max_dd_pct"])]
             for p, r in acc[acc.variant == "FULL"].set_index("population").iterrows()}
    out = {"harness_version": VERSION, "platform": PLATFORM, "p1_half_split": str(half),
           "share_days_above_sma": {s: float(above[s].mean()) for s in SYMS},
           "full_reproduces_exp57 [n, cagr, maxdd, n57, cagr57, maxdd57]": repro, "criteria": crit}
    OUT.mkdir(parents=True, exist_ok=True)
    tab.to_csv(OUT / f"Exp-60_{args.date}_delta.csv", index=False)
    acc.to_csv(OUT / f"Exp-60_{args.date}_accounts.csv", index=False)
    tr[["population", "symbol", "signal_time", "entry_time", "net_pct", "R"]].to_csv(
        OUT / f"Exp-60_{args.date}_per_trade.csv", index=False)
    (OUT / f"Exp-60_{args.date}_criteria.json").write_text(json.dumps(out, indent=2, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)
    print(tab.round(4).to_string())
    print(acc[["population", "variant", "n_trades", "total_return_cad_pct", "cagr_cad_pct", "max_dd_pct",
               "worst_day_pct", "worst_day_date", "worst_intraday_pct", "worst_week_pct", "pf_usd",
               "mean_ret_on_notional_pct"]].round(3).to_string())
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
