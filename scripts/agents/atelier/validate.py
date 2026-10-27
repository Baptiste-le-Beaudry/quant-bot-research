"""T-074 -- ONE-SHOT validation 2010-01-04 -> end of Exp 77 (C09), 78 (C19), 79 (C02), 80 (C13).

Rules and engine are reused unchanged from scripts/agents/atelier/ (commit e0c3917):
  * discovery.rule / discovery.c09_signal / discovery.above_ma ... (rule logic),
  * controls.c09_control / controls.monthly_market / controls.monthly_control (control construction),
  * engine.simulate / engine.evaluate (costs, lag, reference at equal vol).
Only the data source changes: `discovery.L` and `controls.L` are pointed at loader_validation (same
parsers, no 2009-12-31 cut, data/atelier_validation).  k are the FROZEN discovery values
(candidats.md / LOG.csv); nothing is re-fitted (scale_to_vol is never called).

The discovery `run_config` / `_eval_daily` / `monthly_control` re-solve k on 1990-2009 and write
LOG.csv; they are therefore NOT called as such: their construction code is reused by intercepting
the point where they would re-solve k (the weights they built are captured, then simulated with the
frozen k on the full history, metrics on the validation window only).

Usage:  py -3 scripts/agents/atelier/validate.py [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import controls as C  # noqa: E402
import discovery as D  # noqa: E402
import engine as E  # noqa: E402
import loader_validation as LV  # noqa: E402

ROOT = HERE.parents[2]
V0 = LV.VAL_START
N_TRIALS = 117
SD_SR_ANN = 0.1116
TH = {"cagr": 0.15, "maxdd": -0.50, "dsharpe": 0.10, "n_controls_pos": 2, "dsr": 0.95}

# frozen discovery k (candidats.md, LOG.csv commit e0c3917)
EXPS = {
    "Exp-77": {"cid": "C09", "k": 1.532, "controls": [("C09", "NDX", 0.896), ("C09", "RUT", 1.390), ("C09", "DevExUS", 1.650)],
               "sources": ["tr", "gspc", "irx", "dgs10", "baa10y"], "disc": {"sharpe": 0.567, "dsharpe": 0.259}},
    "Exp-78": {"cid": "C19", "k": 1.418, "controls": [("C19", "ind30/8", 1.370), ("C19", "ind49/12", 1.377)],
               "sources": ["tr", "gspc", "irx", "dgs10", "baa10y", "ind12"], "disc": {"sharpe": 0.727, "dsharpe": 0.420}},
    "Exp-79": {"cid": "C02", "k": 2.877, "controls": [("C02", "DE", 3.434), ("C02", "UK", 3.070), ("C02", "JP", 3.077)],
               "sources": ["tr", "irx", "dgs10"], "disc": {"sharpe": 0.500, "dsharpe": 0.192}},
    "Exp-80": {"cid": "C13", "k": 1.098, "controls": [("C13", "ind30/8", 1.056), ("C13", "ind49/12", 1.063)],
               "sources": ["tr", "irx", "ind12"], "disc": {"sharpe": 0.484, "dsharpe": 0.176}},
}
# Ken French 12 industries -> US ETF used for the reported-only real-instrument control (approximate:
# KF industries are SIC-based, SPDRs are GICS; Durbl and Shops both map to XLY; Other -> SPY).
IND_ETF = {"NoDur": "XLP", "Durbl": "XLY", "Manuf": "XLI", "Enrgy": "XLE", "Chems": "XLB", "BusEq": "XLK",
           "Telcm": "IYZ", "Utils": "XLU", "Shops": "XLY", "Hlth": "XLV", "Money": "XLF", "Other": "SPY"}


# ------------------------------------------------------------------------------------ data
def point_modules_to_validation_loader():
    D.L = LV
    C.L = LV


def fill_cache() -> dict:
    """Same construction as discovery.data() for the keys used by C02/C09/C13/C19 and their controls
    (lines copied verbatim; data via loader_validation).  Keys not used by these rules (t10y3m,
    regions, cape) are not loaded."""
    L = LV
    D._CACHE.clear()
    tr = L.yahoo_close("IDX_SP500TR")
    cal = tr.index
    d = {"cal": cal}
    d["EQ"] = tr.pct_change()
    d["gspc"] = L.yahoo_close("IDX_GSPC")
    irx = L.yahoo_close("IDX_IRX")
    d["rf"] = (irx / 100 / 252).reindex(cal).ffill()
    dgs10 = L.fred("DGS10")
    b = E.bond_tr_from_yield(dgs10)
    d["B10"] = D.to_calendar(b, cal)
    d["B10_idx"] = (1 + b).cumprod()
    d["baa10y"] = L.fred("BAA10Y")
    ff = L.kf("F-F_Research_Data_Factors_daily_CSV.zip")
    d["kf_mkt"] = ff["Mkt-RF"] + ff["RF"]
    d["kf_rf"] = ff["RF"]
    d["ind12"] = L.kf("12_Industry_Portfolios_daily_CSV.zip")
    d["ind30"] = L.kf("30_Industry_Portfolios_daily_CSV.zip")
    d["ind49"] = L.kf("49_Industry_Portfolios_daily_CSV.zip")
    D._CACHE.update(d)
    last = {"tr": tr.index[-1], "gspc": d["gspc"].index[-1], "irx": irx.index[-1], "dgs10": dgs10.index[-1],
            "baa10y": d["baa10y"].index[-1], "ind12": d["ind12"].dropna(how="all").index[-1],
            "ind30": d["ind30"].dropna(how="all").index[-1], "ind49": d["ind49"].dropna(how="all").index[-1]}
    return last


def end_date(sources: list[str], last: dict) -> pd.Timestamp:
    """Last session where every source the rule uses is available (no zero-filled tail)."""
    cal = D._CACHE["cal"]
    e = min(last[s] for s in sources)
    return cal[cal <= e][-1]


# ------------------------------------------------------------------------------------ statistics
def deflated_sharpe(r: pd.Series, rf: pd.Series, n_trials: int = N_TRIALS, sd_sr_ann: float = SD_SR_ANN,
                    ppy: int = 252) -> dict:
    """Bailey & Lopez de Prado (2014) on per-period excess returns.  Variance of Sharpe across
    trials = sd_sr_ann**2 / ppy (preregistered: 0.1116 annual, N = 117)."""
    ex = (r - rf.reindex(r.index)).dropna()
    T = len(ex)
    sr = ex.mean() / ex.std(ddof=1)
    s0 = ex.std(ddof=0)
    g3 = float(((ex - ex.mean()) ** 3).mean() / s0 ** 3)
    g4 = float(((ex - ex.mean()) ** 4).mean() / s0 ** 4)
    em = 0.5772156649
    sd = sd_sr_ann / math.sqrt(ppy)
    sr0 = sd * ((1 - em) * norm.ppf(1 - 1.0 / n_trials) + em * norm.ppf(1 - 1.0 / (n_trials * math.e)))
    den = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2))
    return {"T": T, "sr_ann": float(sr * math.sqrt(ppy)), "sr0_ann": float(sr0 * math.sqrt(ppy)), "skew": g3,
            "kurt": g4, "dsr": float(norm.cdf((sr - sr0) * math.sqrt(T - 1) / den)), "n_trials": n_trials,
            "sd_sr_ann": sd_sr_ann}


def verdict(cagr_: float, maxdd: float, dsharpe: float, ctl_d: list[float], dsr: float) -> dict:
    c1, c2, c3, c5 = cagr_ >= TH["cagr"], maxdd >= TH["maxdd"], dsharpe >= TH["dsharpe"], dsr >= TH["dsr"]
    n_pos = sum(1 for x in ctl_d if x > 0)
    n_nonpos = len(ctl_d) - n_pos
    c4 = n_pos >= TH["n_controls_pos"]
    if dsharpe <= 0 or n_nonpos > len(ctl_d) / 2:
        v = "REJET"
    elif c1 and c2 and c3 and c4 and c5:
        v = "PASS"
    else:
        v = "INCERTAIN"
    return {"c1_cagr": bool(c1), "c2_maxdd": bool(c2), "c3_dsharpe": bool(c3), "c4_controls": bool(c4), "c5_dsr": bool(c5),
            "n_controls_pos": n_pos, "n_controls": len(ctl_d), "verdict": v}


def yearly(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index.year).prod() - 1


def top3_share(r: pd.Series, ref: pd.Series) -> dict:
    """As diagnostics.py: log surplus per calendar year vs the reference; share of the 3 best."""
    ex = np.log1p(yearly(r)) - np.log1p(yearly(ref))
    top = ex.nlargest(3)
    tot = float(ex.sum())
    return {"years": [int(y) for y in top.index], "share": float(top.sum() / tot) if tot != 0 else float("nan"),
            "total_log_surplus": tot}


def eff_weights(w: pd.DataFrame, rets: pd.DataFrame, lag: int = 2) -> pd.DataFrame:
    """Held weights exactly as engine.simulate builds them."""
    return w.reindex(columns=rets.columns).reindex(rets.index).ffill().shift(lag).fillna(0.0)


def orders_per_year(sim: pd.DataFrame, a, b) -> float:
    o = sim["orders"].loc[a:b]
    yrs = (o.index[-1] - o.index[0]).days / 365.25
    return float(o.sum() / yrs)


def to_cad(r: pd.Series, fx_cad_per_usd: pd.Series) -> pd.Series:
    fx = fx_cad_per_usd.reindex(fx_cad_per_usd.index.union(r.index)).ffill().reindex(r.index)
    return (1 + r) * (fx / fx.shift(1)) - 1


def ev_round(ev: dict) -> dict:
    return {k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in ev.items()}


# ------------------------------------------------------------------------------------ controls
class _Captured(Exception):
    pass


def captured_c09_control(name: str):
    """Run controls.c09_control unchanged, intercepting _eval_daily (which would re-solve k)."""
    orig = C._eval_daily

    def grab(label, idea, params, w, rets, mkt, start):
        raise _Captured((w, rets, mkt, start))
    C._eval_daily = grab
    try:
        C.c09_control(name)
    except _Captured as cap:
        return cap.args[0]
    finally:
        C._eval_daily = orig
    raise RuntimeError("c09_control did not reach _eval_daily")


class _EngineShim:
    """Delegates to engine, except scale_to_vol which captures the weights built by monthly_control."""
    def __getattr__(self, item):
        return getattr(E, item)

    @staticmethod
    def scale_to_vol(w, rets, rf, **kw):
        raise _Captured((w, rf, kw))


def captured_monthly_control(cid: str, code: str):
    orig = C.E
    C.E = _EngineShim()
    try:
        C.monthly_control(cid, code)
    except _Captured as cap:
        return cap.args[0]
    finally:
        C.E = orig
    raise RuntimeError("monthly_control did not reach scale_to_vol")


def run_control(cid: str, what: str, k: float, last: dict) -> dict:
    d = D._CACHE
    rf = d["rf"]
    if cid == "C09":
        w, rets, mkt, start = captured_c09_control(what)
        rets = rets.fillna(0.0)  # as controls._eval_daily
        sim = E.simulate(w * k, rets, rf)
        if what == "DevExUS":
            kfx = LV.kf("Developed_ex_US_3_Factors_Daily_CSV.zip")
            src_end = (kfx["Mkt-RF"] + kfx["RF"]).dropna().index[-1]
        else:
            src_end = LV.yahoo_close(f"IDX_{what}").index[-1]
        b = end_date(["tr", "irx", "dgs10", "baa10y"], last)
        b = min(b, d["cal"][d["cal"] <= src_end][-1])
        r = sim["ret"].loc[V0:b]
        ev = E.evaluate(r, rf.loc[r.index], mkt.loc[r.index])
        per = (str(r.index[0].date()), str(r.index[-1].date()))
        ords = orders_per_year(sim, V0, b)
    elif cid in ("C13", "C19"):
        uni, kk = what.split("/")
        w, rets, _, _ = D.rule(cid, {"universe": uni, "k": int(kk)})
        sim = E.simulate(w * k, rets, rf)
        srcs = ["tr", "irx", uni] + (["gspc", "dgs10", "baa10y"] if cid == "C19" else [])
        b = end_date(srcs, last)
        r = sim["ret"].loc[V0:b]
        ev = E.evaluate(r, rf.loc[r.index], d["EQ"].loc[r.index])
        per = (str(r.index[0].date()), str(r.index[-1].date()))
        ords = orders_per_year(sim, V0, b)
    elif cid == "C02":
        w, rf_m, kw = captured_monthly_control(cid, what)
        df, rf_m = C.monthly_market(what)  # full history (monthly_control cut it at 2009-12)
        name = C.MKT[what]["eq"][0]
        px = LV.yahoo_close(name)
        b = min(df.index[-1], LV.last_complete_month(px.index[-1]))
        sim = E.simulate(w * k, df, rf_m, lag=kw.get("lag", 1), ppy=kw.get("ppy", 12))
        r = sim["ret"].loc[LV.VAL_START_MONTH:b]
        ev = E.evaluate(r, rf_m.loc[r.index], df["EQ"].loc[r.index], ppy=12)
        per = (str(r.index[0]), str(r.index[-1]))
        ords = float(sim["orders"].loc[LV.VAL_START_MONTH:b].sum() / (len(r) / 12))
    else:
        raise KeyError(cid)
    return {"control": f"{cid}-ctl-{what}", "k_frozen": k, "period": per, "orders_per_year": ords, **ev_round(ev)}


# ------------------------------------------------------------------------------------ main experiment
def fixed_mix(cid: str, w: pd.DataFrame, rets: pd.DataFrame, k: float, a, b) -> tuple[pd.Series, dict]:
    """Fixed weights = mean held weights of the rule on the validation window (same k)."""
    d = D._CACHE
    we = eff_weights(w * k, rets).loc[a:b]
    mw = we.mean()
    if cid == "C13":  # no bond leg: the 12 industries at their mean weights
        wm = pd.DataFrame([mw.values] * len(rets.index), index=rets.index, columns=rets.columns)
        mix_rets = rets
        desc = {c: float(v) for c, v in mw.items()}
    else:
        eq_w = float(mw.drop("B10").sum())
        b_w = float(mw["B10"])
        mix_rets = pd.DataFrame({"EQ": d["EQ"], "B10": d["B10"]}).reindex(rets.index)
        wm = pd.DataFrame({"EQ": eq_w, "B10": b_w}, index=rets.index)
        desc = {"EQ (S&P 500 TR)": eq_w, "B10": b_w}
    sim = E.simulate(wm, mix_rets, d["rf"])
    return sim["ret"].loc[a:b], desc


def real_instruments(cid: str, w: pd.DataFrame, rets: pd.DataFrame, k: float, b) -> dict:
    """Reported only.  Variant A (all): synthetic legs replaced by 1x ETFs (EQ->SPY, B10->IEF,
    industries->sector ETFs), same weights x k, engine financing on gross>1.  Variant B (C09, C02):
    2x ETFs SSO/UST for the leverage (C09: SPY/SSO and IEF/UST blend, gross 1; C02: SSO + UST at k/2,
    the excess over 1 financed by the engine at T-bill + 1.8 %)."""
    d = D._CACHE
    cal, rf = d["cal"], d["rf"]
    etf = {}
    for t in ["SPY", "SSO", "IEF", "UST"] + sorted(set(IND_ETF.values())):
        px = LV.yahoo_close(f"ETF_{t}")
        etf[t] = px.pct_change().reindex(cal)
    out = {}
    # variant A
    cols = {}
    for c in rets.columns:
        cols[c] = etf["SPY"] if c == "EQ" else etf["IEF"] if c == "B10" else etf[IND_ETF[c]]
    ra = pd.DataFrame(cols)
    used = [IND_ETF.get(c, "SPY" if c == "EQ" else "IEF") for c in rets.columns]
    a0 = max([V0] + [etf[t].dropna().index[0] + pd.Timedelta(days=7) for t in used])
    b_etf = min([b] + [etf[t].dropna().index[-1] for t in used])
    sim = E.simulate(w * k, ra.fillna(0.0), rf)
    r = sim["ret"].loc[a0:b_etf]
    ev = E.evaluate(r, rf.loc[r.index], etf["SPY"].loc[r.index])
    out["A_etf_1x_engine_financing"] = {"etfs": sorted(set(used)), "period": (str(r.index[0].date()), str(r.index[-1].date())),
                                        **ev_round(ev)}
    # variant B
    if cid in ("C09", "C02"):
        we = w.reindex(cal).ffill().fillna(0.0)
        if cid == "C09":
            ok = we["EQ"]  # 1 = equities, 0 = bonds (rule weights before k)
            wb = pd.DataFrame({"SPY": ok * (2 - k), "SSO": ok * (k - 1), "IEF": (1 - ok) * (2 - k), "UST": (1 - ok) * (k - 1)})
        else:
            wb = pd.DataFrame({"SSO": we["EQ"] * k / 2, "UST": we["B10"] * k / 2})
        wb = wb.where(w.reindex(cal).notna().any(axis=1), np.nan)  # same decision dates as the rule
        rb = pd.DataFrame({c: etf[c] for c in wb.columns})
        a1 = max(V0, etf["UST"].dropna().index[0] + pd.Timedelta(days=7))
        b1 = min([b] + [etf[c].dropna().index[-1] for c in wb.columns])
        simb = E.simulate(wb, rb.fillna(0.0), rf)
        r = simb["ret"].loc[a1:b1]
        ev = E.evaluate(r, rf.loc[r.index], etf["SPY"].loc[r.index])
        out["B_2x_etfs"] = {"etfs": list(wb.columns), "period": (str(r.index[0].date()), str(r.index[-1].date())),
                            "gross_mean": float(simb["gross"].loc[a1:b1].mean()), **ev_round(ev)}
    return out


def run_exp(exp: str, spec: dict, last: dict, fx: pd.Series) -> tuple[dict, pd.Series]:
    d = D._CACHE
    rf, cid, k = d["rf"], spec["cid"], spec["k"]
    b = end_date(spec["sources"], last)
    w, rets, idea, params = D.rule(cid)
    sim = E.simulate(w * k, rets, rf)  # full history: pre-2010 = warm-up / positions carried in
    r = sim["ret"].loc[V0:b]
    ev = E.evaluate(r, rf.loc[r.index], d["EQ"].loc[r.index])
    dsr = deflated_sharpe(r, rf)
    ref = E.ref_returns(ev["L_ref"], d["EQ"].loc[r.index], rf.loc[r.index])
    # reproduction check on the ALREADY-SEEN discovery window with the re-downloaded data
    rd = sim["ret"].loc[D.D0:D.D1]
    evd = E.evaluate(rd, rf.loc[rd.index], d["EQ"].loc[rd.index])
    # controls
    ctl = [run_control(c, wht, kc, last) for c, wht, kc in spec["controls"]]
    v = verdict(ev["cagr"], ev["maxdd"], ev["dsharpe"], [c["dsharpe"] for c in ctl], dsr["dsr"])
    # reported without effect
    rmix, mixw = fixed_mix(cid, w, rets, k, V0, b)
    mix_stats = E.stats(rmix, rf.loc[rmix.index])
    subs = {}
    for a_, b_ in [("2010-01-04", "2019-12-31"), ("2020-01-01", str(b.date()))]:
        rr = r.loc[a_:b_]
        e2 = E.evaluate(rr, rf.loc[rr.index], d["EQ"].loc[rr.index])
        subs[f"{a_[:4]}..{b_[:10]}"] = ev_round(e2)
    yr, yref = yearly(r), yearly(ref)
    yeq = yearly(d["EQ"].loc[r.index])
    r_cad, ref_cad = to_cad(r, fx).dropna(), to_cad(ref, fx).dropna()
    eq_on = float((eff_weights(w * k, rets).loc[V0:b].drop(columns=["B10"], errors="ignore").sum(axis=1) > 0).mean())
    res = {
        "exp": exp, "rule_id": cid, "idea": idea, "params": params, "k_frozen": k,
        "period": (str(r.index[0].date()), str(r.index[-1].date())), "n_days": int(len(r)),
        "end_date_sources": {s: str(last[s].date()) for s in spec["sources"]},
        "main": ev_round(ev), "dsr": dsr, "controls": ctl, "criteria": v,
        "thresholds": TH,
        "reported": {
            "orders_per_year": orders_per_year(sim, V0, b), "gross_mean": float(sim["gross"].loc[V0:b].mean()),
            "share_days_equity_on": eq_on,
            "fixed_mix": {"weights": mixw, **{k2: float(v2) for k2, v2 in mix_stats.items()},
                          "dsharpe_rule_minus_mix": float(ev["sharpe"] - mix_stats["sharpe"])},
            "subperiods": subs,
            "year_2022": {"rule": float(yr.get(2022, np.nan)), "ref_L": float(yref.get(2022, np.nan)),
                          "sp500tr_x1": float(yeq.get(2022, np.nan))},
            "yearly": {str(y): {"rule": float(yr[y]), "ref_L": float(yref[y]), "sp500tr_x1": float(yeq[y])} for y in yr.index},
            "top3_years_share_of_log_surplus": top3_share(r, ref),
            "cad": {"rule": E.stats(r_cad, rf.loc[r_cad.index]) | {}, "ref_L": E.stats(ref_cad, rf.loc[ref_cad.index]),
                    "note": "USD returns converted to CAD with FRED DEXCAUS (unhedged); Sharpe here uses the US T-bill"},
            "real_instruments": real_instruments(cid, w, rets, k, b),
            "sp500tr_x1_same_period": {k2: float(v2) for k2, v2 in E.stats(d["EQ"].loc[r.index], rf.loc[r.index]).items()},
            "discovery_reproduction_with_new_data": {"sharpe": float(evd["sharpe"]), "dsharpe": float(evd["dsharpe"]),
                                                     "cagr": float(evd["cagr"]), "maxdd": float(evd["maxdd"]),
                                                     "log_csv": spec["disc"]},
        },
    }
    for kk in ("rule", "ref_L"):
        res["reported"]["cad"][kk] = {k2: float(v2) for k2, v2 in res["reported"]["cad"][kk].items()}
    return res, r.rename(exp)


def main(out_dir: Path, stem: str):
    point_modules_to_validation_loader()
    last = fill_cache()
    fx = LV.fred("DEXCAUS")
    results, series = {}, []
    for exp, spec in EXPS.items():
        res, r = run_exp(exp, spec, last, fx)
        results[exp] = res
        series.append(r)
        m, c = res["main"], res["criteria"]
        print(exp, res["rule_id"], res["period"], f"CAGR {m['cagr']:.4f} MaxDD {m['maxdd']:.4f} Sharpe {m['sharpe']:.3f} "
              f"dS {m['dsharpe']:+.3f} DSR {res['dsr']['dsr']:.3f} ctl {[round(x['dsharpe'], 3) for x in res['controls']]} "
              f"-> {c['verdict']}", flush=True)
    meta = {"task": "T-074", "n_trials_dsr": N_TRIALS, "sd_sr_ann": SD_SR_ANN, "val_start": str(V0.date()),
            "data_dir": str(LV.VALIDATION_DIR), "source_last_dates": {k: str(v.date()) for k, v in last.items()},
            "code_rules_engine_commit": "e0c3917", "prereg_commit": "9f6baca"}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{stem}_criteria.json").write_text(json.dumps({"meta": meta, **results}, indent=1, default=str),
                                                   encoding="utf-8")
    pd.concat(series, axis=1).to_csv(out_dir / f"{stem}_daily.csv", float_format="%.8f")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(ROOT / "docs" / "agents" / "results"))
    ap.add_argument("--stem", default="Exp-77-80_validation_2026-10-11")
    a = ap.parse_args()
    main(Path(a.out_dir), a.stem)
