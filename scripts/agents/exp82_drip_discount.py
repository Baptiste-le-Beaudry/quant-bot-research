"""Exp 82 (T-077) -- treasury DRIP discount: underperformance in the pricing window, recovery after.

Preregistration: docs/agents/hypotheses/Exp-82.md (frozen at commit 12cee11).  Event table (step 0, committed
before any price was loaded): docs/agents/results/Exp-82_events.csv.

Measures (frozen, see prereg):
  * P = payment date, rolled to the next trading day if it is not one.
  * Window A = trading days P-5..P-1 (Canada: every circular read says 5 trading days before the payment date;
    Australia: the DRP pricing period printed in the ASX notice).  Window B = P..P+4.
  * Abnormal return: banks -> stock minus the equal-weight mean of the other big Canadian banks that have *no
    active discount* that day (^GSPTSE when none); other issuers -> stock minus ^GSPTSE.  A bank has an active
    discount on day d when its next payment date on or after d is a discount event of the table; a bank whose
    next payment is undocumented is left out of the benchmark (conservative: unknown is not "no discount").
  * CAR_A, CAR_B = sums of abnormal returns.  DiD = mean(discount) - mean(no discount), on the issuers that have
    both states; standard errors clustered by payment date (CR1).
  * Abnormal volume (extra prediction): mean over window A of log(volume / median volume of the 20 trading days
    before window A).
  * Trading rule: hold the equal-weight basket of the 6 big banks; for each discount event switch the basket
    into the stock at the close of P-1 and back at the close of P+4 (returns of P..P+4); 0.20 % per event
    (charged 0.10 % on entry day, 0.10 % on exit day, times the fraction of the portfolio switched).
    Reference: the same basket x constant L at the rule's volatility, T-bill + 1.8 %/yr on L-1.
  * Verdict exactly as preregistered; DSR with N = 133 and 96 (decision), 95 and 132 (reported).

Conservative choices where the prereg is silent are listed in CONSERVATIVE below and in the report.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
DATA = Path("C:/AAProjet/quant_bot_v1/data/exp82")
EVENTS = ROOT / "docs" / "agents" / "results" / "Exp-82_events.csv"

_spec = importlib.util.spec_from_file_location("atelier_engine", ROOT / "scripts" / "agents" / "atelier" / "engine.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

CA_BANKS = ["RY.TO", "TD.TO", "BMO.TO", "BNS.TO", "CM.TO", "NA.TO"]
AU_BANKS = ["NAB.AX", "ANZ.AX", "WBC.AX", "CBA.AX"]
CA_INDEX = "^GSPTSE"
AU_INDEX = "^AXJO"
COST_EVENT = 0.002          # 0.20 % per event (4 orders x 0.05 %), prereg
COST_AVOID = 0.001          # 2 orders x 0.05 % for the "avoid the window" variant (reported only)
SPREAD = 0.018              # financing spread over T-bill on L-1 (atelier convention)
N_DSR = (133, 96)           # decision (orchestrator arbitration)
N_DSR_REPORTED = (95, 132)  # prereg "rapporté sans effet"
SD_SR_ANN = 0.1116          # cross-trial SD of annual Sharpe, same constant as Exp 81 (T-074 value)
TH = {"did_a": -0.0020, "t_a": -2.0, "did_b": 0.0015, "t_b": 1.5, "t_vol": 2.0}
EPISODE_C = ("2022-01-01", "2024-12-31")
MIN_EVENTS = 40
MIN_AU = 20
FRED_RF = "IR3TIB01CAM156N"   # Canada 3-month interbank rate, monthly, % per year
CONSERVATIVE = [
    "Evenements au statut non documente exclus (inconnu != sans rabais).",
    "Banque au statut inconnu exclue du panier de reference du jour.",
    "Fenetre A = P-5..P-1 pour le Canada (circulaires TD et BCE lues ; autres emetteurs : defaut du preenregistrement).",
    "Si plusieurs evenements se chevauchent, le panier est reparti a parts egales entre les actions concernees.",
    "Cout 0,20 % par evenement meme si l'action fait deja partie du panier.",
    "Critere 4(e) Australie exige seulement si au moins 20 evenements australiens avec rabais (sinon rapporte).",
]


# =================================================================================== calendar helpers
def roll_forward(d: pd.Timestamp, cal: pd.DatetimeIndex) -> int | None:
    """Index in cal of the first trading day >= d (None if beyond the calendar)."""
    i = int(cal.searchsorted(pd.Timestamp(d)))
    return i if i < len(cal) else None


def window_idx(p_idx: int, a: int, b: int, n: int) -> list[int] | None:
    lo, hi = p_idx + a, p_idx + b
    if lo < 0 or hi >= n:
        return None
    return list(range(lo, hi + 1))


# =================================================================================== events
def load_events(path: Path) -> pd.DataFrame:
    ev = pd.read_csv(path, dtype=str, keep_default_na=False)
    ev["pay_date"] = pd.to_datetime(ev["pay_date"])
    for c in ("window_a_start", "window_a_end", "record_date"):
        if c not in ev.columns:
            ev[c] = ""
        ev[c] = pd.to_datetime(ev[c].replace("", None))
    if "souscripteur" not in ev.columns:
        ev["souscripteur"] = ""
    ev["rabais_pct"] = pd.to_numeric(ev["rabais_pct"].replace("", None), errors="coerce")
    ev["usable"] = ((ev["statut_doc"] != "non_documente") & ev["rabais_pct"].notna()
                    & (ev["souscripteur"] != "oui"))
    ev["D"] = (ev["rabais_pct"] > 0).astype(int)
    return ev.sort_values(["country", "ticker", "pay_date"]).reset_index(drop=True)


def active_discount_table(ev: pd.DataFrame, tickers: list[str], cal: pd.DatetimeIndex) -> pd.DataFrame:
    """For each day of cal and each bank: 1 = active discount, 0 = documented no discount, NaN = unknown.
    Active on day d = the bank's next payment (rolled) on or after d is a discount event."""
    out = pd.DataFrame(np.nan, index=cal, columns=tickers)
    for t in tickers:
        e = ev[ev["ticker"] == t].copy()
        if e.empty:
            continue
        e["p_idx"] = [roll_forward(p, cal) for p in e["pay_date"]]
        e = e.dropna(subset=["p_idx"]).sort_values("p_idx")
        prev = -1
        for _, row in e.iterrows():
            pi = int(row["p_idx"])
            val = np.nan if not row["usable"] else float(row["D"])
            # days (prev, pi] have this event as "next payment"
            out.iloc[prev + 1: pi + 1, out.columns.get_loc(t)] = val
            prev = pi
    return out


def bank_benchmark(rets: pd.DataFrame, active: pd.DataFrame, index_ret: pd.Series, own: str) -> pd.Series:
    others = [c for c in active.columns if c != own and c in rets.columns]
    ok = (active[others] == 0)
    r = rets[others].where(ok)
    bench = r.mean(axis=1, skipna=True)
    n = r.notna().sum(axis=1)
    bench = bench.where(n > 0, index_ret)
    return bench


# =================================================================================== statistics
def cluster_did(y: np.ndarray, d: np.ndarray, g: np.ndarray) -> dict:
    """OLS y = a + b d with CR1 cluster-robust SE (clusters g).  Returns b (DiD), se, t, n, clusters."""
    y = np.asarray(y, float)
    d = np.asarray(d, float)
    m = np.isfinite(y)
    y, d, g = y[m], d[m], np.asarray(g)[m]
    n = len(y)
    n1 = int(d.sum())
    out = {"n": n, "n_discount": n1, "n_none": n - n1, "mean_discount": float(y[d == 1].mean()) if n1 else float("nan"),
           "mean_none": float(y[d == 0].mean()) if n - n1 else float("nan")}
    if n1 == 0 or n1 == n:
        out.update({"did": float("nan"), "se": float("nan"), "t": float("nan"), "clusters": 0})
        return out
    X = np.column_stack([np.ones(n), d])
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    u = y - X @ beta
    groups = pd.unique(g)
    G = len(groups)
    meat = np.zeros((2, 2))
    for gg in groups:
        idx = g == gg
        s = X[idx].T @ u[idx]
        meat += np.outer(s, s)
    k = 2
    c = (G / (G - 1)) * ((n - 1) / (n - k)) if G > 1 else float("nan")
    V = c * XtX_inv @ meat @ XtX_inv
    se = float(math.sqrt(V[1, 1])) if V[1, 1] > 0 else float("nan")
    out.update({"did": float(beta[1]), "se": se, "t": float(beta[1] / se) if se and se > 0 else float("nan"),
                "clusters": G})
    return out


def deflated_sharpe(ex: pd.Series, n_trials: int, sd_sr_ann: float = SD_SR_ANN, ppy: int = 252) -> dict:
    """Bailey & Lopez de Prado (2014); same formula as Exp 81 / atelier validate.py."""
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


# =================================================================================== event measures
def event_measures(ev: pd.DataFrame, px: dict, cal: pd.DatetimeIndex, index_ret: pd.Series,
                   bank_list: list[str], vs_index_only: bool = False) -> pd.DataFrame:
    """CAR_A, CAR_B, raw window returns, abnormal volume, rule return per event (one row per usable event)."""
    rets = pd.DataFrame({t: px[t]["adj"].pct_change() for t in px}).reindex(cal)
    vols = pd.DataFrame({t: px[t]["vol"] for t in px}).reindex(cal)
    active = active_discount_table(ev, [b for b in bank_list if b in rets.columns], cal)
    basket = rets[[b for b in bank_list if b in rets.columns]].mean(axis=1, skipna=True)
    rows = []
    n = len(cal)
    for _, e in ev[ev["usable"]].iterrows():
        t = e["ticker"]
        if t not in rets.columns:
            continue
        p = roll_forward(e["pay_date"], cal)
        if p is None:
            continue
        if str(e["window_a_def"]).startswith("regle Pembina") and pd.notna(e["record_date"]):
            r2 = roll_forward(e["record_date"], cal)
            wa = window_idx(p, -21, -2, n) if r2 is None else None
            if r2 is not None and p - 2 >= max(p - 21, r2 + 2):
                wa = list(range(max(p - 21, r2 + 2), p - 1))
        elif pd.notna(e["window_a_start"]) and pd.notna(e["window_a_end"]):
            a0 = roll_forward(e["window_a_start"], cal)
            a1 = int(cal.searchsorted(pd.Timestamp(e["window_a_end"]), side="right")) - 1
            wa = list(range(a0, a1 + 1)) if a0 is not None and a1 >= a0 else None
        else:
            wa = window_idx(p, -5, -1, n)
        wb = window_idx(p, 0, 4, n)
        if wa is None or wb is None:
            continue
        r = rets[t]
        if vs_index_only or e["ticker"] not in bank_list:
            bench = index_ret
        else:
            bench = bank_benchmark(rets, active, index_ret, t)
        ar = r - bench
        ra, rb = r.iloc[wa], r.iloc[wb]
        if ra.isna().any() or rb.isna().any() or ar.iloc[wa].isna().any() or ar.iloc[wb].isna().any():
            continue
        # abnormal volume: 20 trading days before window A
        v = vols[t]
        pre = v.iloc[max(0, wa[0] - 20): wa[0]]
        pre = pre[pre > 0]
        va = v.iloc[wa]
        av = float(np.log(va[va > 0] / pre.median()).mean()) if len(pre) >= 10 and (va > 0).any() else float("nan")
        bk = basket.iloc[wb]
        rows.append({
            "event_id": e["event_id"], "country": e["country"], "ticker": t, "group": e["group"],
            "pay_date": e["pay_date"], "P": cal[p], "D": int(e["D"]), "rabais_pct": float(e["rabais_pct"]),
            "source_achat": e["source_achat"],
            "CAR_A": float(ar.iloc[wa].sum()), "CAR_B": float(ar.iloc[wb].sum()), "AR_P": float(ar.iloc[p]),
            "RAW_A": float((1 + ra).prod() - 1), "RAW_B": float((1 + rb).prod() - 1),
            "BASKET_B": float((1 + bk).prod() - 1), "AV_A": av, "nA": len(wa),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["RULE_NET"] = out["RAW_B"] - out["BASKET_B"] - COST_EVENT
        out["AVOID_NET"] = -out["RAW_A"] - COST_AVOID
    return out


def both_states(df: pd.DataFrame) -> pd.DataFrame:
    k = df.groupby("ticker")["D"].agg(["min", "max"])
    keep = k[(k["min"] == 0) & (k["max"] == 1)].index
    return df[df["ticker"].isin(keep)]


def did_block(df: pd.DataFrame) -> dict:
    s = both_states(df)
    g = s["P"].dt.strftime("%Y-%m-%d").values
    return {"A": cluster_did(s["CAR_A"].values, s["D"].values, g),
            "B": cluster_did(s["CAR_B"].values, s["D"].values, g),
            "VOL": cluster_did(s["AV_A"].values, s["D"].values, g),
            "issuers": sorted(s["ticker"].unique().tolist())}


# =================================================================================== trading rule (daily series)
def rule_series(ev_meas: pd.DataFrame, rets: pd.DataFrame, cal: pd.DatetimeIndex, banks: list[str],
                rf_d: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Daily returns of the rule and of the equal-weight bank basket (the reference's underlying)."""
    bk = rets[banks].mean(axis=1, skipna=True)
    disc = ev_meas[ev_meas["D"] == 1]
    hold = {}      # day index -> list of tickers held that day
    entry_cost = pd.Series(0.0, index=cal)
    for _, e in disc.iterrows():
        p = cal.get_loc(e["P"])
        for k in range(p, min(p + 5, len(cal))):
            hold.setdefault(k, []).append(e["ticker"])
    rule = bk.copy()
    for k, tick in hold.items():
        rr = rets.iloc[k][tick]
        if rr.isna().any():
            rule.iloc[k] = bk.iloc[k]
            continue
        rule.iloc[k] = float(rr.mean())
    # costs: 0.10 % on entry day and 0.10 % on exit day, times the fraction switched (1/m on that day)
    for _, e in disc.iterrows():
        p = cal.get_loc(e["P"])
        for k in (p, min(p + 4, len(cal) - 1)):
            m = len(hold.get(k, [e["ticker"]]))
            entry_cost.iloc[k] += (COST_EVENT / 2.0) / m
    rule = rule - entry_cost
    return rule, bk


# =================================================================================== verdict
def verdict(n_disc: int, did: dict, rule_net_mean: float, rob: dict, au: dict, au_n_disc: int, dsharpe: float) -> dict:
    A, B, V = did["A"], did["B"], did["VOL"]
    c1 = A["did"] <= TH["did_a"] and A["t"] <= TH["t_a"]
    c2 = B["did"] >= TH["did_b"] and B["t"] >= TH["t_b"] and rule_net_mean > 0
    c3 = V["did"] > 0 and V["t"] >= TH["t_vol"]
    c4_detail = {k: bool(v["did"] < 0) if v["did"] == v["did"] else False for k, v in rob.items()}
    au_required = au_n_disc >= MIN_AU
    c4_detail["e_australie"] = bool(au["did"] < 0) if au["did"] == au["did"] else False
    c4 = all(v for k, v in c4_detail.items() if k != "e_australie") and (c4_detail["e_australie"] or not au_required)
    c5 = dsharpe > 0
    reject = (A["did"] >= 0) or (V["did"] <= 0)
    if n_disc < MIN_EVENTS:
        out = "INCERTAIN"
    elif c1 and c2 and c3 and c4 and c5:
        out = "PASS"
    elif reject:
        out = "REJET"
    else:
        out = "INCERTAIN"
    return {"n_discount_events": n_disc, "c1_did_a": bool(c1), "c2_did_b_and_rule": bool(c2), "c3_volume": bool(c3),
            "c4_robustness": bool(c4), "c4_detail": c4_detail, "c4e_required": au_required, "c5_dsharpe": bool(c5),
            "reject_trigger": bool(reject), "verdict": out}


# =================================================================================== data (untrusted files)
def ycsv(t: str) -> str:
    return "YH_" + t.replace("^", "IDX_").replace(".", "_").replace("-", "_") + ".csv"


def parse_yahoo(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    out = pd.DataFrame({"close": pd.to_numeric(df["Close"], errors="coerce"),
                        "adj": pd.to_numeric(df["Adj Close"], errors="coerce"),
                        "vol": pd.to_numeric(df["Volume"], errors="coerce")})
    out.index = pd.DatetimeIndex(out.index).tz_localize(None).normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out[(out["adj"] > 0) & (out["close"] > 0)]


def parse_fred(path: Path) -> pd.Series:
    df = pd.read_csv(path)
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna()


def _save(raw: Path, name: str, data: bytes, src: str, meta: dict):
    (raw / name).write_bytes(data)
    meta[name] = {"source": src, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "downloaded_utc": datetime.now(timezone.utc).isoformat()}
    print("saved", name, len(data))


def tickers_from_events(ev: pd.DataFrame) -> list[str]:
    t = set(ev["ticker"]) | set(CA_BANKS) | set(AU_BANKS) | {CA_INDEX, AU_INDEX}
    return sorted(x for x in t if x)


def download(raw: Path, ev: pd.DataFrame):
    raw.mkdir(parents=True, exist_ok=True)
    mp = raw.parent / "meta.json"
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    import yfinance as yf
    for t in tickers_from_events(ev):
        try:
            df = yf.download(t, start="1999-01-01", end="2026-10-11", auto_adjust=False, progress=False, actions=False)
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(0)
            if df.empty:
                print("Yahoo EMPTY", t)
                meta[ycsv(t)] = {"source": f"yfinance {t}", "status": "empty"}
                continue
            data = df[["Close", "Adj Close", "Volume"]].rename_axis("Date").to_csv().encode()
            _save(raw, ycsv(t), data, f"yfinance {yf.__version__} {t} start=1999-01-01 end=2026-10-11 auto_adjust=False", meta)
        except Exception as ex:  # noqa: BLE001
            print("Yahoo FAIL", t, ex)
            meta[ycsv(t)] = {"source": f"yfinance {t}", "status": f"fail {ex}"}
        time.sleep(0.5)
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={FRED_RF}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=120) as r:
            _save(raw, f"FRED_{FRED_RF}.csv", r.read(), url, meta)
    except Exception as ex:  # noqa: BLE001
        print("FRED FAIL", ex)
    mp.write_text(json.dumps(meta, indent=1))


def load_prices(raw: Path, tickers: list[str]) -> dict:
    px = {}
    for t in tickers:
        p = raw / ycsv(t)
        if p.exists():
            df = parse_yahoo(p)
            if len(df) > 50:
                px[t] = df
    return px


def adj_check(ev: pd.DataFrame, px: dict, cal: pd.DatetimeIndex, k: int = 10) -> list[dict]:
    """Compare window-A and window-B returns from adjusted vs raw closes on the first k usable discount events."""
    out = []
    for _, e in ev[ev["usable"] & (ev["D"] == 1)].iterrows():
        t = e["ticker"]
        if t not in px:
            continue
        p = roll_forward(e["pay_date"], cal)
        if p is None or p - 6 < 0 or p + 4 >= len(cal):
            continue
        s = px[t].reindex(cal)
        a = s["adj"].iloc[[p - 6, p - 1, p + 4]].values
        c = s["close"].iloc[[p - 6, p - 1, p + 4]].values
        if np.isnan(a).any() or np.isnan(c).any():
            continue
        out.append({"event_id": e["event_id"], "ticker": t, "P": str(cal[p].date()),
                    "A_adj": a[1] / a[0] - 1, "A_raw": c[1] / c[0] - 1, "B_adj": a[2] / a[1] - 1, "B_raw": c[2] / c[1] - 1})
        if len(out) >= k:
            break
    return out


# =================================================================================== main analysis
def summarize(df: pd.DataFrame) -> dict:
    return {"n": int(len(df)), "car_a": float(df["CAR_A"].mean()) if len(df) else float("nan"),
            "car_b": float(df["CAR_B"].mean()) if len(df) else float("nan")}


def run(raw: Path, events: Path, out_dir: Path, stem: str) -> dict:
    ev = load_events(events)
    px = load_prices(raw, tickers_from_events(ev))
    res: dict = {"missing_tickers": sorted(set(tickers_from_events(ev)) - set(px))}

    # ---------------- Canada
    ca = ev[ev["country"] == "CA"]
    cal = px[CA_INDEX].index
    cal = cal[cal >= "1999-06-01"]
    idx_ret = px[CA_INDEX]["adj"].pct_change().reindex(cal)
    m = event_measures(ca, px, cal, idx_ret, CA_BANKS)
    m_idx = event_measures(ca, px, cal, idx_ret, CA_BANKS, vs_index_only=True)
    res["counts"] = {"table_discount_ca": int((ca["usable"] & (ca["D"] == 1)).sum()),
                     "table_none_ca": int((ca["usable"] & (ca["D"] == 0)).sum()),
                     "table_undocumented_ca": int((~ca["usable"]).sum()),
                     "measured_discount_ca": int((m["D"] == 1).sum()), "measured_none_ca": int((m["D"] == 0).sum())}
    did = did_block(m)
    res["did_main"] = did
    disc = m[m["D"] == 1]
    res["rule_per_event"] = {"n": int(len(disc)), "mean_net": float(disc["RULE_NET"].mean()),
                             "median_net": float(disc["RULE_NET"].median()),
                             "hit_rate": float((disc["RULE_NET"] > 0).mean()),
                             "t": float(disc["RULE_NET"].mean() / (disc["RULE_NET"].std(ddof=1) / math.sqrt(len(disc))))
                             if len(disc) > 1 else float("nan")}
    rob = {"a_banques": did_block(m[m["group"] == "banque"])["A"],
           "b_non_banques": did_block(m[m["group"] != "banque"])["A"],
           "c_2022_2024": did_block(m[(m["P"] >= EPISODE_C[0]) & (m["P"] <= EPISODE_C[1])])["A"],
           "d_vs_gsptse": did_block(m_idx)["A"]}
    res["robustness"] = rob

    # ---------------- Australia
    au = ev[ev["country"] == "AU"]
    au_res = {"did": float("nan"), "n": 0}
    au_n_disc = 0
    if AU_INDEX in px and len(au):
        cal_au = px[AU_INDEX].index
        cal_au = cal_au[cal_au >= "2018-01-01"]
        idx_au = px[AU_INDEX]["adj"].pct_change().reindex(cal_au)
        m_au = event_measures(au, px, cal_au, idx_au, AU_BANKS)
        au_n_disc = int((m_au["D"] == 1).sum()) if len(m_au) else 0
        if len(m_au):
            dau = did_block(m_au)
            au_res = {**dau["A"], "issuers": dau["issuers"], "did_vol": dau["VOL"]}
            m_au.to_csv(out_dir / f"{stem}_events_au_measured.csv", index=False)
    res["australia"] = au_res
    res["australia_n_discount_measured"] = au_n_disc

    # ---------------- rule daily series vs reference
    rets = pd.DataFrame({t: px[t]["adj"].pct_change() for t in px}).reindex(cal)
    banks = [b for b in CA_BANKS if b in rets.columns]
    rule, basket = rule_series(m, rets, cal, banks, None)
    start = disc["P"].min() - pd.Timedelta(days=7)
    end = disc["P"].max() + pd.Timedelta(days=10)
    rf_m = parse_fred(raw / f"FRED_{FRED_RF}.csv") / 100.0
    rf_d = (rf_m.resample("D").ffill().reindex(cal, method="ffill") / 252.0)
    sel = (cal >= start) & (cal <= end)
    rr, bb, ff = rule[sel], basket[sel], rf_d[sel]
    ev_port = E.evaluate(rr, ff, bb, ppy=252, spread=SPREAD)
    res["portfolio"] = {"start": str(cal[sel][0].date()), "end": str(cal[sel][-1].date()), **ev_port}
    ex = (rr - ff).dropna()
    res["dsr"] = {f"N{n}": deflated_sharpe(ex, n) for n in N_DSR}
    res["dsr_reported"] = {f"N{n}": deflated_sharpe(ex, n) for n in N_DSR_REPORTED}

    res["criteria"] = verdict(res["counts"]["measured_discount_ca"], did, res["rule_per_event"]["mean_net"], rob,
                              au_res, au_n_disc, ev_port["dsharpe"])

    # ---------------- reported without effect
    rep = {}
    pi = m.groupby(["ticker", "D"])[["CAR_A", "CAR_B", "AV_A"]].agg(["mean", "count"]).round(5)
    pi.columns = ["_".join(c) for c in pi.columns]
    rep["per_issuer"] = pi.reset_index().to_dict(orient="records")
    pnl = disc["RULE_NET"].sort_values(ascending=False)
    rep["top5_share_rule_pnl"] = float(pnl.head(5).sum() / pnl.sum()) if pnl.sum() != 0 else float("nan")
    rep["by_discount_level"] = {
        lvl: summarize(disc[sel_]) for lvl, sel_ in
        {"1pct": disc["rabais_pct"] < 1.5, "2pct": (disc["rabais_pct"] >= 1.5) & (disc["rabais_pct"] < 2.5),
         "ge3pct": disc["rabais_pct"] >= 2.5}.items()}
    mk = m[(m["D"] == 0) & (m["source_achat"] == "marche")]
    ot = m[(m["D"] == 0) & (m["source_achat"] != "marche")]
    rep["market_purchase_events"] = {"n": int(len(mk)), "AR_P_mean": float(mk["AR_P"].mean()) if len(mk) else None,
                                     "CAR_B_mean": float(mk["CAR_B"].mean()) if len(mk) else None,
                                     "other_none_AR_P_mean": float(ot["AR_P"].mean()) if len(ot) else None,
                                     "did_AR_P_market_vs_other_none": cluster_did(
                                         pd.concat([mk["AR_P"], ot["AR_P"]]).values,
                                         np.r_[np.ones(len(mk)), np.zeros(len(ot))],
                                         pd.concat([mk["P"], ot["P"]]).dt.strftime("%Y-%m-%d").values)}
    rep["avoid_window_bank_holder"] = {"n": int((disc["group"] == "banque").sum()),
                                       "mean_net": float(disc.loc[disc["group"] == "banque", "AVOID_NET"].mean())}
    rep["intensity_slope"] = "non calcule : actions emises par le DRIP non collectees dans l'etape 0"
    rep["adj_vs_raw_check"] = adj_check(ca, px, cal)
    rep["did_issuer_fixed_effects_note"] = "non calcule (non preenregistre)"
    res["reported"] = rep
    res["conservative_choices"] = CONSERVATIVE

    m.to_csv(out_dir / f"{stem}_events_measured.csv", index=False)
    pd.DataFrame({"rule": rr, "basket": bb, "rf": ff}).to_csv(out_dir / f"{stem}_daily.csv")
    (out_dir / f"{stem}_criteria.json").write_text(json.dumps(res, indent=1, default=_json_default))
    return res


def inspect(raw: Path, events: Path):
    """Structure only: rows, first/last dates, missing values. No return statistic."""
    ev = load_events(events)
    for t in tickers_from_events(ev):
        p = raw / ycsv(t)
        if not p.exists():
            print(t, "MISSING")
            continue
        df = parse_yahoo(p)
        print(t, len(df), df.index.min().date(), df.index.max().date(), "vol0:", int((df["vol"] <= 0).sum()))


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["download", "inspect", "run"])
    ap.add_argument("--raw", default=str(DATA / "raw"))
    ap.add_argument("--events", default=str(EVENTS))
    ap.add_argument("--out", default=str(ROOT / "docs" / "agents" / "results"))
    ap.add_argument("--stem", default="Exp-82_2026-10-12")
    a = ap.parse_args(argv)
    raw = Path(a.raw)
    if a.cmd == "download":
        download(raw, load_events(Path(a.events)))
    elif a.cmd == "inspect":
        inspect(raw, Path(a.events))
    else:
        r = run(raw, Path(a.events), Path(a.out), a.stem)
        print(json.dumps(r["criteria"], indent=1, default=_json_default))


if __name__ == "__main__":
    sys.exit(main())
