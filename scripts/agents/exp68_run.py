"""Exp 68 runner. Usage:
  python scripts/agents/exp68_run.py <cache_dir> <kamino_csv> <out_prefix>
Reads the Binance 1m cache read-only (BTC/ETH/SOL), never loads beyond 2026-08-17 (end of P2).
Writes <out_prefix>_daily.csv and <out_prefix>_criteria.json.
Kamino series: GET https://api.kamino.finance/kamino-market/7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF/reserves/
  D6q6wuQSrifJKZYpR1M8R4YawnLDtDsMmWM1NbBmgJ59/metrics/history?env=mainnet-beta&start=2020-10-01T00:00:00Z
  &end=2026-08-19T00:00:00Z&frequency=day  (field supplyInterestAPY; available from 2023-10-12).
"""
import gc
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
spec = importlib.util.spec_from_file_location("exp68", HERE / "exp68_trend.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
from quant_bot.execution_harness.data import load_bars  # noqa: E402

P1 = ("2020-10-01", "2025-03-27")
P2 = ("2025-03-28", "2026-08-17")
END = P2[1]
COST = 0.0005
STRESS = {"BTCUSDT": 0.002, "ETHUSDT": 0.002, "SOLUSDT": 0.0005}

cache, kamino_csv, prefix = sys.argv[1], sys.argv[2], sys.argv[3]

# ------------------------------------------------------------ data (read-only)
daily, daily_ref, quality = {}, {}, {}
for s in m.SYMS:
    b = load_bars(s, cache)
    b = b[b.index < pd.Timestamp(END, tz="UTC")]  # last bar used: opens 2026-08-16 23:59 -> close at 08-17 00:00
    d = m.daily_from_minutes(b, end=END)
    # reference convention (closed='right'), only to reproduce the reference figure on P1
    r = b["close"].resample("1D", label="right", closed="right").last().dropna()
    daily_ref[s] = r[r.index <= pd.Timestamp(END, tz="UTC")]
    daily[s] = d
    for name, (a, z) in (("P1", P1), ("P2", P2)):
        dd = d[m.period_mask(d.index, a, z)]
        quality[f"{s}_{name}"] = dict(days=int(len(dd)), days_no_bar=int((dd.n_bars == 0).sum()),
                                      days_lt_1380_bars=int((dd.n_bars < 1380).sum()), min_bars=int(dd.n_bars.min()))
    quality[f"{s}_first_day"] = str(d.index.min().date())
    del b
    gc.collect()
C = pd.concat({s: daily[s]["close"] for s in m.SYMS}, axis=1)
Cref = pd.concat(daily_ref, axis=1)

kam = pd.read_csv(kamino_csv)
kam.index = pd.to_datetime(kam["timestamp"], utc=True).dt.normalize()
kam = kam["supplyInterestAPY"].astype(float)
kam = kam[~kam.index.duplicated()]
apy_k = kam.reindex(C.index)  # APY at D 00:00, applied to the cash held over D -> D+1
kam_cover = apy_k.notna()
apy_k_filled = apy_k.fillna(0.04)
apy_4 = pd.Series(0.04, index=C.index)

# ------------------------------------------------------------ rule
w = m.target_weights(C)
main = m.backtest(C, w, COST)
stress = m.backtest(C, w, STRESS)
cash_k = m.backtest(C, w, COST, cash_apy=apy_k_filled)
cash_4 = m.backtest(C, w, COST, cash_apy=apy_4)
nodrift = m.backtest(C, w, COST, drift_turnover=False)
w_refformula = m.target_weights(C, reference=True)
ref_formula = m.backtest(C, w_refformula, COST)
# full reference reproduction on P1 (reference weights, closed='right', no drift turnover, MaxDD without start)
w_ref = m.target_weights(Cref, reference=True)
ref_full = m.backtest(Cref, w_ref, COST, drift_turnover=False)
sig = m.signal(C)


def sl(x, p):
    return x[m.period_mask(x.index, *p)]


def ystats(r):
    return {int(y): round(float((1 + g).prod() - 1), 4) for y, g in r.groupby(r.index.year)}


def rnd(d, k=4):
    return {a: (round(b, k) if isinstance(b, float) else b) for a, b in d.items()}


res = {"data_quality": quality, "periods": {"P1": P1, "P2": P2},
       "conventions": {
           "fill": "close-to-close daily, decision at close J (00:00 UTC price = close of the 1m bar opening 23:59), held over J+1; "
                   "rebalanced daily to target; idealised fill at the 00:00 close, no slippage beyond the round-trip cost",
           "cost_rt_main": COST, "cost_rt_stress": STRESS, "turnover": "|w_J - drifted w_J| (incl. drift)",
           "cash_yield_decision": 0.0, "sharpe": "mean/std*sqrt(365.25), daily net returns, no risk-free",
           "maxdd": "equity starts at 1 at the beginning of the period",
           "category": "P1 en echantillon (deja vu) ; P2 hors echantillon pour la regle mais regime connu (Exp 56)"}}

for pname, p in (("P1", P1), ("P2", P2)):
    reb, bh = m.basket(C, *p)
    r = sl(main, p)
    days = len(r)
    yrs = days / m.ANN_STATS
    trades = r[[f"trade_{s}" for s in m.SYMS]]
    sig_p = sl(sig, p)
    block = {
        "strategy": rnd(m.stats(r["net"])),
        "basket_rebalanced_daily": rnd(m.stats(reb)),
        "basket_buy_and_hold": rnd(m.stats(bh)),
        "gross_no_cost": rnd(m.stats(r["gross"])),
        "stress_cost_btceth_0.20": rnd(m.stats(sl(stress, p)["net"])),
        "cash_kamino": rnd(m.stats(sl(cash_k, p)["net"])),
        "cash_kamino_coverage_days": int(sl(kam_cover, p).sum()),
        "cash_kamino_mean_apy_covered": round(float(sl(apy_k, p).mean()), 4) if sl(kam_cover, p).any() else None,
        "cash_4pct_const": rnd(m.stats(sl(cash_4, p)["net"])),
        "cost_no_drift_turnover": rnd(m.stats(sl(nodrift, p)["net"])),
        "reference_weight_formula": rnd(m.stats(sl(ref_formula, p)["net"])),
        "exposure_mean": round(float(r["expo"].mean()), 4),
        "exposure_max": round(float(r["expo"].max()), 4),
        "days_invested_frac": round(float((r["expo"] > 1e-9).mean()), 4),
        "turnover_per_year": round(float(r["turnover"].sum() / yrs), 3),
        "turnover_per_year_no_drift": round(float(sl(nodrift, p)["turnover"].sum() / yrs), 3),
        "cost_paid_per_year": round(float(r["cost"].sum() / yrs), 5),
        "swaps_nonzero": int((trades > 1e-12).sum().sum()),
        "swaps_ge_1pct_capital": int((trades >= 0.01).sum().sum()),
        "swaps_ge_1pct_per_year": round(float((trades >= 0.01).sum().sum() / yrs), 1),
        "state_signal_changes": {s: int((sig_p[s].diff().abs() > 1e-12).sum()) for s in m.SYMS},
        "per_year_strategy": ystats(r["net"]),
        "per_year_basket_rebalanced": ystats(reb),
        "per_asset": {s: {"contrib_total_sum": round(float(r[f"contrib_{s}"].sum()), 4),
                          "contrib_ann": round(float(r[f"contrib_{s}"].sum() / yrs), 4),
                          "mean_weight": round(float(r[f"w_{s}"].mean()), 4),
                          "asset_buy_and_hold_total": round(float(sl(C[s], (str((pd.Timestamp(p[0]) - pd.Timedelta('1D')).date()), p[1])).iloc[[0, -1]].pct_change().iloc[-1]), 4)}
                      for s in m.SYMS},
        "worst_5_days": {str(k.date()): round(float(v), 4) for k, v in r["net"].nsmallest(5).items()},
    }
    if pname == "P2":
        sh_b = max(block["basket_rebalanced_daily"]["sharpe"], block["basket_buy_and_hold"]["sharpe"])
        s = block["strategy"]
        block["criteria"] = m.verdict(s["sharpe"], s["maxdd"], s["cagr"], sh_b)
        block["criteria"]["basket_sharpe_used"] = sh_b
        block["criteria"]["basket_sharpe_used_note"] = "max(daily-rebalanced, buy-and-hold) : la plus defavorable a la strategie"
        for k in ("pass_conditions", "reject_conditions"):
            block["criteria"][k] = {a: bool(b) for a, b in block["criteria"][k].items()}
    res[pname] = block

# reference reproduction: P1 must be ~ CAGR 21.6 %, Sharpe 1.74, MaxDD -12.7 % (T-054 trend_out.txt); P2 reported sans effet
for pname, p in (("P1", P1), ("P2", P2)):
    rr = sl(ref_full, p)["net"]
    eq = (1 + rr).cumprod()
    res[f"reference_reproduction_{pname}"] = {**rnd(m.stats(rr)), "maxdd_reference_convention": round(float((eq / eq.cummax() - 1).min()), 4)}
sv = m.vol(C)
inv = w > 0
res["sigma_min_when_invested"] = {s: round(float(sv[s][inv[s]].min()), 4) for s in m.SYMS}
res["weights_text_vs_reference_max_abs_diff"] = round(float((w - w_refformula).abs().max().max()), 6)

# ------------------------------------------------------------ outputs
out = main.copy()
out["period"] = np.where(m.period_mask(out.index, *P1), "P1", np.where(m.period_mask(out.index, *P2), "P2", ""))
for s in m.SYMS:
    out[f"close_{s}"] = C[s]
    out[f"signal_{s}"] = sig[s]
    out[f"target_w_{s}"] = w[s]
out["net_stress"] = stress["net"]
out["net_cash_kamino"] = cash_k["net"]
out["kamino_apy"] = apy_k
reb_all = (C.pct_change().fillna(0) / 3).sum(axis=1)
out["basket_rebalanced"] = reb_all
out = out[out["period"] != ""]
out.index.name = "date"
out.round(8).to_csv(f"{prefix}_daily.csv")
Path(f"{prefix}_criteria.json").write_text(json.dumps(res, indent=1, default=str))
print(json.dumps({k: res[k] for k in ("P2",)}["P2"]["criteria"], indent=1))
print("P2 strat", res["P2"]["strategy"])
print("P2 basket reb", res["P2"]["basket_rebalanced_daily"], "\nP2 basket bh", res["P2"]["basket_buy_and_hold"])
print("P1 strat", res["P1"]["strategy"])
print("ref repro P1", res["reference_reproduction_P1"])
print("ref repro P2", res["reference_reproduction_P2"])
print("sigma min", res["sigma_min_when_invested"], "wdiff", res["weights_text_vs_reference_max_abs_diff"])
