"""T-073 atelier -- descriptive diagnostics of the shortlisted rules on the discovery period only
(no new configuration: same rules and frozen k as in LOG.csv).  Prints to stdout."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import discovery as D  # noqa: E402
import engine as E  # noqa: E402

SHORT = ["C14", "C09", "C19", "C02", "C13"]


def main():
    d = D.data()
    rf = d["rf"]
    for a, b in [("1990", "2009"), ("1990", "1999"), ("2000", "2009")]:
        for n in ["EQ", "B10"]:
            r = d[n].loc[a:b]
            print(n, a, b, {k: round(v, 3) for k, v in E.stats(r, rf.loc[r.index]).items()})
        print("  corr EQ/B10", round(d["EQ"].loc[a:b].corr(d["B10"].loc[a:b]), 3))
    log = pd.read_csv(D.LOG)
    cfg = log[~log["id"].str.contains("ctl")]
    print("n configs", len(cfg), "n rows", len(log), "sd annual Sharpe configs", round(cfg["sharpe"].std(ddof=1), 4),
          "sd all rows", round(log["sharpe"].std(ddof=1), 4))
    li = log.set_index("id")
    for cid in SHORT:
        w, rets, _, _ = D.rule(cid)
        k = float(li.loc[cid, "k"])
        sim = E.simulate(w * k, rets.loc[:D.D1], rf.loc[:D.D1])
        r = sim["ret"].loc[D.D0:D.D1]
        yr = (1 + r).groupby(r.index.year).prod() - 1
        L = float(li.loc[cid, "L_ref"])
        ref = E.ref_returns(L, d["EQ"].loc[r.index], rf.loc[r.index])
        yref = (1 + ref).groupby(ref.index.year).prod() - 1
        ex = np.log1p(yr) - np.log1p(yref)
        top3 = ex.nlargest(3)
        eq_on = None
        if "EQ" in w.columns:
            eq_on = round(float((w["EQ"].reindex(r.index).ffill() > 0).mean()), 2)
        print(f"{cid} k={k} worst year {yr.min():+.3f} ({yr.idxmin()}) best {yr.max():+.3f} ({yr.idxmax()}) "
              f"years beating ref {(yr > yref).sum()}/20 ; time with EQ>0 {eq_on}")
        print("   rule ", " ".join(f"{y}:{v:+.2f}" for y, v in yr.items()))
        print("   ref  ", " ".join(f"{y}:{v:+.2f}" for y, v in yref.items()))
        print("   top-3 years share of log surplus", round(top3.sum() / ex.sum(), 2), list(top3.index),
              "total log surplus", round(ex.sum(), 3))


if __name__ == "__main__":
    main()
