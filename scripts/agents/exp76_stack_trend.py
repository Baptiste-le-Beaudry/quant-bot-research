"""Exp 76 (preregistered, docs/agents/hypotheses/Exp-76.md, commit 3cec3d5): US equities x1 + trend (TSMOM) x1
stacked, versus US equities at constant leverage L with EQUAL volatility (L re-solved on every evaluated period).

Rule (fixed, monthly):
  * TSMOM_s,t = k_t * TSMOM_t, k_t = 0.10 / (std(ddof=1) of the 36 raw TSMOM months t-36..t-1 * sqrt(12)).
    Month t itself is NOT in the window (no look-ahead). The first 36 months (1985-01..1987-12) are warm-up only.
  * R_gross,t = (Mkt-RF + RF)_t + w * (TSMOM_s,t - D/12) - F/12,  w = 1.0 (decisional), D = 3 %/yr, F = 0.5 %/yr.
  * Monthly rebalancing cost: 0.10 % * |weight change| (equity weight back to 1, trend notional back to w*k_t,
    after drift); charged on the month whose weights it sets: R_t = (1 + R_gross,t) * (1 - c * turnover_t) - 1.

Reference: R_ref = L * (Mkt-RF) + RF - 1 %/yr * max(L - 1, 0) / 12 (monthly), no rebalancing cost (spec formula);
L >= 0 solved (brentq) so that std(R_ref) = std(R_rule) on the SAME evaluated period.

Sharpe = mean(R - RF) / std(R - RF) * sqrt(12) on monthly returns.

Usage:
  py -3 -I scripts/agents/exp76_stack_trend.py download   -> caches raw files in DATA_DIR (outside git) + meta.json
  py -3 -I scripts/agents/exp76_stack_trend.py run        -> computes everything, writes MD-ready JSON + monthly CSV

Conservative / interpretive choices (spec silent), flagged in the deliverable:
  * the 0.10 % rebalancing cost (spec: "rapporté") is INCLUDED in the decisional rule returns (unfavourable to the
    rule); the reference has no cost (spec formula). A no-cost variant is reported;
  * the initial purchase (month 1 of each built series) pays turnover 1 + w*k_1;
  * the stacking fee F is applied for every w (0.5 / 1.0 / 1.5);
  * Ken French international market factors are in USD with the US 1-month T-bill as RF; the "local" reference is
    that market's Mkt-RF + the same RF; the trend series is the same global AQR series (as the spec states).
"""
from __future__ import annotations

import io
import json
import math
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

DATA_DIR = Path("C:/AAProjet/quant_bot_v1/data/exp76")
REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "docs" / "agents" / "results"
TAG = "Exp-76_2026-10-11"

MPY = 12
TARGET_VOL = 0.10
VOL_WIN = 36
DECOTE = 0.03
DECOTE_ROB = 0.045
STACK_FEE = 0.005
LEV_FEE = 0.01
COST = 0.0010
W_DEC = 1.0
W_ROB = (0.5, 1.5)
N_TRIALS = 76
START = "1988-01"
PRE = ("1988-01", "2012-05")
POST_START = "2012-06"
INTL_START = "1990-07"
INTL_PRE = ("1990-07", "2012-05")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
AQR_URL = "https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/Time-Series-Momentum-Factors-Monthly.xlsx"
KF_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
KF_FILES = {"US": "F-F_Research_Data_Factors_CSV.zip",
            "DevExUS": "Developed_ex_US_3_Factors_CSV.zip",
            "Europe": "Europe_3_Factors_CSV.zip",
            "Japan": "Japan_3_Factors_CSV.zip",
            "Developed": "Developed_3_Factors_CSV.zip"}
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXCAUS"
YAHOO = ["DBMF", "RSST", "SSO", "SPXU.TO"]  # SPXU.TO = Yahoo ticker carrying the former HSU.TO history (HSU.TO: not found on Yahoo 2026-10-11)


# ---------------------------------------------------------------- core (pure)
def vol_scale(raw: pd.Series, target: float = TARGET_VOL, win: int = VOL_WIN) -> pd.Series:
    """k_t = target / (annualised std of raw over months t-win..t-1). NaN for the first `win` months."""
    sd = raw.shift(1).rolling(win, min_periods=win).std(ddof=1) * math.sqrt(MPY)
    return target / sd


def rule_returns(mkt_rf: pd.Series, rf: pd.Series, tsmom_raw: pd.Series, k: pd.Series, w: float = W_DEC,
                 decote: float = DECOTE, fee: float = STACK_FEE, cost: float = COST) -> pd.DataFrame:
    """Monthly stacked returns on the common index where k is defined. Returns DataFrame with gross, turnover, net."""
    idx = k.dropna().index.intersection(mkt_rf.index).intersection(tsmom_raw.index)
    rm = (mkt_rf + rf).loc[idx]
    kk = k.loc[idx]
    gross = rm + w * (kk * tsmom_raw.loc[idx] - decote / MPY) - fee / MPY
    turn = np.empty(len(idx))
    for i in range(len(idx)):
        if i == 0:
            turn[i] = 1.0 + abs(w * kk.iloc[0])
        else:
            g = 1.0 + gross.iloc[i - 1]
            eq_end = (1.0 + rm.iloc[i - 1]) / g
            tr_end = w * kk.iloc[i - 1] / g
            turn[i] = abs(1.0 - eq_end) + abs(w * kk.iloc[i] - tr_end)
    turn = pd.Series(turn, index=idx)
    net = (1.0 + gross) * (1.0 - cost * turn) - 1.0
    return pd.DataFrame({"gross": gross, "turnover": turn, "net": net})


def ref_returns(L: float, mkt_rf: pd.Series, rf: pd.Series, lev_fee: float = LEV_FEE) -> pd.Series:
    return L * mkt_rf + rf - lev_fee * max(L - 1.0, 0.0) / MPY


def ann_vol(r: pd.Series) -> float:
    return float(r.dropna().std(ddof=1) * math.sqrt(MPY))


def solve_L(mkt_rf: pd.Series, rf: pd.Series, target_vol: float, hi: float = 20.0) -> float:
    """Constant L >= 0 such that ann_vol(ref_returns(L)) == target_vol on mkt_rf's index."""
    def f(L):
        return ann_vol(ref_returns(L, mkt_rf, rf)) - target_vol
    if f(0.0) >= 0:
        return 0.0
    return float(brentq(f, 0.0, hi, xtol=1e-12))


def sharpe(r: pd.Series, rf: pd.Series) -> float:
    ex = (r - rf.reindex(r.index)).dropna()
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * math.sqrt(MPY)) if sd > 0 else float("nan")


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return float("nan")
    return float(np.prod(1.0 + r.values) ** (MPY / len(r)) - 1.0)


def max_dd(r: pd.Series) -> float:
    eq = np.concatenate([[1.0], np.cumprod(1.0 + r.dropna().values)])
    return float((eq / np.maximum.accumulate(eq) - 1.0).min())


def yearly(r: pd.Series) -> pd.Series:
    return (1.0 + r).groupby(r.index.year).prod() - 1.0


def deflated_sharpe(r: pd.Series, rf: pd.Series, n_trials: int = N_TRIALS) -> dict:
    """Bailey & Lopez de Prado (2014), monthly SR; V[SR] across trials approximated by 1/(T-1) (as Exp 74/75)."""
    ex = (r - rf.reindex(r.index)).dropna()
    T = len(ex)
    sr = ex.mean() / ex.std(ddof=1)
    s0 = ex.std(ddof=0)
    g3 = float(((ex - ex.mean()) ** 3).mean() / s0 ** 3)
    g4 = float(((ex - ex.mean()) ** 4).mean() / s0 ** 4)
    em = 0.5772156649
    sr0 = math.sqrt(1.0 / (T - 1)) * ((1 - em) * norm.ppf(1 - 1.0 / n_trials) + em * norm.ppf(1 - 1.0 / (n_trials * math.e)))
    den = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2))
    return {"T": T, "sr_ann": float(sr * math.sqrt(MPY)), "sr0_ann": float(sr0 * math.sqrt(MPY)), "skew": g3,
            "kurt": g4, "dsr": float(norm.cdf((sr - sr0) * math.sqrt(T - 1) / den)),
            "psr_vs_0": float(norm.cdf(sr * math.sqrt(T - 1) / den)), "n_trials": n_trials}


def stats(r: pd.Series, rf: pd.Series) -> dict:
    r = r.dropna()
    y = yearly(r)
    return {"start": str(r.index[0]), "end": str(r.index[-1]), "n_months": int(len(r)), "cagr": cagr(r),
            "vol": ann_vol(r), "sharpe": sharpe(r, rf), "maxdd_monthly": max_dd(r),
            "worst_year": float(y.min()), "worst_year_label": int(y.idxmin()),
            "worst_month": float(r.min()), "worst_month_label": str(r.idxmin())}


def sub(s, a, b=None):
    return s.loc[pd.Period(a, "M"):(pd.Period(b, "M") if b else None)]


def compare(rule: pd.Series, mkt_rf: pd.Series, rf: pd.Series, a: str, b: str | None = None) -> dict:
    """Rule vs equal-vol constant-leverage reference on [a, b]; L solved on that period only."""
    rr = sub(rule, a, b).dropna()
    m, f = mkt_rf.loc[rr.index], rf.loc[rr.index]
    L = solve_L(m, f, ann_vol(rr))
    ref = ref_returns(L, m, f)
    s_rule, s_ref = stats(rr, f), stats(ref, f)
    return {"L": L, "rule": s_rule, "ref": s_ref, "sharpe_gap": s_rule["sharpe"] - s_ref["sharpe"],
            "cagr_gap": s_rule["cagr"] - s_ref["cagr"], "_ref": ref}


def verdict(gap_full: float, gap_post: float, gap_w05: float, gap_w15: float, gap_d45: float,
            intl_gaps: dict, cagr_full: float, cagr_post: float, maxdd_full: float) -> dict:
    c1 = gap_full >= 0.10 and gap_post > 0
    c2 = gap_w05 > 0 and gap_w15 > 0 and gap_d45 > 0
    n_pos = sum(int(g > 0) for g in intl_gaps.values())
    n_nonpos = sum(int(g <= 0) for g in intl_gaps.values())
    c3 = n_pos >= 2
    c4 = (cagr_full >= 0.15 or cagr_post >= 0.15) and maxdd_full >= -0.40
    rej_a, rej_b = gap_full <= 0, n_nonpos >= 2
    v = "PASS" if (c1 and c2 and c3 and c4) else ("REJET" if (rej_a or rej_b) else "INCERTAIN")
    return {"verdict": v, "c1_gap_full_ge_010_and_post_gt_0": c1, "c2_robust_w05_w15_decote45": c2,
            "c3_intl_2of3_gt_0": c3, "c4_cagr15_full_or_post_and_maxdd_ge_m40": c4,
            "reject_gap_full_le_0": rej_a, "reject_intl_2of3_le_0": rej_b, "n_intl_gap_pos": n_pos}


def top3_share(rule: pd.Series, ref: pd.Series) -> dict:
    yr = np.log1p(yearly(rule)) - np.log1p(yearly(ref))
    tot = float(yr.sum())
    best = yr.sort_values(ascending=False).head(3)
    return {"total_log_surplus": tot, "top3_years": {str(k): float(v) for k, v in best.items()},
            "top3_share": float(best.sum() / tot) if tot > 0 else float("nan"),
            "n_years": int(len(yr)), "n_years_positive": int((yr > 0).sum()),
            "yearly_log_surplus": {str(k): float(v) for k, v in yr.items()}}


def rolling_10y(rule: pd.Series, mkt_rf: pd.Series, rf: pd.Series, n: int = 120) -> dict:
    out = []
    for i in range(0, len(rule) - n + 1):
        w = rule.iloc[i:i + n]
        c = compare(w, mkt_rf, rf, str(w.index[0]), str(w.index[-1]))
        out.append({"start": str(w.index[0]), "cagr": c["rule"]["cagr"], "ref_cagr": c["ref"]["cagr"],
                    "gap": c["sharpe_gap"], "L": c["L"]})
    cg = np.array([x["cagr"] for x in out])
    rc = np.array([x["ref_cagr"] for x in out])
    g = np.array([x["gap"] for x in out])
    return {"n_windows": len(out), "share_cagr_ge_15": float((cg >= 0.15).mean()),
            "share_cagr_lt_5": float((cg < 0.05).mean()), "ref_share_cagr_ge_15": float((rc >= 0.15).mean()),
            "ref_share_cagr_lt_5": float((rc < 0.05).mean()), "min_cagr": float(cg.min()),
            "median_cagr": float(np.median(cg)), "max_cagr": float(cg.max()),
            "share_gap_pos": float((g > 0).mean()), "min_gap": float(g.min()), "median_gap": float(np.median(g)),
            "max_gap": float(g.max()), "worst_gap_start": out[int(g.argmin())]["start"],
            "january_starts": [x for x in out if x["start"].endswith("-01")]}


# ---------------------------------------------------------------- parsing (untrusted files: data only)
def parse_kf_csv(text: str) -> pd.DataFrame:
    """First monthly block of a Ken French CSV: header line starting with ',Mkt-RF', rows 'YYYYMM,...'.
    Values in percent -> returned as decimals, PeriodIndex monthly."""
    lines = text.splitlines()
    h = next(i for i, ln in enumerate(lines) if ln.replace(" ", "").startswith(",Mkt-RF"))
    cols = [c.strip() for c in lines[h].split(",")[1:]]
    rows = []
    for ln in lines[h + 1:]:
        parts = [p.strip() for p in ln.split(",")]
        if not parts or not re.fullmatch(r"\d{6}", parts[0]):
            break
        rows.append([parts[0]] + [float(p) for p in parts[1:len(cols) + 1]])
    df = pd.DataFrame(rows, columns=["ym"] + cols)
    df.index = pd.PeriodIndex([pd.Period(f"{s[:4]}-{s[4:]}", "M") for s in df.pop("ym")], freq="M")
    df = df / 100.0
    if (df.abs() > 0.9).any().any() or (df <= -0.9999 + 0).any().any():
        raise ValueError("implausible Ken French value (missing-value code?)")
    return df


def parse_aqr_xlsx(path: Path) -> pd.Series:
    raw = pd.read_excel(path, sheet_name="TSMOM Factors", header=None, engine="openpyxl")
    h = next(i for i in range(len(raw)) if str(raw.iloc[i, 1]).strip() == "TSMOM")
    body = raw.iloc[h + 1:, [0, 1]].dropna()
    s = pd.Series(pd.to_numeric(body[1]).values, index=pd.to_datetime(body[0]).dt.to_period("M"), name="TSMOM")
    if s.index.has_duplicates or not s.index.is_monotonic_increasing:
        raise ValueError("AQR index not unique/sorted")
    return s.astype(float)


def kf_from_zip(path: Path) -> pd.DataFrame:
    z = zipfile.ZipFile(path)
    name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    return parse_kf_csv(z.read(name).decode("latin1"))


# ---------------------------------------------------------------- download
def _get(url: str, browser_ua: bool = True) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"} if browser_ua else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def download():
    import yfinance as yf
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    meta = {"downloaded_utc": now, "files": {}}
    b = _get(AQR_URL)
    (DATA_DIR / "aqr_tsmom_monthly.xlsx").write_bytes(b)
    a = parse_aqr_xlsx(DATA_DIR / "aqr_tsmom_monthly.xlsx")
    meta["files"]["AQR_TSMOM"] = {"url": AQR_URL, "file": "aqr_tsmom_monthly.xlsx", "bytes": len(b),
                                  "first": str(a.index[0]), "last": str(a.index[-1]), "downloaded_utc": now}
    for key, fn in KF_FILES.items():
        b = _get(KF_BASE + fn)
        (DATA_DIR / fn).write_bytes(b)
        d = kf_from_zip(DATA_DIR / fn)
        meta["files"][f"KF_{key}"] = {"url": KF_BASE + fn, "file": fn, "bytes": len(b), "first": str(d.index[0]),
                                      "last": str(d.index[-1]), "downloaded_utc": now}
    b = _get(FRED_URL, browser_ua=False)  # FRED resets connections with a browser UA
    (DATA_DIR / "FRED_DEXCAUS.csv").write_bytes(b)
    fx = pd.read_csv(DATA_DIR / "FRED_DEXCAUS.csv")
    meta["files"]["FRED_DEXCAUS"] = {"url": FRED_URL, "file": "FRED_DEXCAUS.csv", "first": str(fx.iloc[0, 0]),
                                     "last": str(fx.iloc[-1, 0]), "downloaded_utc": now}
    for s in YAHOO:
        d = yf.download(s, start="2000-01-01", progress=False, auto_adjust=True)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        d = d[["Close"]].dropna()
        fn = "YH_" + s.replace(".", "_") + ".csv"
        d.to_csv(DATA_DIR / fn)
        meta["files"][f"YH_{s}"] = {"source": f"Yahoo Finance via yfinance {yf.__version__} (auto_adjust=True)",
                                    "file": fn, "first": str(d.index[0].date()), "last": str(d.index[-1].date()),
                                    "rows": int(len(d)), "downloaded_utc": now}
    (DATA_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


# ---------------------------------------------------------------- run
def load_all():
    tsm = parse_aqr_xlsx(DATA_DIR / "aqr_tsmom_monthly.xlsx")
    kf = {k: kf_from_zip(DATA_DIR / fn) for k, fn in KF_FILES.items()}
    fx = pd.read_csv(DATA_DIR / "FRED_DEXCAUS.csv")
    fx.columns = ["date", "cadusd"]
    fx["date"] = pd.to_datetime(fx["date"])
    fx["cadusd"] = pd.to_numeric(fx["cadusd"], errors="coerce")
    fx = fx.dropna().set_index("date")["cadusd"]
    fx_m = fx.groupby(fx.index.to_period("M")).last()
    yh = {}
    for s in YAHOO:
        d = pd.read_csv(DATA_DIR / ("YH_" + s.replace(".", "_") + ".csv"), index_col=0, parse_dates=True)["Close"]
        d = pd.to_numeric(d, errors="coerce").dropna()
        yh[s] = d.groupby(d.index.to_period("M")).last()
    return tsm, kf, fx_m, yh


def strip(d):
    if isinstance(d, dict):
        return {k: strip(v) for k, v in d.items() if not str(k).startswith("_")}
    return d


def run():
    meta = json.loads((DATA_DIR / "meta.json").read_text())
    tsm, kf, fx_m, yh = load_all()
    us = kf["US"]
    end = min(tsm.index[-1], us.index[-1])
    k = vol_scale(tsm)
    rf_us = us["RF"]

    def build(mkt: pd.DataFrame, w=W_DEC, decote=DECOTE, cost=COST, start=START):
        df = rule_returns(mkt["Mkt-RF"], mkt["RF"], tsm, k, w=w, decote=decote, cost=cost)
        return sub(df, start, str(end))

    periods = {"full": (START, str(end)), "pre": PRE, "post": (POST_START, str(end))}
    res = {"meta": meta, "params": {"target_vol": TARGET_VOL, "vol_win": VOL_WIN, "decote": DECOTE,
                                    "decote_rob": DECOTE_ROB, "stack_fee": STACK_FEE, "lev_fee": LEV_FEE,
                                    "cost": COST, "w_dec": W_DEC, "w_rob": W_ROB, "n_trials": N_TRIALS,
                                    "start": START, "end": str(end), "pre": PRE, "post_start": POST_START,
                                    "intl_start": INTL_START}}
    variants = {"w1.0_d3": dict(w=1.0), "w0.5_d3": dict(w=0.5), "w1.5_d3": dict(w=1.5),
                "w1.0_d4.5": dict(w=1.0, decote=DECOTE_ROB), "w1.0_d3_nocost": dict(w=1.0, cost=0.0)}
    usres, built = {}, {}
    for vn, kw in variants.items():
        df = build(us, **kw)
        built[vn] = df
        usres[vn] = {pn: compare(df["net"], us["Mkt-RF"], rf_us, a, z) for pn, (a, z) in periods.items()}
    dec = built["w1.0_d3"]
    r_dec = dec["net"]
    usres["w1.0_d3"]["full"]["rule"]["dsr_n76"] = deflated_sharpe(r_dec, rf_us)
    usres["w1.0_d3"]["full"]["rule"]["mean_turnover_month"] = float(dec["turnover"].iloc[1:].mean())
    usres["w1.0_d3"]["full"]["rule"]["cost_drag_ann"] = float((dec["gross"] - dec["net"]).mean() * MPY)
    mkt1 = sub(us["Mkt-RF"] + us["RF"], START, str(end))
    res["us_equity_x1"] = {pn: stats(sub(mkt1, a, z), rf_us) for pn, (a, z) in periods.items()}
    pocket = sub(k * tsm - DECOTE / MPY, START, str(end))
    res["trend_pocket_excess"] = {
        "net_of_decote3": {pn: {"mean_ann": float(sub(pocket, a, z).mean() * MPY), "vol": ann_vol(sub(pocket, a, z)),
                               "sharpe": float(sub(pocket, a, z).mean() / sub(pocket, a, z).std(ddof=1) * math.sqrt(MPY)),
                               "corr_us_mkt_rf": float(sub(pocket, a, z).corr(sub(us["Mkt-RF"], a, z)))}
                           for pn, (a, z) in periods.items()},
        "k_scale": {"min": float(sub(k, START, str(end)).min()), "median": float(sub(k, START, str(end)).median()),
                    "max": float(sub(k, START, str(end)).max())},
        "raw_tsmom_vol_full": ann_vol(sub(tsm, START, str(end)))}
    # decades (L re-solved per decade)
    dec_bounds = [("1988-01", "1989-12"), ("1990-01", "1999-12"), ("2000-01", "2009-12"), ("2010-01", "2019-12"),
                  ("2020-01", str(end))]
    res["decades"] = {f"{a}..{z}": strip(compare(r_dec, us["Mkt-RF"], rf_us, a, z)) |
                      {"us_x1": stats(sub(mkt1, a, z), rf_us)} for a, z in dec_bounds}
    full = usres["w1.0_d3"]["full"]
    res["top3_share_full"] = top3_share(r_dec, full["_ref"])
    res["rolling_10y"] = rolling_10y(r_dec, us["Mkt-RF"], rf_us)
    res["yearly"] = {str(y): {"rule": float(a), "ref_fullL": float(b), "us_x1": float(c)}
                     for (y, a), b, c in zip(yearly(r_dec).items(), yearly(full["_ref"]).values, yearly(mkt1).values)}
    # international (criterion 3) + Developed (reported)
    intl = {}
    intl_periods = {"full": (INTL_START, str(end)), "pre": INTL_PRE, "post": (POST_START, str(end))}
    for key in ("DevExUS", "Europe", "Japan", "Developed"):
        mk = kf[key]
        df = rule_returns(mk["Mkt-RF"], mk["RF"], tsm, k)
        df = sub(df, INTL_START, str(end))
        intl[key] = {pn: strip(compare(df["net"], mk["Mkt-RF"], mk["RF"], a, z)) for pn, (a, z) in intl_periods.items()}
        intl[key]["local_x1_full"] = stats(sub(mk["Mkt-RF"] + mk["RF"], INTL_START, str(end)), mk["RF"])
    res["intl"] = intl
    intl_gaps = {key: intl[key]["full"]["sharpe_gap"] for key in ("DevExUS", "Europe", "Japan")}
    # CAD
    fxr = fx_m.pct_change()
    cad = {}
    for pn, (a, z) in periods.items():
        rr = sub(r_dec, a, z)
        ref = usres["w1.0_d3"][pn]["_ref"]
        f = fxr.reindex(rr.index)
        rc, fc = (1 + rr) * (1 + f) - 1, (1 + ref) * (1 + f) - 1
        cad[pn] = {"rule": {"cagr": cagr(rc), "vol": ann_vol(rc), "maxdd_monthly": max_dd(rc)},
                   "ref": {"cagr": cagr(fc), "vol": ann_vol(fc), "maxdd_monthly": max_dd(fc)},
                   "fx_missing_months": int(f.isna().sum())}
    res["cad"] = cad
    # real instruments (reported only)
    real = {}
    rr_y = {s: v.pct_change().dropna() for s, v in yh.items()}
    trend_funded = sub(rf_us + k * tsm - DECOTE / MPY, START, str(end))

    def track(name, real_r, synth):
        idx = real_r.index.intersection(synth.dropna().index)
        if len(idx) < 6:
            return {"note": "insufficient overlap", "n_months": int(len(idx))}
        a, b = real_r.loc[idx], synth.loc[idx]
        d = a - b
        return {"start": str(idx[0]), "end": str(idx[-1]), "n_months": int(len(idx)), "cagr_real": cagr(a),
                "cagr_synth": cagr(b), "vol_real": ann_vol(a), "vol_synth": ann_vol(b), "corr": float(a.corr(b)),
                "tracking_error_ann": ann_vol(d), "mean_diff_ann": float(d.mean() * MPY), "name": name}
    real["DBMF_vs_trend_pocket"] = track("DBMF vs RF + k*TSMOM - 3%/12", rr_y["DBMF"], trend_funded)
    real["RSST_vs_rule_w1"] = track("RSST vs rule w=1 (net)", rr_y["RSST"], r_dec)
    syn2 = sub(ref_returns(2.0, us["Mkt-RF"], rf_us), START, str(end))
    real["SSO_vs_synth_x2_usmkt"] = track("SSO vs 2*(Mkt-RF)+RF-1%/yr (CRSP US market, not S&P 500)",
                                          rr_y["SSO"], syn2)
    syn2_cad = (1 + syn2) * (1 + fxr.reindex(syn2.index)) - 1
    real["HSU_SPXU_TO_vs_synth_x2_usmkt_cad"] = track("SPXU.TO ex-HSU (CAD) vs synthetic x2 converted to CAD",
                                                 rr_y["SPXU.TO"], syn2_cad)
    res["real_instruments"] = real

    s = usres
    crit = verdict(s["w1.0_d3"]["full"]["sharpe_gap"], s["w1.0_d3"]["post"]["sharpe_gap"],
                   s["w0.5_d3"]["full"]["sharpe_gap"], s["w1.5_d3"]["full"]["sharpe_gap"],
                   s["w1.0_d4.5"]["full"]["sharpe_gap"], intl_gaps, s["w1.0_d3"]["full"]["rule"]["cagr"],
                   s["w1.0_d3"]["post"]["rule"]["cagr"], s["w1.0_d3"]["full"]["rule"]["maxdd_monthly"])
    crit.update({"gap_full": s["w1.0_d3"]["full"]["sharpe_gap"], "gap_pre": s["w1.0_d3"]["pre"]["sharpe_gap"],
                 "gap_post": s["w1.0_d3"]["post"]["sharpe_gap"], "gap_full_w05": s["w0.5_d3"]["full"]["sharpe_gap"],
                 "gap_full_w15": s["w1.5_d3"]["full"]["sharpe_gap"],
                 "gap_full_decote45": s["w1.0_d4.5"]["full"]["sharpe_gap"], "intl_gaps_full": intl_gaps,
                 "cagr_full": s["w1.0_d3"]["full"]["rule"]["cagr"], "cagr_post": s["w1.0_d3"]["post"]["rule"]["cagr"],
                 "maxdd_full_monthly": s["w1.0_d3"]["full"]["rule"]["maxdd_monthly"]})
    res["us"] = strip(usres)
    res["criteria"] = crit
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{TAG}_criteria.json").write_text(json.dumps(res, indent=2, default=str))
    fxa = fx_m.reindex(r_dec.index)
    monthly = pd.DataFrame({"mkt_rf_us": us["Mkt-RF"].reindex(r_dec.index), "rf": rf_us.reindex(r_dec.index),
                            "tsmom_raw": tsm.reindex(r_dec.index), "k_scale": k.reindex(r_dec.index),
                            "turnover_w1": dec["turnover"], "rule_w1_d3_gross": dec["gross"], "rule_w1_d3": r_dec,
                            "ref_fullL": full["_ref"], "rule_w05_d3": built["w0.5_d3"]["net"],
                            "rule_w15_d3": built["w1.5_d3"]["net"], "rule_w1_d45": built["w1.0_d4.5"]["net"],
                            "cad_per_usd_monthend": fxa})
    monthly.index.name = "month"
    monthly.to_csv(OUT_DIR / f"{TAG}_monthly.csv", float_format="%.8g")
    print(json.dumps(crit, indent=2))


if __name__ == "__main__":
    {"download": download, "run": run}[sys.argv[1]]()
