"""T-076 / Exp 81 -- RRSP/TFSA season: S&P/TSX Composite vs S&P 500 (preregistration
docs/agents/hypotheses/Exp-81.md, commit efc2c9a, frozen).

Subcommands
  download  : raw bytes -> C:/AAProjet/quant_bot_v1/data/exp81/raw/ + meta.json (url, utc date, sha256).
              Nothing is parsed at download time.
  inspect   : prints the STRUCTURE of the raw files only (members, columns, date ranges), no statistic.
  run       : the preregistered analysis; writes <stem>_criteria.json and <stem>_annual.csv in --out-dir.

Downloaded files are untrusted: read with pandas / zipfile only (never extracted, never executed);
run with `py -3 -I`.

Frozen conventions (prereg), and the implementation choices where the prereg is silent (flagged
in the result file):
  * Monthly (decisional) season S(y): close end-Dec y-1 -> close end-Feb y.  E_S = rTSX - rSPX.
    E_R(y) = [rTSX(end-Feb y -> end-Dec y) - rSPX(same)] * 2/10.  D = E_S - E_R.  Years 1957 -> last
    complete year.  One observation per year; Student t = mean / (sd / sqrt(n)).
  * RRSP deadline = 60th calendar day of the year (Mar 1, or Feb 29 in leap years); if the TSX is
    closed that day, the next TSX trading day.
  * (a) daily: close of the last TSX trading day of Dec y-1 -> close of the deadline;
        reference = (deadline close -> last Dec trading day close of y) * 2/10 (frozen factor kept).
  * (b) shifted: close of the FIRST January trading day -> close of the last February trading day
        (removes the turn-of-year day, the strict reading of "excludes the last day of December");
        reference = (last Feb trading day -> last Dec trading day) * 2/10.
  * (c) Ken French country "Mkt" returns in USD, Canada vs US, Jan+Feb vs Mar-Dec * 2/10.
  * UK: U(y) = [rUK(Mar) - rUS(Mar)] - mean over the 11 other months of y of [rUK - rUS] (KF, USD).
  * Portfolio (monthly, local-currency price indices): TSX in Jan and Feb, S&P 500 otherwise.  The
    calendar signal is decided at the close before the last Dec / Feb session and executed at that
    last session's close (t+1), so January is the first TSX month.  0.10 % per switch (sell + buy),
    charged on the first month after each switch (Jan, Mar) -> 0.20 %/yr.
    Reference: 1/6 TSX + 5/6 S&P, rebalanced monthly; drift turnover charged at 0.05 % per unit of
    |dw| (same rate: a full switch is |dw| = 2 -> 0.10 %), then x L constant so that its volatility
    equals the rule's on the same sample, levered part financed at T-bill + 1.8 %/yr (atelier
    engine ref_returns / solve_L, ppy = 12).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import re
import sys
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[2]
DATA = Path("C:/AAProjet/quant_bot_v1/data/exp81")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_spec = importlib.util.spec_from_file_location("atelier_engine", ROOT / "scripts" / "agents" / "atelier" / "engine.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

SPREAD = 0.018            # T-bill + 1.8 %/yr on L - 1 (atelier convention)
SWITCH_COST = 0.001       # per switch (sell + buy), prereg
SIDE_RATE = SWITCH_COST / 2.0   # per unit of traded notional |dw|
N_DSR = 132
N_DSR_ALT = 95
SD_SR_ANN = 0.1116        # cross-trial SD of annual Sharpe, T-074 preregistered value (prereg silent)
TH = {"mean_d": 0.0075, "t_d": 2.0, "uk_t": 1.5, "dsharpe": 0.0, "surplus": 0.004}
PERIODS = {"full": (1957, None), "pre1990": (1957, 1989), "1990_2008": (1990, 2008), "tfsa_2009": (2009, None),
           "1990_end": (1990, None)}

YAHOO = {"^GSPTSE": "close", "^GSPC": "close", "^SP500TR": "close", "XIC.TO": "adj", "ZSP.TO": "adj"}
FRED = ["DEXCAUS", "EXCAUS", "TB3MS", "IR3TIB01CAM156N"]
KF = ["F-F_International_Countries.zip", "F-F_Research_Data_Factors_CSV.zip"]
STATCAN_TABLE = "10100125"


# =================================================================================== calendar
def day60(year: int) -> date:
    """60th calendar day of the year (Mar 1; Feb 29 in leap years)."""
    return date(year, 1, 1) + timedelta(days=59)


def rrsp_deadline(year: int, trading_days: pd.DatetimeIndex) -> pd.Timestamp:
    """Deadline = day 60; if not a trading day (weekend/holiday), the next trading day."""
    d = pd.Timestamp(day60(year))
    nxt = trading_days[trading_days >= d]
    if len(nxt) == 0 or (nxt[0] - d).days > 7:
        raise ValueError(f"no trading day near the RRSP deadline of {year}")
    return nxt[0]


def last_trading_day(year: int, month: int, trading_days: pd.DatetimeIndex) -> pd.Timestamp:
    td = trading_days[(trading_days.year == year) & (trading_days.month == month)]
    if len(td) == 0:
        raise ValueError(f"no trading day in {year}-{month:02d}")
    return td[-1]


def first_trading_day(year: int, month: int, trading_days: pd.DatetimeIndex) -> pd.Timestamp:
    td = trading_days[(trading_days.year == year) & (trading_days.month == month)]
    if len(td) == 0:
        raise ValueError(f"no trading day in {year}-{month:02d}")
    return td[0]


def close_at(s: pd.Series, d: pd.Timestamp, max_stale_days: int = 5) -> float:
    """Last close on or before d (an index may be closed on a day the other is open)."""
    x = s.loc[:d]
    if len(x) == 0 or (d - x.index[-1]).days > max_stale_days:
        raise ValueError(f"no close within {max_stale_days} days before {d.date()}")
    return float(x.iloc[-1])


def month_end_close(daily: pd.Series) -> pd.Series:
    s = daily.dropna()
    return s.groupby(s.index.to_period("M")).last()


# =================================================================================== statistics
def ttest(x) -> dict:
    x = pd.Series(x, dtype=float).dropna()
    n = len(x)
    if n < 2:
        return {"n": n, "mean": float(x.mean()) if n else float("nan"), "sd": float("nan"), "t": float("nan"),
                "p_two_sided": float("nan")}
    sd = float(x.std(ddof=1))
    t = float(x.mean() / (sd / math.sqrt(n))) if sd > 0 else float("nan")
    p = float(2 * student_t.sf(abs(t), n - 1)) if not math.isnan(t) else float("nan")
    return {"n": n, "mean": float(x.mean()), "sd": sd, "t": t, "p_two_sided": p}


def sub(series: pd.Series, a: int | None, b: int | None) -> pd.Series:
    i = series.index
    m = np.ones(len(i), bool)
    if a is not None:
        m &= i >= a
    if b is not None:
        m &= i <= b
    return series[m]


def deflated_sharpe(ex: pd.Series, n_trials: int, sd_sr_ann: float = SD_SR_ANN, ppy: int = 12) -> dict:
    """Bailey & Lopez de Prado (2014), same formula as scripts/agents/atelier/validate.py."""
    ex = ex.dropna()
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


# =================================================================================== season statistics
def _r(s: pd.Series, k0, k1) -> float:
    return float(s.loc[k1] / s.loc[k0] - 1.0)


def monthly_season_table(a_m: pd.Series, b_m: pd.Series, years) -> pd.DataFrame:
    """a_m, b_m: month-end closes indexed by Period('M'). Frozen statistic D(y) = E_S - E_R."""
    rows = []
    P = lambda y, m: pd.Period(year=y, month=m, freq="M")  # noqa: E731
    for y in years:
        es = _r(a_m, P(y - 1, 12), P(y, 2)) - _r(b_m, P(y - 1, 12), P(y, 2))
        er = (_r(a_m, P(y, 2), P(y, 12)) - _r(b_m, P(y, 2), P(y, 12))) * 2.0 / 10.0
        rows.append({"year": y, "E_S": es, "E_R": er, "D": es - er})
    return pd.DataFrame(rows).set_index("year")


def monthly_controls(a_m: pd.Series, b_m: pd.Series, years) -> pd.DataFrame:
    """Reported-only single-window controls (same differencing logic as D, monthly reference
    = compounded spread of the remaining months of y scaled to the window length)."""
    P = lambda y, m: pd.Period(year=y, month=m, freq="M")  # noqa: E731
    sp = lambda k0, k1: _r(a_m, k0, k1) - _r(b_m, k0, k1)  # noqa: E731
    rows = []
    for y in years:
        er1 = sp(P(y, 2), P(y, 12)) / 10.0              # one off-season month (Mar-Dec)
        rows.append({
            "year": y,
            "jan": sp(P(y - 1, 12), P(y, 1)) - er1,
            "feb": sp(P(y, 1), P(y, 2)) - er1,
            "dec": sp(P(y, 11), P(y, 12)) - sp(P(y, 2), P(y, 11)) / 9.0,       # Dec vs Mar-Nov
            "mar_apr": sp(P(y, 2), P(y, 4)) - sp(P(y, 4), P(y, 12)) * 2.0 / 8.0,  # reflux vs May-Dec
        })
    return pd.DataFrame(rows).set_index("year")


def daily_season_table(a_d: pd.Series, b_d: pd.Series, years, variant: str) -> pd.DataFrame:
    """variant 'a': last Dec trading day y-1 -> RRSP deadline; ref deadline -> last Dec day y.
    variant 'b': first Jan trading day -> last Feb trading day; ref last Feb day -> last Dec day y.
    Trading calendar = the TSX series (a_d)."""
    cal = a_d.dropna().index
    rows = []
    for y in years:
        if variant == "a":
            s0, s1 = last_trading_day(y - 1, 12, cal), rrsp_deadline(y, cal)
        elif variant == "b":
            s0, s1 = first_trading_day(y, 1, cal), last_trading_day(y, 2, cal)
        else:
            raise ValueError(variant)
        r1 = last_trading_day(y, 12, cal)
        sp = lambda k0, k1: (close_at(a_d, k1) / close_at(a_d, k0) - 1) - (close_at(b_d, k1) / close_at(b_d, k0) - 1)  # noqa: E731
        es = sp(s0, s1)
        er = sp(s1, r1) * 2.0 / 10.0
        rows.append({"year": y, "start": s0.date().isoformat(), "end": s1.date().isoformat(), "E_S": es, "E_R": er,
                     "D": es - er})
    return pd.DataFrame(rows).set_index("year")


def kf_season_table(ra: pd.Series, rb: pd.Series, years) -> pd.DataFrame:
    """ra, rb: monthly simple returns (decimal) indexed by Period('M'); Jan+Feb vs Mar-Dec * 2/10."""
    rows = []
    for y in years:
        g = lambda r, m0, m1: float(np.prod([1 + r.loc[pd.Period(year=y, month=m, freq="M")] for m in range(m0, m1 + 1)]) - 1)  # noqa: E731
        es = g(ra, 1, 2) - g(rb, 1, 2)
        er = (g(ra, 3, 12) - g(rb, 3, 12)) * 2.0 / 10.0
        rows.append({"year": y, "E_S": es, "E_R": er, "D": es - er})
    return pd.DataFrame(rows).set_index("year")


def uk_table(r_uk: pd.Series, r_us: pd.Series, years) -> pd.DataFrame:
    rows = []
    for y in years:
        d = pd.Series({m: r_uk.loc[pd.Period(year=y, month=m, freq="M")] - r_us.loc[pd.Period(year=y, month=m, freq="M")]
                       for m in range(1, 13)})
        rows.append({"year": y, "mar_spread": float(d[3]), "other_mean": float(d.drop(3).mean()),
                     "U": float(d[3] - d.drop(3).mean())})
    return pd.DataFrame(rows).set_index("year")


# =================================================================================== portfolio
def rule_returns(r_tsx: pd.Series, r_spx: pd.Series, season_months=(1, 2), switch_cost: float = SWITCH_COST) -> pd.Series:
    """Monthly returns (Period index).  Month m return comes from TSX if m is a season month, else S&P.
    The switch executed at the close of the last Dec (Feb) session is charged on the next month
    (Jan, Mar): first month in-season and first month after the season."""
    idx = r_tsx.index
    in_season = pd.Series([p.month in season_months for p in idx], index=idx)
    r = r_tsx.where(in_season, r_spx).astype(float)
    first_in = pd.Series([p.month == season_months[0] for p in idx], index=idx)
    first_out = pd.Series([p.month == season_months[-1] % 12 + 1 for p in idx], index=idx)
    return r - switch_cost * (first_in | first_out).astype(float)


def mix_returns(r_tsx: pd.Series, r_spx: pd.Series, w_tsx: float = 1.0 / 6.0, side_rate: float = SIDE_RATE) -> pd.Series:
    """Constant mix rebalanced at each month end; cost = side_rate * sum |drifted - target|."""
    w = np.array([w_tsx, 1 - w_tsx])
    R = pd.concat([r_tsx, r_spx], axis=1).astype(float)
    rp = R.values @ w
    drifted = (w * (1 + R.values)) / (1 + rp)[:, None]
    turn = np.abs(drifted - w).sum(axis=1)
    return pd.Series(rp - side_rate * turn, index=R.index)


def _ts(s: pd.Series) -> pd.Series:
    out = s.copy()
    out.index = s.index.to_timestamp(how="end").normalize()
    return out


def evaluate(rule: pd.Series, mix: pd.Series, rf: pd.Series) -> dict:
    df = pd.concat([rule.rename("r"), mix.rename("m"), rf.rename("rf")], axis=1).dropna()
    r, m, f = _ts(df["r"]), _ts(df["m"]), _ts(df["rf"])
    s = E.stats(r, f, 12)
    L = E.solve_L(s["vol"], m, f, SPREAD, 12)
    ref = E.ref_returns(L, m, f, SPREAD, 12)
    sr = E.stats(ref, f, 12)
    s1 = E.stats(m, f, 12)
    return {"start": str(df.index[0]), "end": str(df.index[-1]), "n_months": len(df),
            "rule": s, "L_ref": L, "ref": sr, "mix_unlevered": s1,
            "dsharpe": s["sharpe"] - sr["sharpe"], "surplus_cagr": s["cagr"] - sr["cagr"]}


# =================================================================================== verdict
def verdict(full: dict, pre: dict, post: dict, uk: dict, port: dict, rob: dict) -> dict:
    c1 = full["mean"] >= TH["mean_d"] and full["t"] >= TH["t_d"]
    c2 = pre["mean"] > 0 and post["mean"] > 0
    c3 = uk["mean"] > 0 and uk["t"] >= TH["uk_t"]
    c4 = port["dsharpe"] > TH["dsharpe"] and port["surplus_cagr"] >= TH["surplus"]
    c5 = all(v["mean"] > 0 for v in rob.values())
    reject = full["mean"] <= 0 or uk["mean"] <= 0
    out = "PASS" if (c1 and c2 and c3 and c4 and c5) else ("REJET" if reject else "INCERTAIN")
    return {"c1_mean_t": bool(c1), "c2_same_sign": bool(c2), "c3_uk": bool(c3), "c4_portfolio": bool(c4),
            "c5_robustness": bool(c5), "c5_detail": {k: bool(v["mean"] > 0) for k, v in rob.items()},
            "reject_trigger": bool(reject), "verdict": out}


# =================================================================================== parsers (untrusted files)
def parse_statcan_zip(path: Path) -> pd.Series:
    """S&P/TSX Composite month-end close from the StatCan full-table zip (10100125.csv)."""
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.endswith(".csv") and "MetaData" not in n]
        if len(name) != 1:
            raise ValueError(f"unexpected members {z.namelist()}")
        df = pd.read_csv(io.BytesIO(z.read(name[0])), dtype=str, encoding="utf-8-sig")
    lab = [c for c in df.columns if c not in ("REF_DATE", "GEO", "DGUID", "UOM", "UOM_ID", "SCALAR_FACTOR",
                                              "SCALAR_ID", "VECTOR", "COORDINATE", "VALUE", "STATUS", "SYMBOL",
                                              "TERMINATED", "DECIMALS")]
    hits = set()
    for c in lab:
        v = df[c].dropna().unique()
        hits |= {(c, x) for x in v if re.search(r"composite", x, re.I) and re.search(r"close", x, re.I)}
    if len(hits) != 1:
        raise ValueError(f"composite close series not unique: {sorted(hits)}")
    col, val = hits.pop()
    s = df[df[col] == val]
    out = pd.Series(pd.to_numeric(s["VALUE"], errors="coerce").values,
                    index=pd.PeriodIndex(s["REF_DATE"], freq="M")).dropna().sort_index()
    if out.index.duplicated().any():
        raise ValueError("duplicated months in StatCan series")
    out.attrs["series"] = val
    return out


def splice_monthly(primary: pd.Series, extension: pd.Series) -> pd.Series:
    """Primary month-end levels up to their last month, then chained with the extension's month-end
    returns after it (levels rescaled at the junction month)."""
    j = primary.index[-1]
    if j not in extension.index:
        raise ValueError(f"junction month {j} missing from extension")
    ext = extension.loc[extension.index > j] * (primary.loc[j] / extension.loc[j])
    out = pd.concat([primary, ext])
    out.attrs.update(primary.attrs)
    out.attrs["junction"] = str(j)
    return out


def parse_yahoo_csv(path: Path, field: str) -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    col = "Adj Close" if field == "adj" else "Close"
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    s = s[s > 0]
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def parse_fred_csv(path: Path) -> pd.Series:
    df = pd.read_csv(path)
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(df.iloc[:, 0]))
    return s.dropna()


def kf_blocks(text: str) -> list[tuple[str, pd.DataFrame]]:
    """Generic Ken French CSV splitter: each block = header line (first field empty) followed by
    rows whose first field is YYYYMM.  Returns (title text preceding the header, DataFrame in %)."""
    lines = text.splitlines()
    out, i, title = [], 0, []
    while i < len(lines):
        ln = lines[i]
        f = [x.strip() for x in ln.split(",")]
        nxt = lines[i + 1].split(",")[0].strip() if i + 1 < len(lines) else ""
        if len(f) > 1 and f[0] == "" and re.fullmatch(r"\d{6}", nxt):
            cols = f[1:]
            rows, j = [], i + 1
            while j < len(lines) and re.fullmatch(r"\d{6}", lines[j].split(",")[0].strip()):
                p = [x.strip() for x in lines[j].split(",")]
                rows.append([p[0]] + p[1:len(cols) + 1])
                j += 1
            df = pd.DataFrame([r[1:] for r in rows], columns=cols,
                              index=pd.PeriodIndex([f"{r[0][:4]}-{r[0][4:]}" for r in rows], freq="M"))
            df = df.apply(pd.to_numeric, errors="coerce").mask(lambda x: x <= -99.99)
            out.append((" ".join(t for t in title if t).strip(), df))
            title, i = [], j
            continue
        if ln.strip():
            title.append(ln.strip().strip(","))
        i += 1
    return out


def kf_zip_texts(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n).decode("latin-1") for n in z.namelist() if n.lower().endswith((".csv", ".txt", ".dat"))}


def kf_dat_market(text: str, must=("Dollar", "Not Reqd")) -> pd.Series:
    """Whitespace-separated KF country .Dat file: monthly block whose title contains all of `must`
    (default: 'Value-Weight Dollar Returns  All 4 Data Items Not Reqd' = all firms with B/M, USD);
    returns its first column 'Mkt' (decimal).  Annual blocks (4-digit dates) are ignored."""
    lines = text.splitlines()
    i, title, found = 0, "", []
    while i < len(lines):
        tok = lines[i].split()
        if tok and tok[0] == "Mkt" and i + 1 < len(lines) and re.fullmatch(r"\d{6}", (lines[i + 1].split() or [""])[0]):
            rows, j = [], i + 1
            while j < len(lines) and lines[j].split() and re.fullmatch(r"\d{6}", lines[j].split()[0]):
                rows.append(lines[j].split()[:2])
                j += 1
            if all(k in title for k in must):
                found.append(pd.Series([float(r[1]) for r in rows],
                                       index=pd.PeriodIndex([f"{r[0][:4]}-{r[0][4:]}" for r in rows], freq="M")))
            i = j
            continue
        if not lines[i].strip():
            title = ""
        elif not re.fullmatch(r"\d{4,6}", (tok or [""])[0]) and "--" not in lines[i]:
            title += " " + lines[i].strip()
        i += 1
    if len(found) != 1:
        raise ValueError(f"expected one monthly block with {must}, found {len(found)}")
    out = found[0].mask(found[0] <= -99.99) / 100.0
    return out.dropna()


def kf_country_market(path: Path, country: str) -> pd.Series:
    """Monthly 'Mkt' return (decimal, USD) of `country` from F-F_International_Countries.zip.
    Selection: members whose name contains the country; first monthly block having a 'Mkt' column
    (blocks of annual data are excluded by the YYYYMM index)."""
    texts = kf_zip_texts(path)
    cand = [n for n in texts if Path(n).stem.lower() == country.lower()]
    if len(cand) != 1:
        raise ValueError(f"{country}: members {cand}")
    if cand[0].lower().endswith(".dat"):
        return kf_dat_market(texts[cand[0]])
    for title, df in kf_blocks(texts[cand[0]]):
        if "Mkt" in df.columns:
            return (df["Mkt"] / 100.0).dropna()
    raise ValueError(f"{country}: no Mkt block")


def kf_us_market_from_factors(path: Path) -> pd.Series:
    texts = kf_zip_texts(path)
    (name, text), = texts.items()
    title, df = kf_blocks(text)[0]
    return ((df["Mkt-RF"] + df["RF"]) / 100.0).dropna()


# =================================================================================== download / inspect
def _get(url: str, ua: bool = True) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA} if ua else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _save(raw: Path, name: str, data: bytes, src: str, meta: dict):
    (raw / name).write_bytes(data)
    meta[name] = {"source": src, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "downloaded_utc": datetime.now(timezone.utc).isoformat()}
    print("saved", name, len(data))


def ycsv_name(t: str) -> str:
    return "YH_" + t.replace("^", "IDX_").replace(".", "_") + ".csv"


def download(raw: Path):
    raw.mkdir(parents=True, exist_ok=True)
    mp = raw.parent / "meta.json"
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    try:
        api = f"https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{STATCAN_TABLE}/en"
        j = json.loads(_get(api).decode("utf-8"))
        url = j["object"]
        if not re.fullmatch(r"https://www150\.statcan\.gc\.ca/[\w/\-.]+\.zip", url):
            raise ValueError(f"unexpected StatCan url {url!r}")
        _save(raw, f"statcan_{STATCAN_TABLE}.zip", _get(url), f"{api} -> {url}", meta)
    except Exception as e:  # noqa: BLE001
        print("StatCan FAIL", e)
    for sid in FRED:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        try:
            _save(raw, f"FRED_{sid}.csv", _get(url, ua=False), url, meta)
        except Exception as e:  # noqa: BLE001
            print("FRED FAIL", sid, e)
        time.sleep(0.5)
    base = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    for fn in KF:
        try:
            _save(raw, fn, _get(base + fn), base + fn, meta)
        except Exception as e:  # noqa: BLE001
            print("KF FAIL", fn, e)
    import yfinance as yf
    for t in YAHOO:
        try:
            df = yf.download(t, start="1927-01-01", auto_adjust=False, progress=False, actions=False)
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(0)
            data = df[["Close", "Adj Close"]].rename_axis("Date").to_csv().encode()
            _save(raw, ycsv_name(t), data, f"yfinance {yf.__version__} {t} start=1927-01-01 auto_adjust=False", meta)
        except Exception as e:  # noqa: BLE001
            print("Yahoo FAIL", t, e)
    mp.write_text(json.dumps(meta, indent=1))


def inspect(raw: Path):
    """Structure only (no statistic of returns)."""
    for p in sorted(raw.iterdir()):
        print("==", p.name, p.stat().st_size)
        if p.name == "F-F_International_Countries.zip":
            for n, txt in kf_zip_texts(p).items():
                if Path(n).stem in ("UK", "Canada"):
                    x = kf_dat_market(txt)
                    print("  member", n, "Mkt monthly", str(x.index[0]), str(x.index[-1]), len(x))
        elif p.suffix == ".zip" and p.name.startswith("F-F"):
            for n, txt in kf_zip_texts(p).items():
                bl = kf_blocks(txt)
                print("  member", n, "blocks", [(t[:60], list(df.columns)[:8], str(df.index[0]), str(df.index[-1])) for t, df in bl[:3]])
        elif p.name.startswith("statcan"):
            with zipfile.ZipFile(p) as z:
                print("  members", z.namelist())
                n = [x for x in z.namelist() if x.endswith(".csv") and "MetaData" not in x][0]
                df = pd.read_csv(io.BytesIO(z.read(n)), dtype=str, encoding="utf-8-sig")
            print("  columns", list(df.columns))
            for c in df.columns:
                if df[c].nunique() < 60 and c not in ("VALUE",):
                    print("   ", c, sorted(df[c].dropna().unique())[:40])
            print("  REF_DATE", df["REF_DATE"].min(), df["REF_DATE"].max())
        elif p.suffix == ".csv":
            df = pd.read_csv(p, index_col=0)
            print("  cols", list(df.columns), "rows", len(df), "from", df.index[0], "to", df.index[-1])


# =================================================================================== run
def load_all(raw: Path) -> dict:
    d = {}
    d["tsx_m_statcan"] = parse_statcan_zip(raw / f"statcan_{STATCAN_TABLE}.zip")
    for t, f in YAHOO.items():
        d[t] = parse_yahoo_csv(raw / ycsv_name(t), f)
    for sid in FRED:
        d[sid] = parse_fred_csv(raw / f"FRED_{sid}.csv")
    kfz = raw / "F-F_International_Countries.zip"
    d["kf_uk"] = kf_country_market(kfz, "UK")
    d["kf_ca"] = kf_country_market(kfz, "Canada")
    try:
        d["kf_us"] = kf_country_market(kfz, "US")
        d["kf_us_src"] = "F-F_International_Countries.zip (US)"
    except ValueError:
        d["kf_us"] = kf_us_market_from_factors(raw / "F-F_Research_Data_Factors_CSV.zip")
        d["kf_us_src"] = "F-F_Research_Data_Factors (Mkt-RF + RF): US absent from the country file"
    return d


def _stats_by_period(D: pd.Series) -> dict:
    return {k: {**ttest(sub(D, a, b)), "years": [int(sub(D, a, b).index.min()), int(sub(D, a, b).index.max())]}
            for k, (a, b) in PERIODS.items() if len(sub(D, a, b))}


def run(raw: Path, out_dir: Path, stem: str):
    d = load_all(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    anomalies = ["StatCan 10-10-0125-01 is a terminated table (last month 2023-09): TSX month-ends after it come from "
                 "Yahoo ^GSPTSE (chained returns)"]
    if "Factors" in d["kf_us_src"]:
        anomalies.append("Ken French country file has no US member: US = F-F_Research_Data_Factors Mkt-RF + RF (CRSP VW, USD)")
    ytsx_m = month_end_close(d["^GSPTSE"])
    tsx_m = splice_monthly(d["tsx_m_statcan"], ytsx_m)
    if tsx_m.attrs["junction"] != "2023-09":
        anomalies.append(f"StatCan junction month {tsx_m.attrs['junction']} (expected 2023-09)")
    spx_m = month_end_close(d["^GSPC"])
    last_full = min(tsx_m.index[-1], spx_m.index[-1], pd.Period("2026-09", "M"))
    last_year = last_full.year if last_full.month == 12 else last_full.year - 1
    years = list(range(1957, last_year + 1))

    # data check: StatCan vs Yahoo month-end TSX on the overlap (reported only)
    ov = pd.concat([d["tsx_m_statcan"], ytsx_m], axis=1, keys=["sc", "yh"]).dropna()
    rel = (ov["yh"] / ov["sc"] - 1).abs()
    check = {"overlap": [str(ov.index[0]), str(ov.index[-1])], "n": len(ov), "max_rel_diff": float(rel.max()),
             "n_over_0.5pct": int((rel > 0.005).sum()), "worst": str(rel.idxmax())}

    main = monthly_season_table(tsx_m, spx_m, years)
    D = main["D"]
    by_p = _stats_by_period(D)

    # UK supplementary prediction
    uk_years_all = [y for y in range(1975, last_year + 1)]
    uk = uk_table(d["kf_uk"], d["kf_us"], uk_years_all)
    uk_post, uk_pre = ttest(sub(uk["U"], 1987, None)), ttest(sub(uk["U"], 1975, 1986))

    # robustness
    cal = d["^GSPTSE"].index
    ydaily = [y for y in years if cal[0] <= pd.Timestamp(f"{y - 1}-12-01")]
    da = daily_season_table(d["^GSPTSE"], d["^GSPC"], ydaily, "a")
    db = daily_season_table(d["^GSPTSE"], d["^GSPC"], ydaily, "b")
    kf_years = [y for y in range(1975, last_year + 1)
                if all(pd.Period(year=y, month=mm, freq="M") in d["kf_ca"].index for mm in range(1, 13))]
    if kf_years[0] != 1975:
        anomalies.append(f"Ken French Canada starts in {d['kf_ca'].index[0]}: control (c) covers {kf_years[0]}-{kf_years[-1]}")
    dc = kf_season_table(d["kf_ca"], d["kf_us"], kf_years)
    rob = {"a_daily_deadline": ttest(da["D"]), "b_shifted_jan_feb": ttest(db["D"]), "c_kf_ca_us_usd": ttest(dc["D"])}

    # portfolio (local currency, price indices), months 1957-01 .. last_year-12
    r_tsx = tsx_m.pct_change().loc[pd.Period(f"{years[0]}-01", "M"):pd.Period(f"{last_year}-12", "M")]
    r_spx = spx_m.pct_change().reindex(r_tsx.index)
    rf_m = (d["TB3MS"] / 100 / 12)
    rf_m.index = rf_m.index.to_period("M")
    rf_m = rf_m.reindex(r_tsx.index)
    rule = rule_returns(r_tsx, r_spx)
    mix = mix_returns(r_tsx, r_spx)
    port = evaluate(rule, mix, rf_m)
    port_sub = {k: evaluate(sub_months(rule, a, b), sub_months(mix, a, b), sub_months(rf_m, a, b))
                for k, (a, b) in PERIODS.items() if k != "full"}
    ex = (rule - rf_m).dropna()
    dsr = {"N132": deflated_sharpe(ex, N_DSR), "N95": deflated_sharpe(ex, N_DSR_ALT)}

    crit = verdict(by_p["full"], by_p["pre1990"], by_p["1990_end"], uk_post, port, rob)

    # ---------------- reported without effect
    ctl = monthly_controls(tsx_m, spx_m, years)
    decades = {f"{(y // 10) * 10}s": ttest(g) for y, g in D.groupby((D.index // 10) * 10)}
    top3 = {"top3_years": [int(x) for x in D.nlargest(3).index], "top3_sum": float(D.nlargest(3).sum()),
            "total_sum": float(D.sum()), "share": float(D.nlargest(3).sum() / D.sum()) if D.sum() > 0 else None}
    controls_rep = {c: _stats_by_period(ctl[c]) for c in ctl.columns}

    # CAD version: S&P 500 converted with DEXCAUS (daily, CAD per USD) at month end, 1971 ->
    fx_m = month_end_close(d["DEXCAUS"])
    spx_cad_m = (spx_m * fx_m).dropna()
    ycad = [y for y in years if pd.Period(f"{y - 1}-12", "M") in spx_cad_m.index]
    cad_tab = monthly_season_table(tsx_m, spx_cad_m, ycad)
    r_spx_cad = spx_cad_m.pct_change().reindex(r_tsx.index)
    rf_ca = d["IR3TIB01CAM156N"] / 100 / 12
    rf_ca.index = rf_ca.index.to_period("M")
    rf_ca = rf_ca.reindex(r_tsx.index)
    msk = r_spx_cad.notna() & rf_ca.notna()
    cad_port = evaluate(rule_returns(r_tsx[msk], r_spx_cad[msk]), mix_returns(r_tsx[msk], r_spx_cad[msk]), rf_ca[msk])

    # ETF version (adjusted closes, CAD): XIC.TO vs ZSP.TO since ZSP's first full December
    etf = {}
    xic_m, zsp_m = month_end_close(d["XIC.TO"]), month_end_close(d["ZSP.TO"])
    yetf = [y for y in years if pd.Period(f"{y - 1}-12", "M") in zsp_m.index and pd.Period(f"{y - 1}-11", "M") in zsp_m.index]
    if yetf:
        etf_tab = monthly_season_table(xic_m, zsp_m, yetf)
        rx, rz = xic_m.pct_change(), zsp_m.pct_change()
        idx = pd.period_range(f"{yetf[0]}-01", f"{last_year}-12", freq="M")
        rfc = d["IR3TIB01CAM156N"] / 100 / 12
        rfc.index = rfc.index.to_period("M")
        rx, rz, rfc = rx.reindex(idx), rz.reindex(idx), rfc.reindex(idx)
        m2 = rx.notna() & rz.notna() & rfc.notna()
        etf = {"years": [yetf[0], yetf[-1]], "D": ttest(etf_tab["D"]),
               "portfolio": evaluate(rule_returns(rx[m2], rz[m2]), mix_returns(rx[m2], rz[m2]), rfc[m2])}
    else:
        anomalies.append("ETF version: not enough ZSP.TO history")

    # TR version: XIC.TO adjusted (TSX TR proxy) vs ^SP500TR, both local currency
    tr = {}
    sptr_m = month_end_close(d["^SP500TR"])
    ytr = [y for y in years if pd.Period(f"{y - 1}-11", "M") in xic_m.index and pd.Period(f"{y - 1}-12", "M") in sptr_m.index]
    if ytr:
        tr = {"years": [ytr[0], ytr[-1]], "D": ttest(monthly_season_table(xic_m, sptr_m, ytr)["D"]),
              "note": "TSX TR proxy = XIC.TO adjusted close (no S&P/TSX TR index found on Yahoo)"}

    annual = main.rename(columns=lambda c: f"m_{c}")
    annual = annual.join(da[["D"]].rename(columns={"D": "a_daily_D"})).join(db[["D"]].rename(columns={"D": "b_shift_D"}))
    annual = annual.join(dc[["D"]].rename(columns={"D": "c_kf_D"})).join(uk[["U"]].rename(columns={"U": "uk_U"}))
    annual = annual.join(ctl).join(cad_tab[["D"]].rename(columns={"D": "cad_D"}))
    annual = annual.join(da[["start", "end"]].rename(columns={"start": "a_start", "end": "a_deadline"}))
    annual.to_csv(out_dir / f"{stem}_annual.csv", float_format="%.6f")

    res = {
        "exp": "Exp 81", "task": "T-076", "prereg": "docs/agents/hypotheses/Exp-81.md @ efc2c9a",
        "run_utc": datetime.now(timezone.utc).isoformat(), "years": [years[0], years[-1]],
        "thresholds": TH, "statcan_series": tsx_m.attrs.get("series"), "statcan_vs_yahoo_tsx": check,
        "D_by_period": by_p, "uk": {"post_1987": uk_post, "pre_1975_1986": uk_pre, "us_source": d["kf_us_src"]},
        "robustness": rob, "robustness_years": {"a_b": [ydaily[0], ydaily[-1]], "c": [kf_years[0], kf_years[-1]]},
        "portfolio_full": port, "portfolio_subperiods": port_sub, "dsr": dsr,
        "criteria": crit,
        "reported": {"decades": decades, "top3": top3, "single_window_controls": controls_rep,
                     "cad_version": {"years": [ycad[0], ycad[-1]], "D": ttest(cad_tab["D"]), "portfolio": cad_port},
                     "etf_version": etf, "tr_version": tr,
                     "ific_correlation": "NOT DONE: IFIC monthly net sales exist only as press releases (no machine-readable series); manual entry out of T-076 scope"},
        "conventions": {"switch_cost": SWITCH_COST, "side_rate_mix": SIDE_RATE, "spread": SPREAD, "rf_local": "FRED TB3MS",
                        "rf_cad": "FRED IR3TIB01CAM156N", "fx": "FRED DEXCAUS month-end (EXCAUS is a monthly average)",
                        "sd_sr_ann_dsr": SD_SR_ANN, "fill": "monthly close-to-close, switch at the close of the last Dec/Feb session (t+1 on a calendar signal)",
                        "category": "en échantillon (historique), aucun forward"},
        "anomalies": anomalies,
    }
    (out_dir / f"{stem}_criteria.json").write_text(json.dumps(res, indent=1, default=_json_default), encoding="utf-8")
    print(json.dumps({"D_full": by_p["full"], "uk_post": uk_post, "rob": rob, "dsharpe": port["dsharpe"],
                      "surplus": port["surplus_cagr"], "criteria": crit}, indent=1, default=_json_default))


def sub_months(s: pd.Series, a: int | None, b: int | None) -> pd.Series:
    y = np.array([p.year for p in s.index])
    m = np.ones(len(s), bool)
    if a is not None:
        m &= y >= a
    if b is not None:
        m &= y <= b
    return s[m]


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["download", "inspect", "run"])
    ap.add_argument("--raw", default=str(DATA / "raw"))
    ap.add_argument("--out-dir", default=str(ROOT / "docs" / "agents" / "results"))
    ap.add_argument("--stem", default="Exp-81_2026-10-12")
    a = ap.parse_args(argv)
    raw = Path(a.raw)
    if a.cmd == "download":
        download(raw)
    elif a.cmd == "inspect":
        inspect(raw)
    else:
        run(raw, Path(a.out_dir), a.stem)


if __name__ == "__main__":
    main()
