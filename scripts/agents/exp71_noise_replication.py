"""Exp 71 -- replication of the Exp 64 "noise area" rule on USA30 -> MYM and USSC2000 -> M2K.

Preregistration: docs/agents/hypotheses/Exp-71.md (frozen). Engine: scripts/agents/exp64_noise_momentum.py
unchanged (frozen reading, commit 33b5a15) except two INSTRUMENTS entries. Only the decision rule
("noise_area") is run: the preregistration allows no variant (the Gao variant of Exp 64 is not run).

Whole series = single test (no TRAIN/HOLDOUT split). Measures: net Sharpe of the daily USD PnL over all
tradable days (0 when no trade) x sqrt(252), on the full period and on the post-publication window
(2024-11-27 -> end); MaxDD, worst day, share of net from the 5 best days, per-year net, cost share.

Fill convention (engine): decisions HH:00/HH:30 from 10:00 to 15:30 ET, executed at the open of the
next bar (never at the stop level), end-of-day exit at the open of the 15:59 bar, 1 contract.
Round trip cost 2.22 USD (1.22 commission + 1 tick of 0.50 USD per side) for both MYM and M2K.

Usage:
    python scripts/agents/exp71_noise_replication.py --data-dir C:/AAProjet/quant_bot_v1/data/indices \
        --out-prefix docs/agents/results/Exp-71_2026-10-10
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1].parent
_spec = importlib.util.spec_from_file_location("exp64", ROOT / "scripts" / "agents" / "exp64_noise_momentum.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

PREREG = ROOT / "docs" / "agents" / "hypotheses" / "Exp-71.md"
NAMES = ("DOW30", "RUSSELL2000")
POST_PUB_START = dt.date(2024, 11, 27)
MIN_ELIGIBLE = {"DOW30": 1000, "RUSSELL2000": 800}
MIN_TRADED_DAYS = 200


def top_k_share(net, k: int = 5):
    """Share of total net PnL coming from the k best days (None if total net <= 0)."""
    x = np.asarray(net, dtype=float)
    tot = x.sum()
    if len(x) == 0 or tot <= 0:
        return None
    return float(np.sort(x)[::-1][:k].sum() / tot)


def summarise(days: pd.DataFrame) -> dict:
    st = E.period_stats(days)
    if days.empty:
        return st
    st["top5_days_share_of_net"] = top_k_share(days["net_usd"])
    st["top5_days_net_usd"] = float(np.sort(days["net_usd"].to_numpy())[::-1][:5].sum())
    return st


def by_year(days: pd.DataFrame) -> dict:
    y = days.assign(year=[d.year for d in days["date"]])
    g = y.groupby("year")
    return {int(k): {"n_days": int(len(v)), "days_traded": int((v["n_trades"] > 0).sum()),
                     "gross_usd": float(v["gross_usd"].sum()), "cost_usd": float(v["cost_usd"].sum()),
                     "net_usd": float(v["net_usd"].sum()), "sharpe_net": E.sharpe(v["net_usd"])}
            for k, v in g}


def verdict(res: dict, eligible: dict) -> dict:
    """Mechanical reading of the Exp 71 criteria. res[name] = {"total": stats, "post": stats}."""
    out = {"rule": ("Etape 0: REJET technique si < 1000 jours eligibles (MYM) ou < 800 (M2K). "
                    "PASS: Sharpe net total >= 0,5 sur les deux ET Sharpe net post-publication > 0 sur les deux "
                    "ET >= 200 jours trades chacun. REJET: Sharpe net total <= 0,2 sur l'un des deux OU "
                    "Sharpe post-publication <= 0 sur les deux. INCERTAIN: tout le reste.")}
    tech = {n: eligible[n] < MIN_ELIGIBLE[n] for n in eligible}
    out["technical_reject"] = tech
    if any(tech.values()):
        out["verdict"] = "REJET (technique, etape 0)"
        return out
    s_tot = {n: res[n]["total"].get("sharpe_net", float("nan")) for n in res}
    s_post = {n: res[n]["post"].get("sharpe_net", float("nan")) for n in res}
    traded = {n: res[n]["total"].get("days_traded", 0) for n in res}
    # NaN Sharpe (no variance / no day) never satisfies a PASS condition and counts as <= 0 (conservative)
    le = lambda x, t: (not np.isfinite(x)) or x <= t   # noqa: E731
    pass_c = {"total_ge_0p5_both": all(np.isfinite(x) and x >= 0.5 for x in s_tot.values()),
              "post_gt_0_both": all(np.isfinite(x) and x > 0 for x in s_post.values()),
              "traded_ge_200_each": all(v >= MIN_TRADED_DAYS for v in traded.values())}
    rej_c = {"total_le_0p2_any": any(le(x, 0.2) for x in s_tot.values()),
             "post_le_0_both": all(le(x, 0.0) for x in s_post.values())}
    out.update({"sharpe_net_total": s_tot, "sharpe_net_post": s_post, "days_traded_total": traded,
                "pass_conditions": pass_c, "reject_conditions": rej_c})
    if all(pass_c.values()):
        out["verdict"] = "PASS"
    elif any(rej_c.values()):
        out["verdict"] = "REJET"
    else:
        out["verdict"] = "INCERTAIN"
    return out


def run_index(name: str, data_dir):
    spec = E.INSTRUMENTS[name]
    df = E.load_pre_holdout(Path(data_dir) / spec["file"], str(PREREG))   # whole series, see step0
    last_bar = str(df.index.max())
    grid = E.build_grid(df)
    del df
    elig = E.eligibility(grid)
    lv = E.compute_levels(grid, elig)
    tr = E.price_trades(E.simulate_noise(grid, elig, lv), spec)
    days = E.daily_series(tr, elig, lv, grid, spec)
    info = {"last_bar_loaded_et": last_bar, "sessions_in_grid": len(grid["dates"]),
            "eligible_sessions": int(elig["eligible"].sum()), "tradable_sessions": int(lv["tradable"].sum())}
    return tr, days, info


def analyse(name: str, tr: pd.DataFrame, days: pd.DataFrame) -> dict:
    post = days[days["date"] >= POST_PUB_START]
    return {"total": summarise(days), "post": summarise(post), "by_year": by_year(days),
            "exit_reasons": tr["exit_reason"].value_counts().to_dict() if len(tr) else {}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out-prefix", required=True)
    a = ap.parse_args(argv)
    crit = {"preregistration": "docs/agents/hypotheses/Exp-71.md", "engine": "scripts/agents/exp64_noise_momentum.py",
            "variants_counted": 1, "fill_convention": "next-bar open after HH:00/HH:30 decision; EOD exit at open of 15:59 bar",
            "category": "en echantillon (serie complete, test unique, aucun parametre regle)", "indices": {}}
    all_days, all_trades, res, elig = [], [], {}, {}
    for name in NAMES:
        spec = E.INSTRUMENTS[name]
        tr, days, info = run_index(name, a.data_dir)
        r = analyse(name, tr, days)
        res[name], elig[name] = r, info["eligible_sessions"]
        crit["indices"][name] = {"future": spec["future"], "mult_usd_per_pt": spec["mult"], "tick_usd": spec["tick_usd"],
                                 "cost_rt_usd": 2 * (E.COMM_PER_SIDE + spec["tick_usd"]), "data": info, **r}
        all_days.append(days.assign(index=name, future=spec["future"],
                                    window=["post" if d >= POST_PUB_START else "pre" for d in days["date"]]))
        all_trades.append(tr.assign(index=name, future=spec["future"]))
        print(name, json.dumps({k: r["total"].get(k) for k in ("n_days", "days_traded", "sharpe_net")}), flush=True)
    crit["verdict"] = verdict(res, elig)
    cols = ["date", "index", "future", "window", "n_trades", "gross_usd", "cost_usd", "net_usd",
            "notional_usd", "gross_pct", "net_pct"]
    pd.concat(all_days, ignore_index=True)[cols].to_csv(a.out_prefix + "_daily.csv", index=False, float_format="%.6f")
    pd.concat(all_trades, ignore_index=True).to_csv(a.out_prefix + "_trades.csv", index=False, float_format="%.6f")
    with open(a.out_prefix + "_criteria.json", "w", encoding="utf-8") as f:
        json.dump(crit, f, indent=2, default=str, ensure_ascii=False)
    print(json.dumps(crit["verdict"], ensure_ascii=False, default=str))
    return crit


if __name__ == "__main__":
    main()
    sys.exit(0)
