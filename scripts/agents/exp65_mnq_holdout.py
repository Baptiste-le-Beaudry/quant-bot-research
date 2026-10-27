"""Exp 65 -- noise-area momentum, MNQ only, single test on the index HOLDOUT.

Preregistration: docs/agents/hypotheses/Exp-65.md (commit bec173b). Rule/engine unchanged:
scripts/agents/exp64_noise_momentum.py (reading frozen at 33b5a15). Only the window changes:
the HOLDOUT is unlocked by the decision file and stats are computed on H and H-post.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

_spec = importlib.util.spec_from_file_location("exp64", Path(__file__).with_name("exp64_noise_momentum.py"))
e64 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e64)

# first session entirely inside each file's positional HOLDOUT (HOLDOUT start: NQ 2024-03-05 12:21 UTC,
# SP 2024-04-03 07:20 UTC, both before that day's 09:30 ET open)
H_START = {"NASDAQ100": dt.date(2024, 3, 5), "SP500": dt.date(2024, 4, 3)}
H_POST_START = dt.date(2024, 11, 27)


def window_stats(days: pd.DataFrame, start: dt.date) -> dict:
    return e64.period_stats(days[days["date"] >= start].reset_index(drop=True))


def by_year(days: pd.DataFrame, start: dt.date) -> dict:
    d = days[days["date"] >= start]
    out = {}
    for y, g in d.groupby([x.year for x in d["date"]]):
        out[int(y)] = {"n_days": int(len(g)), "days_traded": int((g["n_trades"] > 0).sum()),
                       "gross_usd": float(g["gross_usd"].sum()), "net_usd": float(g["net_usd"].sum()),
                       "sharpe_net": e64.sharpe(g["net_usd"]), "worst_day_usd": float(g["net_usd"].min())}
    return out


def verdict65(h: dict, hp: dict) -> dict:
    rule = ("PASS: Sharpe net H >= 0.7, H-post >= 0.5 with >200 traded days, worst day > -1000 USD, "
            "MaxDD > -2000 USD (on H); REJET: Sharpe net H <= 0.3 or H-post <= 0; else INCERTAIN")
    checks = {"sharpe_net_H_ge_0p7": h["sharpe_net"] >= 0.7,
              "sharpe_net_Hpost_ge_0p5": hp["sharpe_net"] >= 0.5,
              "days_traded_Hpost_gt_200": hp["days_traded"] > 200,
              "worst_day_H_gt_minus_1000": h["worst_day_usd"] > -1000,
              "maxdd_H_gt_minus_2000": h["maxdd_usd"] > -2000}
    if h["sharpe_net"] <= 0.3 or hp["sharpe_net"] <= 0:
        v = "REJET"
    elif all(checks.values()):
        v = "PASS"
    else:
        v = "INCERTAIN"
    return {"rule": rule, "checks": {k: bool(x) for k, x in checks.items()}, "verdict": v}


def exp64_p2_verdict(stats: dict) -> str:
    """Exp 64 criteria with P2 = H-post on both indices (reported without effect)."""
    return e64.verdict(stats)["verdict"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--holdout-decision", required=True)
    a = ap.parse_args(argv)
    crit = {"prereg": "docs/agents/hypotheses/Exp-65.md", "engine": "scripts/agents/exp64_noise_momentum.py",
            "holdout_decision": a.holdout_decision, "indices": {}}
    all_days, all_trades, exp64_stats = [], [], {}
    for name in ("NASDAQ100", "SP500"):
        spec = e64.INSTRUMENTS[name]
        res, info = e64.run_index(name, a.data_dir, a.holdout_decision)
        tr, days = res["noise_area"]
        crit["indices"][name] = {
            "future": spec["future"], "cost_rt_usd": 2 * (e64.COMM_PER_SIDE + spec["tick_usd"]),
            "role": "decisional" if name == "NASDAQ100" else "reported without effect",
            "data": {k: v for k, v in info.items() if k != "eligible_by_year"},
            "eligible_by_year": info["eligible_by_year"],
            "H_start": str(H_START[name]), "H": window_stats(days, H_START[name]),
            "H_post": window_stats(days, H_POST_START), "by_year_H": by_year(days, H_START[name]),
            "pre_holdout_P1_check": e64.period_stats(days[(days["date"] < H_START[name]) & (days["period"] == "P1")]),
        }
        exp64_stats[name] = {"P1": crit["indices"][name]["pre_holdout_P1_check"],
                             "P2": crit["indices"][name]["H_post"]}
        h = days["date"] >= H_START[name]
        all_days.append(days[h].assign(index=name, future=spec["future"],
                                       window=["H-post" if d >= H_POST_START else "H" for d in days.loc[h, "date"]]))
        all_trades.append(tr[tr["date"] >= H_START[name]].assign(index=name, future=spec["future"]))
        print(name, json.dumps({"H": crit["indices"][name]["H"], "H_post": crit["indices"][name]["H_post"]},
                               default=str), flush=True)
    nq = crit["indices"]["NASDAQ100"]
    crit["verdict_exp65_mnq"] = verdict65(nq["H"], nq["H_post"])
    crit["exp64_P2_verdict_without_effect"] = exp64_p2_verdict(exp64_stats)
    d = pd.concat(all_days, ignore_index=True)
    cols = ["date", "index", "future", "window", "n_trades", "gross_usd", "cost_usd", "net_usd",
            "notional_usd", "gross_pct", "net_pct"]
    d[cols].to_csv(a.out_prefix + "_daily.csv", index=False, float_format="%.6f")
    pd.concat(all_trades, ignore_index=True).to_csv(a.out_prefix + "_trades.csv", index=False, float_format="%.6f")
    with open(a.out_prefix + "_criteria.json", "w", encoding="utf-8") as f:
        json.dump(crit, f, indent=2, default=str, ensure_ascii=False)
    print(json.dumps(crit["verdict_exp65_mnq"]), crit["exp64_P2_verdict_without_effect"])
    return crit


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
