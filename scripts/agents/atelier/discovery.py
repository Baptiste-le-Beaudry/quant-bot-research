"""T-073 atelier -- discovery runs (1990-01-02 -> 2009-12-31) of the ideas in
docs/agents/research/atelier/IDEES.md.  All data via loader.py (hard 2009-12-31 cutoff).

Usage:  py -3 scripts/agents/atelier/discovery.py C01 C02 ...
Each evaluated configuration is written (one row, replaced if re-run) to
docs/agents/research/atelier/LOG.csv.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import loader as L  # noqa: E402

ROOT = HERE.parents[2]
LOG = ROOT / "docs" / "agents" / "research" / "atelier" / "LOG.csv"
D0, D1 = "1990-01-02", "2009-12-31"
HALVES = [("1990-01-02", "1999-12-31"), ("2000-01-01", "2009-12-31")]


# ------------------------------------------------------------------------------------ data
_CACHE: dict = {}


def to_calendar(r: pd.Series, cal: pd.DatetimeIndex) -> pd.Series:
    """Re-express a return series on another trading calendar by compounding (no look-ahead:
    the cumulative index is forward-filled)."""
    idx = (1 + r.fillna(0.0)).cumprod()
    idx = idx.reindex(idx.index.union(cal)).ffill().reindex(cal)
    return idx.pct_change()


def data() -> dict:
    if _CACHE:
        return _CACHE
    tr = L.yahoo_close("IDX_SP500TR")
    cal = tr.index
    d = {"cal": cal}
    d["EQ"] = tr.pct_change()
    d["gspc"] = L.yahoo_close("IDX_GSPC")
    irx = L.yahoo_close("IDX_IRX")
    d["rf"] = (irx / 100 / 252).reindex(cal).ffill()
    b = E.bond_tr_from_yield(L.fred("DGS10"))
    d["B10"] = to_calendar(b, cal)
    d["B10_idx"] = (1 + b).cumprod()
    d["baa10y"] = L.fred("BAA10Y")
    d["t10y3m"] = L.fred("T10Y3M")
    ff = L.kf("F-F_Research_Data_Factors_daily_CSV.zip")
    d["kf_mkt"] = ff["Mkt-RF"] + ff["RF"]
    d["kf_rf"] = ff["RF"]
    d["ind12"] = L.kf("12_Industry_Portfolios_daily_CSV.zip")
    d["ind30"] = L.kf("30_Industry_Portfolios_daily_CSV.zip")
    d["ind49"] = L.kf("49_Industry_Portfolios_daily_CSV.zip")
    reg = {"US": ff}
    for k, fn in [("EU", "Europe_3_Factors_Daily_CSV.zip"), ("JP", "Japan_3_Factors_Daily_CSV.zip"),
                  ("AP", "Asia_Pacific_ex_Japan_3_Factors_Daily_CSV.zip")]:
        reg[k] = L.kf(fn)
    d["regions"] = pd.DataFrame({k: v["Mkt-RF"] + v["RF"] for k, v in reg.items()})
    sh = L.shiller_xls()
    d["cape"] = sh["CAPE"]
    _CACHE.update(d)
    return d


def month_ends(cal: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(cal, index=cal)
    return pd.DatetimeIndex(s.groupby(cal.to_period("M")).last().values)


# ------------------------------------------------------------------------------------ rules
def W(cal, **cols) -> pd.DataFrame:
    return pd.DataFrame({k: (v.reindex(cal) if isinstance(v, pd.Series) else v) for k, v in cols.items()}, index=cal)


def monthly_only(w: pd.DataFrame, cal) -> pd.DataFrame:
    me = month_ends(cal)
    out = w.copy() * np.nan
    out.loc[me] = w.loc[me]
    out.iloc[0] = w.iloc[0].fillna(0.0)
    return out


def above_ma(px: pd.Series, n: int, cal) -> pd.Series:
    return (px > px.rolling(n).mean()).astype(float).reindex(cal, method="ffill")


def inv_vol_weights(rets: pd.DataFrame, n: int, cal) -> pd.DataFrame:
    iv = 1.0 / rets.rolling(n).std()
    w = iv.div(iv.sum(axis=1), axis=0)
    return monthly_only(w.reindex(cal).ffill(), cal)


def assets(d, names):
    return pd.DataFrame({n: d[n] for n in names}).reindex(d["cal"])


def rule(cid: str, p: dict | None = None):
    """Returns (target_w, rets, description, params string)."""
    p = p or {}
    d = data()
    cal = d["cal"]
    one = pd.Series(1.0, index=cal)
    sb = assets(d, ["EQ", "B10"])
    ma = p.get("ma", 200)
    if cid == "C01":
        return W(cal, EQ=0.6 * one, B10=0.4 * one), sb, "I1 60/40 fixe", "EQ 0.6 / B10 0.4"
    if cid in ("C02", "C04"):
        n = p.get("vol", 63)
        w = inv_vol_weights(sb, n, cal)
        if cid == "C04":
            w = w.ffill() * pd.DataFrame({"EQ": above_ma(d["gspc"], ma, cal), "B10": above_ma(d["B10_idx"], ma, cal)})
            return w, sb, "I2 parité de risque + MM par poche", f"1/vol {n}j, MM{ma}, cash si sous MM"
        return w, sb, "I1 parité de risque EQ/B10", f"1/vol {n}j, mensuel"
    if cid == "C03":
        w = W(cal, EQ=0.6 * above_ma(d["gspc"], ma, cal), B10=0.4 * above_ma(d["B10_idx"], ma, cal))
        return w, sb, "I2 60/40 + MM par poche", f"MM{ma}, cash si sous MM"
    if cid == "C05":
        up = above_ma(d["gspc"], ma, cal)
        return W(cal, EQ=up, B10=1 - up), sb, "I3 EQ si GSPC>MM sinon B10", f"MM{ma}"
    if cid in ("C06", "C07"):
        n = p.get("sma", 252)
        s = d["baa10y"]
        ok = (s <= s.rolling(n).mean()).astype(float).reindex(cal, method="ffill")
        if cid == "C06":
            return W(cal, EQ=ok), sb, "I4 crédit, sinon cash", f"BAA10Y<=moy{n}j"
        return W(cal, EQ=ok, B10=1 - ok), sb, "I4 crédit, sinon B10", f"BAA10Y<=moy{n}j"
    if cid == "C08":
        ok = (d["t10y3m"] >= 0).astype(float).reindex(cal, method="ffill")
        return W(cal, EQ=ok, B10=1 - ok), sb, "I5 courbe 10a-3m", "EQ si T10Y3M>=0 sinon B10"
    if cid in ("C09", "C10"):
        s = d["baa10y"]
        n = p.get("sma", 252)
        cok = (s <= s.rolling(n).mean()).astype(float).reindex(cal, method="ffill")
        tok = above_ma(d["gspc"], ma, cal)
        ok = ((cok + tok) >= 1).astype(float) if cid == "C09" else (cok * tok)
        lab = "ou" if cid == "C09" else "et"
        return W(cal, EQ=ok, B10=1 - ok), sb, f"I6 EQ si tendance {lab} crédit OK, sinon B10", f"MM{ma}, BAA10Y moy{n}j"
    if cid in ("C11", "C12", "C13"):
        uni = p.get("universe", "ind12")
        ind = d[uni].reindex(cal)
        if cid == "C12":
            n = p.get("vol", 63)
            return inv_vol_weights(ind, n, cal), ind, "I7 12 industries 1/vol", f"1/vol {n}j mensuel"
        me = month_ends(cal)
        w = pd.DataFrame(np.nan, index=cal, columns=ind.columns)
        if cid == "C11":
            n, k = p.get("beta_win", 252), p.get("k", 4)
            mkt = d["kf_mkt"].reindex(cal)
            rfk = d["kf_rf"].reindex(cal)
            ex = ind.sub(rfk, axis=0)
            mx = mkt - rfk
            for t in me:
                win = slice(cal[max(0, cal.get_loc(t) - n + 1)], t)
                if cal.get_loc(t) < n:
                    continue
                X, Y = mx.loc[win], ex.loc[win]
                beta = Y.apply(lambda c: np.cov(c, X)[0, 1]) / X.var()
                sel = beta.nsmallest(k).index
                w.loc[t] = 0.0
                w.loc[t, sel] = 1.0 / k
            return w, ind, "I7 industries à bêta le plus faible", f"bêta {n}j, k={k}, mensuel"
        # C13 momentum 12-1
        k = p.get("k", 3)
        mret = (1 + ind.fillna(0)).groupby(cal.to_period("M")).prod()
        lb = p.get("lookback", 11)
        mom = mret.rolling(lb).apply(np.prod, raw=True).shift(1) - 1  # months m-lb..m-1
        for t in me:
            per = t.to_period("M")
            if per not in mom.index or mom.loc[per].dropna().size < 2 * k:
                continue
            sel = mom.loc[per].dropna().nlargest(k).index
            w.loc[t] = 0.0
            w.loc[t, sel] = 1.0 / k
        return w, ind, "I8 momentum sectoriel", f"{uni} top {k}, {lb + 1}-1 mois, mensuel"
    if cid in ("C14", "C15"):
        months = p.get("winter", [11, 12, 1, 2, 3, 4])
        winter = pd.Series(cal.month.isin(months).astype(float), index=cal)
        # decision taken 2 sessions before the month change so that the lag-2 execution lands on it
        sig = winter.shift(-2).ffill()
        if cid == "C14":
            return W(cal, EQ=sig, B10=1 - sig), sb, "I9 Halloween, été en B10", f"EQ mois {months}, B10 sinon"
        return W(cal, EQ=sig), sb, "I9 Halloween, été en cash", "EQ nov-avr, cash mai-oct"
    if cid == "C16":
        cape = d["cape"].dropna()
        med = cape.rolling(240, min_periods=240).median()
        cheap = (cape <= med).astype(float).where(med.notna()).shift(2)  # 2-month publication lag
        me = month_ends(cal)
        sig = pd.Series(np.nan, index=cal)
        for t in me:
            per = t.to_period("M")
            if per in cheap.index and not np.isnan(cheap.loc[per]):
                sig.loc[t] = cheap.loc[per]
        sig = sig.ffill().fillna(0.0)
        return W(cal, EQ=0.6 + 0.4 * sig, B10=0.4 * (1 - sig)), sb, "I10 CAPE vs médiane 20 ans", "EQ 100% si CAPE<=méd240m (lag 2m) sinon 60/40"
    if cid == "C17":
        px = d["gspc"]
        dd = px / px.rolling(252, min_periods=1).max() - 1
        boost = ((dd <= -0.20) & (px > px.rolling(50).mean())).astype(float).reindex(cal, method="ffill")
        return W(cal, EQ=1 + 0.5 * boost), sb, "I11 contrarian après krach", "EQ 1, 1.5 si DD252<=-20% et >MM50"
    if cid == "C18":
        k = p.get("k", 2)
        reg = pd.DataFrame({c: to_calendar(d["regions"][c].dropna(), cal) for c in d["regions"].columns})
        me = month_ends(cal)
        mret = (1 + reg.fillna(0)).groupby(cal.to_period("M")).prod().where(reg.groupby(cal.to_period("M")).count() > 0)
        mom = mret.rolling(11).apply(np.prod, raw=True).shift(1) - 1
        w = pd.DataFrame(np.nan, index=cal, columns=reg.columns)
        for t in me:
            per = t.to_period("M")
            if per not in mom.index or mom.loc[per].isna().any():
                continue
            sel = mom.loc[per].nlargest(k).index
            w.loc[t] = 0.0
            w.loc[t, sel] = 1.0 / k
        return w, reg, "I12 momentum régions", f"top {k}/4 sur 12-1 mois, mensuel"
    if cid in ("C19", "C20"):
        ok = c09_signal(p)
        if cid == "C19":
            w, ind, _, _ = rule("C13", p)
            w = w.ffill().fillna(0.0).mul(ok, axis=0)
            w["B10"] = 1 - ok
            rets = pd.concat([ind, d["B10"].reindex(cal).rename("B10")], axis=1)
            return w, rets, "I8+I6 momentum sectoriel, B10 si signal C09 mauvais", f"{p.get('universe', 'ind12')} top{p.get('k', 3)} 12-1 ; MM200 ou BAA10Y moy252"
        w = inv_vol_weights(sb, p.get("vol", 63), cal).ffill()
        eq = w["EQ"] * ok
        w = pd.DataFrame({"EQ": eq, "B10": w["B10"] + w["EQ"] * (1 - ok)})
        return w, sb, "I1+I6 parité de risque, poche actions en B10 si signal C09 mauvais", "1/vol 63j ; MM200 ou BAA10Y moy252"
    raise KeyError(cid)


def c09_signal(p: dict | None = None) -> pd.Series:
    p = p or {}
    d = data()
    cal = d["cal"]
    s = d["baa10y"]
    n, ma = p.get("sma", 252), p.get("ma", 200)
    cok = (s <= s.rolling(n).mean()).astype(float).reindex(cal, method="ffill")
    tok = above_ma(d["gspc"], ma, cal)
    return ((cok + tok) >= 1).astype(float)


# ------------------------------------------------------------------------------------ evaluation
def run_config(cid: str, p: dict | None = None, label: str | None = None, note: str = "") -> dict:
    d = data()
    w, rets, idea, params = rule(cid, p)
    rf = d["rf"]
    win = slice(D0, D1)
    rets_d, rf_d = rets.loc[:D1], rf.loc[:D1]
    k, sim = E.scale_to_vol(w, rets_d, rf_d, target=E.TARGET_VOL, window=(D0, D1))
    r = sim["ret"].loc[win]
    # first date with a non-zero position inside the window (C18 starts later)
    live = sim["gross"].loc[win]
    start = live[live > 0].index[0]
    r = r.loc[start:]
    ev = E.evaluate(r, rf.loc[start:D1], d["EQ"].loc[start:D1])
    halves = []
    for a, b in HALVES:
        rr = r.loc[a:b]
        halves.append(E.evaluate(rr, rf.loc[rr.index], d["EQ"].loc[rr.index])["dsharpe"] if len(rr) > 250 else np.nan)
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    row = {"date": date.today().isoformat(), "id": label or cid, "idee": idea, "parametres": params,
           "periode": f"{r.index[0].date()}→{r.index[-1].date()}", "k": round(k, 3),
           "sharpe": round(ev["sharpe"], 3), "dsharpe": round(ev["dsharpe"], 3),
           "cagr": round(ev["cagr"], 4), "maxdd": round(ev["maxdd"], 4), "vol": round(ev["vol"], 4),
           "L_ref": round(ev["L_ref"], 3), "ref_sharpe": round(ev["ref_sharpe"], 3),
           "ref_cagr": round(ev["ref_cagr"], 4), "ref_maxdd": round(ev["ref_maxdd"], 4),
           "dsharpe_1990s": round(halves[0], 3), "dsharpe_2000s": round(halves[1], 3),
           "ordres_an": round(sim["orders"].loc[start:D1].sum() / yrs, 1),
           "gross_moy": round(sim["gross"].loc[start:D1].mean(), 2), "note": note}
    write_row(row)
    return row


def write_row(row: dict):
    cols = list(row.keys())
    if LOG.exists():
        df = pd.read_csv(LOG, dtype=str, keep_default_na=False)
        df = df[df["id"] != row["id"]]
        df = pd.concat([df, pd.DataFrame([row]).astype(str)], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    LOG.parent.mkdir(parents=True, exist_ok=True)
    df[cols].to_csv(LOG, index=False)


WAVE2 = {"C09b": ("C09", {"ma": 250}), "C09c": ("C09", {"sma": 126}),
         "C14b": ("C14", {"winter": [10, 11, 12, 1, 2, 3, 4]}), "C14c": ("C14", {"winter": [11, 12, 1, 2, 3, 4, 5]}),
         "C13b": ("C13", {"k": 4}), "C13c": ("C13", {"lookback": 5}), "C02b": ("C02", {"vol": 126}),
         "C11b": ("C11", {"k": 6})}


if __name__ == "__main__":
    ids = sys.argv[1:]
    for cid in ids:
        base, prm = WAVE2.get(cid, (cid, None))
        row = run_config(base, prm, label=cid)
        print({k: row[k] for k in ["id", "idee", "k", "sharpe", "dsharpe", "cagr", "maxdd", "dsharpe_1990s",
                                   "dsharpe_2000s", "ordres_an", "gross_moy"]})
