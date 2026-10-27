"""Exp 74 (preregistered, docs/agents/hypotheses/Exp-74.md, commit 24011d4): S&P 500 x2 with a 200-day trend filter.

Rule (fixed, no tuning):
  * signal s_t = 1 if close_t(^GSPC) > SMA200_t (simple mean of the 200 closes ending at t, t included), else 0;
  * the position decided at close t takes effect at close t+1, so it earns the return of day t+2:
        pos_d = s_{d-2}            (paper version, reported without effect: pos_d = s_{d-1});
  * invested day:  r = k * r_TR - (k-1) * rf - FEE/252       (k = 2 decisional, k = 3 reported);
    cash day:      r = rf,     rf = ^IRX/100/252 (value of the day, forward-filled);
  * each switch (pos_d != pos_{d-1}) costs SWITCH_COST of capital, charged on the first day of the new position.

Modes:
  py -3 scripts/agents/exp74_leveraged_trend.py download   -> caches raw series in DATA_DIR (outside git)
  py -3 scripts/agents/exp74_leveraged_trend.py run        -> computes everything, writes JSON + CSV

Conservative choices (spec silent):
  * leveraged-proxy check: if synthetic x2 (always invested) beats SSO by more than 1.5 pt/yr CAGR on 2007+, an
    extra annual drag is added so that the CAGRs match (applied to every x2 figure used by the verdict). If the
    synthetic is BELOW SSO, no upward correction is applied (it is only reported). Same logic for x3 vs UPRO,
    reported only.
  * other indices without a full-period total-return series: price-only on BOTH sides (x2 rule and x1 hold);
    this omits 2x the dividend on invested days for the rule vs 1x for the hold (unfavourable to the rule).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

DATA_DIR = Path("C:/AAProjet/quant_bot_v1/data/exp74_yahoo")
REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "docs" / "agents" / "results"

SMA_N = 200
FEE = 0.0095          # per year, synthetic leveraged fund fees
SWITCH_COST = 0.0010  # fraction of capital per switch
TD = 252              # trading days per year (rf and fee de-annualisation, Sharpe annualisation)
N_TRIALS = 74         # global experiment counter for the Deflated Sharpe
START = "1990-01-01"
PRE = ("1990-01-01", "2016-02-29")
POST_START = "2016-03-01"
PROXY_TOL = 0.015

YAHOO = ["^GSPC", "^SP500TR", "^IRX", "SSO", "UPRO", "^NDX", "^RUT", "^RUTTR", "^GDAXI", "CAD=X"]


# ---------------------------------------------------------------- core (pure)
def sma_signal(close: pd.Series, n: int = SMA_N) -> pd.Series:
    """s_t = 1 if close_t > SMA_n(t) (trailing, t included), 0 otherwise; 0 while fewer than n closes exist."""
    sma = close.rolling(n, min_periods=n).mean()
    s = (close > sma).astype(int)
    s[sma.isna()] = 0
    return s


def positions(signal: pd.Series, lag: int = 2) -> pd.Series:
    """Position earning the return of day d. lag=2: decided at close d-2, executed at close d-1 (rule).
    lag=1: executed at the signal close (paper)."""
    return signal.shift(lag).fillna(0).astype(int)


def strategy_returns(pos: pd.Series, r_tr: pd.Series, rf: pd.Series, k: float = 2.0,
                     fee: float = FEE, switch_cost: float = SWITCH_COST, extra_drag: float = 0.0) -> pd.Series:
    """Daily returns of the filtered k-x strategy. extra_drag: additional annual drag (proxy correction)."""
    lev = k * r_tr - (k - 1.0) * rf - (fee + extra_drag) / TD
    r = pd.Series(np.where(pos == 1, lev, rf), index=pos.index)
    sw = pos.diff().abs().fillna(0) > 0
    r = (1 + r) * (1 - switch_cost * sw.astype(float)) - 1
    return r


def leveraged_hold(r_tr: pd.Series, rf: pd.Series, k: float = 2.0, fee: float = FEE, extra_drag: float = 0.0) -> pd.Series:
    return k * r_tr - (k - 1.0) * rf - (fee + extra_drag) / TD


def cagr(r: pd.Series) -> float:
    """CAGR on calendar time; the equity starts at the close preceding the first return (approx. 1 trading day)."""
    r = r.dropna()
    if len(r) == 0:
        return float("nan")
    eq = float(np.prod(1 + r.values))
    days = (r.index[-1] - r.index[0]).days + 365.25 / TD
    return eq ** (365.25 / days) - 1


def max_dd(r: pd.Series) -> float:
    eq = np.cumprod(1 + r.dropna().values)
    eq = np.concatenate([[1.0], eq])
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1).min())


def sharpe(r: pd.Series, rf: pd.Series) -> float:
    ex = (r - rf.reindex(r.index)).dropna()
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * math.sqrt(TD)) if sd > 0 else float("nan")


def period_returns(r: pd.Series, freq: str) -> pd.Series:
    return (1 + r).groupby(r.index.to_period(freq)).prod() - 1


def deflated_sharpe(r: pd.Series, rf: pd.Series, n_trials: int = N_TRIALS) -> dict:
    """Bailey & Lopez de Prado (2014). Per-period SR of excess returns. The cross-trial variance of SR is not
    observable here, so V[SR] is taken as the null estimator variance 1/(T-1) (documented approximation)."""
    ex = (r - rf.reindex(r.index)).dropna()
    T = len(ex)
    sr = ex.mean() / ex.std(ddof=1)
    g3 = float(((ex - ex.mean()) ** 3).mean() / ex.std(ddof=0) ** 3)
    g4 = float(((ex - ex.mean()) ** 4).mean() / ex.std(ddof=0) ** 4)
    em = 0.5772156649
    sr0 = math.sqrt(1.0 / (T - 1)) * ((1 - em) * norm.ppf(1 - 1.0 / n_trials) + em * norm.ppf(1 - 1.0 / (n_trials * math.e)))
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2))
    dsr = norm.cdf((sr - sr0) * math.sqrt(T - 1) / denom)
    psr0 = norm.cdf(sr * math.sqrt(T - 1) / denom)
    return {"T": T, "sr_daily": float(sr), "sr_ann": float(sr * math.sqrt(TD)), "skew": g3, "kurt": g4,
            "sr0_daily": float(sr0), "sr0_ann": float(sr0 * math.sqrt(TD)), "dsr": float(dsr), "psr_vs_0": float(psr0),
            "n_trials": n_trials}


def stats(r: pd.Series, rf: pd.Series, pos: pd.Series | None = None) -> dict:
    r = r.dropna()
    yrs = period_returns(r, "Y")
    mos = period_returns(r, "M")
    out = {"start": str(r.index[0].date()), "end": str(r.index[-1].date()), "n_days": int(len(r)),
           "cagr": cagr(r), "maxdd": max_dd(r), "sharpe": sharpe(r, rf),
           "worst_year": float(yrs.min()), "worst_year_label": str(yrs.idxmin()),
           "worst_month": float(mos.min()), "worst_month_label": str(mos.idxmin())}
    if pos is not None:
        p = pos.reindex(r.index)
        n_years = len(r) / TD
        out["time_invested"] = float(p.mean())
        out["switches"] = int((pos.diff().abs().fillna(0) > 0).reindex(r.index).sum())
        out["switches_per_year"] = out["switches"] / n_years
    return out


def verdict(post_cagr: float, post_maxdd: float, post_bh_cagr: float, n_other_beat: int) -> dict:
    c1 = post_cagr >= 0.15
    c2 = post_maxdd >= -0.45
    c3 = post_cagr > post_bh_cagr
    c4 = n_other_beat >= 2
    rej = (post_cagr < 0.10) or (post_cagr <= post_bh_cagr) or (post_maxdd < -0.60)
    if c1 and c2 and c3 and c4:
        v = "PASS"
    elif rej:
        v = "REJET"
    else:
        v = "INCERTAIN"
    return {"verdict": v, "pass_c1_cagr_ge_15": c1, "pass_c2_maxdd_ge_m45": c2, "pass_c3_beats_bh": c3,
            "pass_c4_same_sign_2of3": c4, "reject_cagr_lt_10": post_cagr < 0.10,
            "reject_le_bh": post_cagr <= post_bh_cagr, "reject_maxdd_lt_m60": post_maxdd < -0.60}


def proxy_correction(synth: pd.Series, etf_ret: pd.Series, start: str) -> dict:
    """Compare CAGR of the always-invested synthetic vs the real ETF on common dates >= start.
    Returns gap and a conservative extra annual drag (only if synthetic > ETF by more than PROXY_TOL)."""
    idx = synth.dropna().index.intersection(etf_ret.dropna().index)
    idx = idx[idx >= pd.Timestamp(start)]
    cs, ce = cagr(synth.loc[idx]), cagr(etf_ret.loc[idx])
    gap = cs - ce
    drag = 0.0
    if gap > PROXY_TOL:
        lo, hi = 0.0, 0.2
        for _ in range(60):
            mid = (lo + hi) / 2
            if cagr(synth.loc[idx] - mid / TD) > ce:
                lo = mid
            else:
                hi = mid
        drag = (lo + hi) / 2
    return {"start": str(idx[0].date()), "end": str(idx[-1].date()), "cagr_synth": cs, "cagr_etf": ce,
            "gap": gap, "tolerance": PROXY_TOL, "within_tolerance": abs(gap) <= PROXY_TOL, "extra_drag_applied": drag}


# ---------------------------------------------------------------- data I/O
def download():
    import yfinance as yf
    import urllib.request
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"downloaded_utc": datetime.now(timezone.utc).isoformat(), "series": {}}
    for s in YAHOO:
        d = yf.download(s, start="1985-01-01", progress=False, auto_adjust=True)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        d = d[["Close"]].dropna()
        f = DATA_DIR / (s.replace("^", "IDX_").replace("=", "_") + ".csv")
        d.to_csv(f)
        meta["series"][s] = {"source": "Yahoo Finance via yfinance %s (auto_adjust=True)" % yf.__version__,
                             "file": f.name, "first": str(d.index[0].date()), "last": str(d.index[-1].date()), "rows": len(d)}
        print(s, len(d), d.index[0].date(), d.index[-1].date())
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXCAUS"
    f = DATA_DIR / "FRED_DEXCAUS.csv"
    urllib.request.urlretrieve(url, f)
    fx = pd.read_csv(f)
    meta["series"]["DEXCAUS"] = {"source": "FRED " + url, "file": f.name, "first": str(fx.iloc[0, 0]),
                                 "last": str(fx.iloc[-1, 0]), "rows": len(fx)}
    (DATA_DIR / "meta.json").write_text(json.dumps(meta, indent=2))


def load(sym: str) -> pd.Series:
    f = DATA_DIR / (sym.replace("^", "IDX_").replace("=", "_") + ".csv")
    d = pd.read_csv(f, index_col=0, parse_dates=True)
    s = d["Close"].astype(float)
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated()].sort_index()


def load_cadusd() -> pd.Series:
    """CAD per USD: FRED DEXCAUS (noon rate), spliced with Yahoo CAD=X after FRED's last date."""
    fx = pd.read_csv(DATA_DIR / "FRED_DEXCAUS.csv", index_col=0, parse_dates=True).iloc[:, 0]
    fx = pd.to_numeric(fx, errors="coerce").dropna()
    y = load("CAD=X")
    tail = y[y.index > fx.index[-1]]
    return pd.concat([fx, tail]).sort_index()


# ---------------------------------------------------------------- run
def rule_on_index(price: pd.Series, tr_level: pd.Series, rf_level: pd.Series, k: float = 2.0, lag: int = 2,
                  extra_drag: float = 0.0, start: str = START):
    """Returns (strategy daily returns, positions, r_tr, rf) on the index's own calendar, from `start`."""
    idx = price.index.intersection(tr_level.index)
    price, tr_level = price.loc[idx], tr_level.loc[idx]
    sig = sma_signal(price)
    pos = positions(sig, lag)
    r_tr = tr_level.pct_change()
    rf = (rf_level.reindex(idx.union(rf_level.index)).ffill().reindex(idx)) / 100.0 / TD
    r = strategy_returns(pos, r_tr, rf, k=k, extra_drag=extra_drag)
    m = idx >= pd.Timestamp(start)
    return r[m], pos[m], r_tr[m], rf[m]


def sub(r: pd.Series, a: str, b: str | None = None) -> pd.Series:
    m = r.index >= pd.Timestamp(a)
    if b is not None:
        m &= r.index <= pd.Timestamp(b)
    return r[m]


def run():
    meta = json.loads((DATA_DIR / "meta.json").read_text())
    gspc, tr, irx = load("^GSPC"), load("^SP500TR"), load("^IRX")
    sso, upro = load("SSO"), load("UPRO")

    # proxy checks (always-invested synthetic vs real ETF)
    idx = gspc.index.intersection(tr.index)
    r_tr_all = tr.loc[idx].pct_change()
    rf_all = (irx.reindex(idx.union(irx.index)).ffill().reindex(idx)) / 100.0 / TD
    chk2 = proxy_correction(leveraged_hold(r_tr_all, rf_all, 2.0), sso.pct_change(), "2007-01-01")
    chk3 = proxy_correction(leveraged_hold(r_tr_all, rf_all, 3.0), upro.pct_change(), "2009-06-26")
    drag2 = chk2["extra_drag_applied"]

    res = {"meta": meta, "params": {"sma": SMA_N, "fee": FEE, "switch_cost": SWITCH_COST, "td": TD, "n_trials": N_TRIALS,
                                     "pre": PRE, "post_start": POST_START, "exec_lag_days": 2},
           "proxy_check_x2_vs_SSO": chk2, "proxy_check_x3_vs_UPRO": chk3}

    r2, pos2, r_tr, rf = rule_on_index(gspc, tr, irx, 2.0, 2, drag2)
    r2_paper, pos2p, _, _ = rule_on_index(gspc, tr, irx, 2.0, 1, drag2)
    r2_nocorr, _, _, _ = rule_on_index(gspc, tr, irx, 2.0, 2, 0.0)
    r3, pos3, _, _ = rule_on_index(gspc, tr, irx, 3.0, 2, chk3["extra_drag_applied"])
    hold2 = leveraged_hold(r_tr, rf, 2.0, extra_drag=drag2)
    bh = r_tr

    series = {"rule_x2_t+1": (r2, pos2), "rule_x2_paper_t": (r2_paper, pos2p), "rule_x2_uncorrected": (r2_nocorr, pos2),
              "rule_x3_t+1": (r3, pos3), "hold_x2_nofilter": (hold2, None), "sp500tr_x1": (bh, None)}
    periods = {"full": (START, None), "pre": PRE, "post": (POST_START, None)}
    tab = {}
    for name, (r, p) in series.items():
        tab[name] = {pn: stats(sub(r, a, b), rf, p) for pn, (a, b) in periods.items()}
    res["sp500"] = tab

    dec = {}
    for name in ["rule_x2_t+1", "hold_x2_nofilter", "sp500tr_x1"]:
        r = series[name][0]
        for d0 in (1990, 2000, 2010, 2020):
            rr = sub(r, f"{d0}-01-01", f"{d0 + 9}-12-31")
            dec.setdefault(name, {})[f"{d0}s"] = {"cagr": cagr(rr), "maxdd": max_dd(rr), "start": str(rr.index[0].date()),
                                                   "end": str(rr.index[-1].date())}
    res["decades"] = dec

    # yearly returns
    yr = pd.DataFrame({n: period_returns(series[n][0], "Y") for n in ["rule_x2_t+1", "hold_x2_nofilter", "sp500tr_x1", "rule_x3_t+1"]})
    res["yearly"] = {str(k): {c: float(v) for c, v in row.items()} for k, row in yr.iterrows()}

    # Deflated Sharpe
    res["dsr"] = {"post": deflated_sharpe(sub(r2, POST_START), rf), "full": deflated_sharpe(r2, rf)}

    # CAD
    fx = load_cadusd()
    fxa = fx.reindex(r2.index.union(fx.index)).ffill().reindex(r2.index)
    fxr = fxa.pct_change().fillna(0)
    cad = {}
    for name in ["rule_x2_t+1", "sp500tr_x1"]:
        rc = (1 + series[name][0]) * (1 + fxr) - 1
        cad[name] = {pn: {"cagr": cagr(sub(rc, a, b)), "maxdd": max_dd(sub(rc, a, b))} for pn, (a, b) in periods.items()}
    res["cad"] = cad
    res["cad_fx_note"] = "FRED DEXCAUS (CAD per USD, noon/close-ish), Yahoo CAD=X spliced after FRED last date; forward-filled on S&P dates"

    # other indices: x2 rule (own SMA200) vs x1 hold, full available period from 1990
    others = {}
    ruttr = load("^RUTTR")
    for sym, tr_sym, note in [("^NDX", None, "no TR series on Yahoo (^XNDX empty): price-only both sides"),
                              ("^RUT", None, "^RUTTR only from 1995-06: price-only both sides over full period; TR from 1995 reported"),
                              ("^GDAXI", "^GDAXI", "DAX is a performance (total-return) index; EUR; US T-bill rf used as proxy")]:
        px = load(sym)
        trl = load(tr_sym) if tr_sym else px
        r, p, rt, rfx = rule_on_index(px, trl, irx, 2.0, 2, drag2)
        others[sym] = {"note": note, "rule_x2": stats(r, rfx, p), "hold_x1": stats(rt.dropna(), rfx),
                       "beats_hold": cagr(r) > cagr(rt.dropna())}
        others[sym]["rule_x2_post"] = stats(sub(r, POST_START), rfx, p)
        others[sym]["hold_x1_post"] = stats(sub(rt.dropna(), POST_START), rfx)
    # RUT TR sensitivity (signal still on ^RUT price, returns from ^RUTTR) from TR start
    rut = load("^RUT")
    r, p, rt, rfx = rule_on_index(rut, ruttr, irx, 2.0, 2, drag2, start="1995-06-02")
    others["^RUT_TR_sensitivity"] = {"note": "signal ^RUT, returns ^RUTTR, 1995-06+ (SMA warm-up uses only common dates -> first 200 sessions in cash)",
                                     "rule_x2": stats(r, rfx, p), "hold_x1": stats(rt.dropna(), rfx), "beats_hold": cagr(r) > cagr(rt.dropna())}
    res["others"] = others
    n_beat = sum(int(others[s]["beats_hold"]) for s in ["^NDX", "^RUT", "^GDAXI"])

    post = tab["rule_x2_t+1"]["post"]
    res["criteria"] = verdict(post["cagr"], post["maxdd"], tab["sp500tr_x1"]["post"]["cagr"], n_beat)
    res["criteria"].update({"post_cagr": post["cagr"], "post_maxdd": post["maxdd"],
                            "post_bh_cagr": tab["sp500tr_x1"]["post"]["cagr"], "n_other_indices_beating_hold": n_beat})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "Exp-74_2026-10-11_criteria.json").write_text(json.dumps(res, indent=2, default=str))
    daily = pd.DataFrame({"pos_rule": pos2, "rule_x2_t1": r2, "rule_x2_paper_t": r2_paper, "rule_x3_t1": r3,
                          "hold_x2_nofilter": hold2, "sp500tr_x1": bh, "rf_daily": rf, "cad_per_usd": fxa})
    daily.index.name = "date"
    daily.to_csv(OUT_DIR / "Exp-74_2026-10-11_daily_returns.csv", float_format="%.8g")
    print(json.dumps(res["criteria"], indent=2))
    print("proxy x2", json.dumps(chk2), "\nproxy x3", json.dumps(chk3))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    download() if mode == "download" else run()
