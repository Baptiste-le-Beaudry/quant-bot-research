"""T-073 atelier -- discovery-period control markets for the shortlisted ideas (1990 -> 2009 only,
all data via loader.py).  Each evaluation is one counted row of LOG.csv.

Fixed conventions for controls (written before computing):
  * Daily US sub-universes for C09 (trend OR US credit -> B10): Nasdaq-100 and Russell 2000 price
    indices + constant dividend yield (0.8 %/yr and 1.3 %/yr, rough 1990-2009 averages, added to
    both rule and reference: conservative for a rule that is out of equities part of the time), and
    Ken French Developed ex US (USD, total return).  Trend = the market's own index vs MM200.
  * Industry sub-universes for C13/C19: Ken French 30 and 49 industries, top quarter (8 / 12).
  * Monthly local-currency markets for C14 and C02: Germany (DAX performance index, Bund 10y,
    3-month rate), UK (FTSE 100 price + 3.5 %/yr, gilt 10y, 3-month rate), Japan (Nikkei 225 price +
    1.0 %/yr, JGB 10y, call rate).  Reference = local equity x L at equal vol, ppy = 12.
    C02 monthly uses 12-month volatility of monthly returns (63 days is not available monthly).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import discovery as D  # noqa: E402
import engine as E  # noqa: E402
import loader as L  # noqa: E402


# ------------------------------------------------------------------------------- daily US sub-universes
def c09_control(name: str) -> dict:
    d = D.data()
    cal = d["cal"]
    if name in ("NDX", "RUT"):
        px = L.yahoo_close(f"IDX_{name}")
        dy = {"NDX": 0.008, "RUT": 0.013}[name]
        r = px.pct_change().reindex(cal) + dy / 252
        idxpx = px
    else:  # DevExUS
        k = L.kf("Developed_ex_US_3_Factors_Daily_CSV.zip")
        rr = (k["Mkt-RF"] + k["RF"]).dropna()
        r = D.to_calendar(rr, cal)
        r[cal < rr.index[0]] = np.nan
        idxpx = (1 + rr).cumprod()
    s = d["baa10y"]
    cok = (s <= s.rolling(252).mean()).astype(float).reindex(cal, method="ffill")
    tok = D.above_ma(idxpx, 200, cal).fillna(0.0)
    ok = ((cok + tok) >= 1).astype(float)
    rets = pd.DataFrame({"EQX": r, "B10": d["B10"]}, index=cal)
    w = pd.DataFrame({"EQX": ok, "B10": 1 - ok}, index=cal)
    first = r.dropna().index[0]
    first_sig = idxpx.rolling(200).mean().dropna().index[0]
    start = max(first, first_sig + pd.Timedelta(days=7), pd.Timestamp(D.D0))
    w.loc[:start] = 0.0
    return _eval_daily(f"C09-ctl-{name}", "contrôle C09", f"{name}, MM200 propre, BAA10Y moy252, B10 US",
                       w, rets, rets["EQX"], start)


def _eval_daily(label, idea, params, w, rets, mkt, start):
    d = D.data()
    rf = d["rf"]
    rets = rets.loc[:D.D1].fillna(0.0)
    k, sim = E.scale_to_vol(w, rets, rf.loc[:D.D1], window=(start, D.D1))
    r = sim["ret"].loc[start:D.D1]
    ev = E.evaluate(r, rf.loc[r.index], mkt.loc[r.index])
    halves = []
    for a, b in D.HALVES:
        rr = r.loc[a:b]
        halves.append(E.evaluate(rr, rf.loc[rr.index], mkt.loc[rr.index])["dsharpe"] if len(rr) > 250 else np.nan)
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    return _row(label, idea, params, r, k, ev, halves, sim["orders"].loc[start:D.D1].sum() / yrs,
                sim["gross"].loc[start:D.D1].mean())


def _row(label, idea, params, r, k, ev, halves, orders, gross):
    p0, p1 = str(r.index[0])[:10], str(r.index[-1])[:10]
    row = {"date": date.today().isoformat(), "id": label, "idee": idea, "parametres": params,
           "periode": f"{p0}→{p1}", "k": round(k, 3),
           "sharpe": round(ev["sharpe"], 3), "dsharpe": round(ev["dsharpe"], 3),
           "cagr": round(ev["cagr"], 4), "maxdd": round(ev["maxdd"], 4), "vol": round(ev["vol"], 4),
           "L_ref": round(ev["L_ref"], 3), "ref_sharpe": round(ev["ref_sharpe"], 3),
           "ref_cagr": round(ev["ref_cagr"], 4), "ref_maxdd": round(ev["ref_maxdd"], 4),
           "dsharpe_1990s": round(halves[0], 3), "dsharpe_2000s": round(halves[1], 3),
           "ordres_an": round(float(orders), 1), "gross_moy": round(float(gross), 2), "note": "contrôle"}
    D.write_row(row)
    return row


# ------------------------------------------------------------------------------- monthly local markets
MKT = {
    "DE": {"eq": ("IDX_GDAXI", None, 0.0), "y10": "IRLTLT01DEM156N", "rf": "IR3TIB01DEM156N"},
    "UK": {"eq": ("YH_IDX_FTSE", "atelier", 0.035), "y10": "IRLTLT01GBM156N", "rf": "IR3TIB01GBM156N"},
    "JP": {"eq": ("YH_IDX_N225", "atelier", 0.010), "y10": "IRLTLT01JPM156N", "rf": "IRSTCI01JPM156N"},
}


def monthly_market(code: str) -> tuple[pd.DataFrame, pd.Series]:
    m = MKT[code]
    name, where, dy = m["eq"]
    px = L.yahoo_close(name, L.ATELIER_DIR if where == "atelier" else None)
    pm = px.groupby(px.index.to_period("M")).last()
    eq = pm.pct_change() + dy / 12
    y = L.fred(m["y10"])
    y.index = y.index.to_period("M")
    bond = E.bond_tr_from_yield(y, monthly=True)
    rf = L.fred(m["rf"])
    rf.index = rf.index.to_period("M")
    rf = (rf / 100 / 12).shift(1)  # rate known at the start of the month
    df = pd.DataFrame({"EQ": eq, "BOND": bond, "rf": rf}).dropna()
    return df, df.pop("rf")


def monthly_control(cid: str, code: str) -> dict:
    df, rf = monthly_market(code)
    idx = df.index
    if cid == "C14":
        nxt = (idx + 1).month
        sig = pd.Series(np.isin(nxt, [11, 12, 1, 2, 3, 4]).astype(float), index=idx)
        w = pd.DataFrame({"EQ": sig, "BOND": 1 - sig}, index=idx)
        idea, params = "contrôle C14", f"{code} mensuel, EQ nov-avr sinon obligation 10 ans locale"
        start = idx[0]
    elif cid == "C02":
        iv = 1.0 / df.rolling(12).std()
        w = iv.div(iv.sum(axis=1), axis=0)
        start = w.dropna().index[0] + 1
        w = w.fillna(0.0)
        idea, params = "contrôle C02", f"{code} mensuel, 1/vol 12 mois actions/obligation locale"
    else:
        raise KeyError(cid)
    start = max(start, pd.Period("1990-01", "M"))
    rets = df.loc[:"2009-12"]
    k, sim = E.scale_to_vol(w, rets, rf, lag=1, ppy=12, window=(start, pd.Period("2009-12", "M")))
    r = sim["ret"].loc[start:]
    ev = E.evaluate(r, rf.loc[r.index], df["EQ"].loc[r.index], ppy=12)
    halves = []
    for a, b in [("1990-01", "1999-12"), ("2000-01", "2009-12")]:
        rr = r.loc[a:b]
        halves.append(E.evaluate(rr, rf.loc[rr.index], df["EQ"].loc[rr.index], ppy=12)["dsharpe"])
    orders = sim["orders"].loc[start:].sum() / (len(r) / 12)
    return _row(f"{cid}-ctl-{code}", idea, params, r, k, ev, halves, orders, sim["gross"].loc[start:].mean())


def industry_control(cid: str, uni: str, k: int) -> dict:
    return D.run_config(cid, {"universe": uni, "k": k}, label=f"{cid}-ctl-{uni}", note="contrôle")


if __name__ == "__main__":
    out = []
    for a in sys.argv[1:]:
        cid, what = a.split(":")
        if cid == "C09":
            out.append(c09_control(what))
        elif cid in ("C14", "C02"):
            out.append(monthly_control(cid, what))
        elif cid in ("C13", "C19"):
            uni, k = what.split("/")
            out.append(industry_control(cid, uni, int(k)))
    for row in out:
        print({k: row[k] for k in ["id", "periode", "k", "sharpe", "dsharpe", "cagr", "maxdd", "dsharpe_1990s",
                                   "dsharpe_2000s", "ordres_an"]})
