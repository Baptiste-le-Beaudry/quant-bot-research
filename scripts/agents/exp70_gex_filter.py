"""Exp 70 -- noise-area MNQ, flat on high-GEX days (H-R15-C).

Preregistration: docs/agents/hypotheses/Exp-70.md (frozen at commit 3986ce6). Step 0 (data revision
check) is done by exp70_step0.py and committed before this script was run on window H.

Rule: engine and reading of Exp 64 unchanged (daily PnL taken from the Exp 65 HOLDOUT run,
docs/agents/results/Exp-65_2026-10-08_daily.csv). Day J is FLAT (no trade, no cost, net 0) if
pct(GEX(J-1)) > 2/3, pct = share of the 251 preceding GEX values strictly below GEX(J-1)
(same computation as docs/agents/research/H-R15_scripts/gex_split.py, but a full 251-value window
is required). Otherwise the day is unchanged.

GEX(J-1) alignment: the last DIX.csv row with date strictly before J (merge_asof, no exact match).
SqueezeMetrics publishes the row of day D on the evening of D (Wayback captures 18:20-19:55 ET,
see Exp-70 step 0), i.e. before the 09:30 ET open of J. If the previous NYSE session is missing
from DIX.csv, the older row is used (what a live trader would see) and the day is counted.
If no GEX value is available (pct undefined) the rule applies unchanged (no flat) and is counted.

Because every Exp 64 trade is opened and closed inside the same session (exit at 15:59 ET), a flat
day is exactly "engine not run that day": net_usd, gross_usd, cost_usd, n_trades set to 0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_spec = importlib.util.spec_from_file_location("exp64", Path(__file__).with_name("exp64_noise_momentum.py"))
e64 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e64)

FROZEN_SHA256 = "75495c7b1bf8260679504c1370e43833c618415b252b3b29491f0fb9d8d8c190"
WINDOW = 251                     # preceding values used for the percentile
THRESHOLD = 2 / 3                # decisional (preregistered)
THRESHOLD_ALT = 1 / 2            # reported without effect
H_START = {"NASDAQ100": dt.date(2024, 3, 5), "SP500": dt.date(2024, 4, 3)}
H_END = dt.date(2026, 8, 18)
H_POST_START = dt.date(2024, 11, 27)
FUTURE = {"NASDAQ100": "MNQ", "SP500": "MES"}
DAY_COLS = ["n_trades", "gross_usd", "cost_usd", "net_usd", "gross_pct", "net_pct"]


def load_gex(path, expected_sha=FROZEN_SHA256) -> pd.DataFrame:
    if expected_sha is not None:
        sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if sha != expected_sha:
            raise ValueError(f"DIX snapshot sha256 {sha} != frozen {expected_sha}")
    g = pd.read_csv(path)
    g["date"] = pd.to_datetime(g["date"]).dt.date
    g = g.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    return g[["date", "gex"]]


def gex_percentile(gex: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """pct(D) = share of the `window` GEX values preceding D (in DIX rows) strictly below GEX(D).
    NaN when fewer than `window` preceding values exist."""
    x = gex["gex"].to_numpy(dtype=float)
    pct = np.full(len(x), np.nan)
    for i in range(window, len(x)):
        prev = x[i - window:i]
        pct[i] = float((prev < x[i]).mean())
    out = gex.copy()
    out["pct"] = pct
    return out


def attach_prev_gex(days: pd.DataFrame, gexp: pd.DataFrame) -> pd.DataFrame:
    """For each trading day J, attach the last DIX row dated strictly before J."""
    d = days.copy()
    d["_ts"] = pd.to_datetime(d["date"])
    g = gexp.rename(columns={"date": "gex_prev_date", "gex": "gex_prev", "pct": "pct_prev"}).copy()
    g["_ts"] = pd.to_datetime(g["gex_prev_date"])
    m = pd.merge_asof(d.sort_values("_ts"), g.sort_values("_ts"), on="_ts",
                      allow_exact_matches=False, direction="backward")
    m = m.drop(columns="_ts")
    m["prev_session"] = [e64.previous_session(x) for x in m["date"]]
    m["gex_prev_is_prev_session"] = [(isinstance(a, dt.date) and a == b)
                                     for a, b in zip(m["gex_prev_date"], m["prev_session"])]
    return m


def apply_filter(days: pd.DataFrame, threshold: float) -> tuple[pd.DataFrame, pd.Series]:
    flat = (days["pct_prev"] > threshold).fillna(False).astype(bool)
    f = days.copy()
    for c in DAY_COLS:
        f.loc[flat, c] = 0.0
    f["n_trades"] = f["n_trades"].astype(int)
    return f, flat


def top5_share(net: pd.Series):
    tot = float(net.sum())
    if tot <= 0:
        return None
    return float(net.nlargest(5).sum() / tot)


def stats(days: pd.DataFrame) -> dict:
    s = e64.period_stats(days.reset_index(drop=True))
    n = days["net_usd"]
    s["top5_share_of_net"] = top5_share(n)
    s["sharpe_net_without_best_day"] = e64.sharpe(n.drop(n.idxmax())) if len(n) > 2 else None
    return s


def by_year(days: pd.DataFrame) -> dict:
    out = {}
    for y, g in days.groupby([x.year for x in days["date"]]):
        out[int(y)] = {"n_days": int(len(g)), "days_traded": int((g["n_trades"] > 0).sum()),
                       "net_usd": float(g["net_usd"].sum()), "sharpe_net": e64.sharpe(g["net_usd"]),
                       "maxdd_usd": e64.max_drawdown(g["net_usd"]), "worst_day_usd": float(g["net_usd"].min())}
    return out


def verdict70(filt: dict, unfilt: dict) -> dict:
    s, s0, mdd, t5 = filt["sharpe_net"], unfilt["sharpe_net"], filt["maxdd_usd"], filt["top5_share_of_net"]
    checks = {"sharpe_net_filtered_ge_0p8": bool(s >= 0.8),
              "maxdd_filtered_ge_minus_2000": bool(mdd >= -2000),
              "top5_share_le_0p5": bool(t5 is not None and t5 <= 0.5),
              "sharpe_filtered_ge_unfiltered": bool(s >= s0)}
    rej = {"maxdd_filtered_lt_minus_2500": bool(mdd < -2500), "sharpe_filtered_lt_0p5": bool(s < 0.5),
           "sharpe_filtered_lt_unfiltered": bool(s < s0)}
    if any(rej.values()):
        v = "REJET"
    elif all(checks.values()):
        v = "PASS"
    else:
        v = "INCERTAIN"
    return {"rule": "PASS: Sharpe net filtered >= 0.8 and MaxDD filtered >= -2000 USD and top-5-days share <= 50 % "
                    "and Sharpe filtered >= unfiltered; REJET: MaxDD filtered < -2500 or Sharpe filtered < 0.5 "
                    "or Sharpe filtered < unfiltered; else INCERTAIN",
            "unfiltered_sharpe_used": s0, "pass_checks": checks, "reject_checks": rej, "verdict": v}


def evaluate(days: pd.DataFrame, gexp: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """days: one index, window already cut. Returns (block, daily frame with filter columns)."""
    d = attach_prev_gex(days, gexp)
    f23, flat23 = apply_filter(d, THRESHOLD)
    f12, flat12 = apply_filter(d, THRESHOLD_ALT)
    blk = {
        "alignment": {
            "n_days": int(len(d)),
            "pct_undefined_days_traded_unchanged": int(d["pct_prev"].isna().sum()),
            "gex_prev_is_previous_nyse_session": int(d["gex_prev_is_prev_session"].sum()),
            "gex_prev_older_than_previous_session": int((~d["gex_prev_is_prev_session"] & d["gex_prev_date"].notna()).sum()),
            "older_examples": [{"date": str(a), "gex_prev_date": str(b), "previous_session": str(c)}
                               for a, b, c in d.loc[~d["gex_prev_is_prev_session"], ["date", "gex_prev_date", "prev_session"]]
                               .head(20).itertuples(index=False)],
            "max_gex_prev_date_lt_date": bool((pd.to_datetime(d["gex_prev_date"]) < pd.to_datetime(d["date"])).all()),
        },
        "unfiltered": stats(d),
        "filtered_2_3": stats(f23),
        "filtered_1_2_without_effect": stats(f12),
        "flat_days_2_3": int(flat23.sum()),
        "flat_days_1_2": int(flat12.sum()),
        "flat_days_2_3_that_had_trades": int((flat23 & (d["n_trades"] > 0)).sum()),
        "net_removed_by_2_3_usd": float(d.loc[flat23, "net_usd"].sum()),
        "by_year_filtered_2_3": by_year(f23),
    }
    out = d.copy()
    out["flat_2_3"] = flat23.to_numpy()
    out["flat_1_2"] = flat12.to_numpy()
    out["net_usd_filtered_2_3"] = f23["net_usd"].to_numpy()
    out["net_usd_filtered_1_2"] = f12["net_usd"].to_numpy()
    out["n_trades_filtered_2_3"] = f23["n_trades"].to_numpy()
    return blk, out


def load_exp65(path) -> pd.DataFrame:
    d = pd.read_csv(path)
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp65-daily", required=True)
    ap.add_argument("--exp64-daily", required=True, help="P1 daily (information only)")
    ap.add_argument("--dix", required=True)
    ap.add_argument("--out-prefix", required=True)
    a = ap.parse_args(argv)
    gexp = gex_percentile(load_gex(a.dix))
    d65 = load_exp65(a.exp65_daily)
    d64 = load_exp65(a.exp64_daily)
    crit = {"prereg": "docs/agents/hypotheses/Exp-70.md", "engine": "scripts/agents/exp64_noise_momentum.py (unchanged)",
            "daily_source": a.exp65_daily, "dix_snapshot": a.dix, "dix_sha256": FROZEN_SHA256,
            "threshold": THRESHOLD, "pct_window": WINDOW, "indices": {}}
    frames = []
    for name in ("NASDAQ100", "SP500"):
        d = d65[(d65["index"] == name) & (d65["date"] >= H_START[name]) & (d65["date"] <= H_END)]
        d = d.sort_values("date").reset_index(drop=True)
        blk, out = evaluate(d, gexp)
        post = out[out["date"] >= H_POST_START]
        blk["H_post_without_effect"] = {
            "unfiltered": stats(post), "filtered_2_3": stats(post.assign(net_usd=post["net_usd_filtered_2_3"],
                                                                         n_trades=post["n_trades_filtered_2_3"],
                                                                         gross_usd=np.where(post["flat_2_3"], 0.0, post["gross_usd"]),
                                                                         cost_usd=np.where(post["flat_2_3"], 0.0, post["cost_usd"]),
                                                                         net_pct=np.where(post["flat_2_3"], 0.0, post["net_pct"])))}
        p1 = d64[(d64["index"] == name) & (d64["variant"] == "noise_area") & (d64["period"] == "P1")]
        p1 = p1.sort_values("date").reset_index(drop=True)
        p1blk, _ = evaluate(p1, gexp)
        blk["P1_information_only"] = {k: p1blk[k] for k in ("unfiltered", "filtered_2_3", "flat_days_2_3")}
        blk["P1_information_only"]["pct_undefined_days"] = p1blk["alignment"]["pct_undefined_days_traded_unchanged"]
        blk["future"] = FUTURE[name]
        blk["role"] = "decisional" if name == "NASDAQ100" else "reported without effect"
        crit["indices"][name] = blk
        frames.append(out)
        print(name, json.dumps({k: {x: blk[k][x] for x in ("sharpe_net", "maxdd_usd", "top5_share_of_net",
                                                         "worst_day_usd", "n_days", "days_traded")}
                                for k in ("unfiltered", "filtered_2_3", "filtered_1_2_without_effect")}), flush=True)
    nq = crit["indices"]["NASDAQ100"]
    crit["verdict_exp70_mnq"] = verdict70(nq["filtered_2_3"], nq["unfiltered"])
    crit["mes_same_rule_without_effect"] = verdict70(crit["indices"]["SP500"]["filtered_2_3"],
                                                     crit["indices"]["SP500"]["unfiltered"])["verdict"]
    crit["mnq_threshold_1_2_without_effect"] = verdict70(nq["filtered_1_2_without_effect"], nq["unfiltered"])["verdict"]
    crit["variants"] = {"decisional": 1, "exploratory_P1_looks_counted": 4,
                        "reported_without_effect": ["MES same filter", "threshold 1/2", "H-post", "P1"]}
    print("VERDICT", crit["verdict_exp70_mnq"]["verdict"])
    cols = ["date", "index", "future", "window", "n_trades", "gross_usd", "cost_usd", "net_usd", "gex_prev_date",
            "gex_prev", "pct_prev", "gex_prev_is_prev_session", "flat_2_3", "flat_1_2", "n_trades_filtered_2_3",
            "net_usd_filtered_2_3", "net_usd_filtered_1_2"]
    pd.concat(frames, ignore_index=True)[cols].to_csv(a.out_prefix + "_daily.csv", index=False, float_format="%.6f")
    Path(a.out_prefix + "_criteria.json").write_text(json.dumps(crit, indent=2, default=str, ensure_ascii=False),
                                                     encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
