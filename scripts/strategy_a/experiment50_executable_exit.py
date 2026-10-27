"""Experiment 50 — executable exits on the HOLDOUT-window walk-forward entries
(preregistered in docs/research_plan_status.md before any result).

Reads Experiment 49's walk-forward entries (outputs/experiment49/*_trades.csv:
symbol, fold, entry_time, stop_distance) and re-exits each one on the cached
1m OHLC with:
  TIME50_CAT3      exit at the close 50 bars later; intrabar stop at 3x the
                   fold's stop distance, filled at min(stop, open)  [primary]
  TIME50_NOSTOP    same, no stop                                    [secondary]
  CURRENT_INTRABAR today's stop + trailing (0.63 %/0.8 %), intrabar fills
Then per-symbol / pooled mean net at 0.05 / 0.17 / 0.25 % round trip, the
preregistered verdict, and account-level metrics at 10 % notional per trade
(no compounding, minute MTM on bar lows).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.multi_crypto_walkforward import _load_full_cached  # noqa: E402
from scripts.strategy_a.exit_realism_check import sim as current_rule  # noqa: E402

IN = ROOT / "outputs" / "experiment49"
COSTS = (0.0005, 0.0017, 0.0025)
SIZE = 0.10
HOLD = 50


def time_exit(o, l, c, e, stop_d, k):
    entry = c[e]
    for j in range(1, HOLD + 1):
        if e + j >= len(c):
            break
        if k is not None and l[e + j] / entry - 1 <= -k * stop_d:
            return min(-k * stop_d, o[e + j] / entry - 1), e + j
    end = min(e + HOLD, len(c) - 1)
    return c[end] / entry - 1, end


def main():
    files = sorted(IN.glob("*_trades.csv"))
    trades = pd.concat([pd.read_csv(f, parse_dates=["entry_time"]) for f in files if f.stat().st_size > 5])
    rows, mtm = [], {"TIME50_CAT3": [], "TIME50_NOSTOP": []}
    for sym, g in trades.groupby("symbol"):
        bars = _load_full_cached(sym)
        idx = bars.index.get_indexer(g.entry_time)
        o, h, l, c = (bars[x].to_numpy() for x in ("open", "high", "low", "close"))
        ti = bars.index.tz_convert(None)
        for e, sd, t in zip(idx, g.stop_distance, g.entry_time):
            if e < 0:
                continue
            r = {"symbol": sym, "entry_time": t}
            for name, k in (("TIME50_CAT3", 3.0), ("TIME50_NOSTOP", None)):
                ret, end = time_exit(o, l, c, e, sd, k)
                r[name] = ret
                lows = np.maximum(l[e + 1:end] / c[e] - 1, -3 * sd if k else -1)
                mtm[name].append((ti[e + 1:end].values, lows, ti[end], ret))
            r["CURRENT_INTRABAR"] = current_rule(o, h, l, c, e, sd, "intrabar")
            rows.append(r)
        del bars
    d = pd.DataFrame(rows)
    d.to_csv(ROOT / "docs" / "experiment50_trades.csv", index=False)
    out = []
    print(f"trades {len(d)}  ({d.entry_time.min():%Y-%m-%d} -> {d.entry_time.max():%Y-%m-%d})")
    for rule in ("TIME50_CAT3", "TIME50_NOSTOP", "CURRENT_INTRABAR"):
        for cost in COSTS:
            net = d[rule] - cost
            per = (d.assign(n=net).groupby("symbol").n.mean() * 100)
            pf = net[net > 0].sum() / -net[net < 0].sum()
            out.append({"rule": rule, "cost_rt_pct": 100 * cost, "trades": len(net), "mean_net_pct": 100 * net.mean(),
                        "pf": pf, "symbols_positive": int((per > 0).sum()), "symbols": len(per)})
            print(f"{rule:17s} cost {100 * cost:.2f}%: mean net {100 * net.mean():+.3f}%  PF {pf:.3f}  symbols>0 {(per > 0).sum()}/{len(per)}  {per.round(3).to_dict()}")
    res = pd.DataFrame(out)
    res.to_csv(ROOT / "docs" / "experiment50_summary.csv", index=False)
    p = res[(res.rule == "TIME50_CAT3")]
    m17 = p[p.cost_rt_pct.round(2) == 0.17].iloc[0]
    m05 = p[p.cost_rt_pct.round(2) == 0.05].iloc[0]
    if m17.mean_net_pct > 0 and m17.symbols_positive >= 5:
        verdict = "PASS"
    elif m05.mean_net_pct <= 0:
        verdict = "FAIL"
    else:
        verdict = "PARTIAL"
    print(f"\nPREREGISTERED VERDICT (TIME50_CAT3): {verdict}")
    years = max((d.entry_time.max() - d.entry_time.min()).days / 365.25, 1e-9)
    for rule, items in mtm.items():
        for cost in COSTS:
            mt = pd.Series(np.concatenate([x[1] for x in items]) * SIZE,
                           index=pd.DatetimeIndex(np.concatenate([x[0] for x in items]))).groupby(level=0).sum()
            fin = pd.Series([(x[3] - cost) * SIZE for x in items], index=pd.DatetimeIndex([x[2] for x in items])).groupby(level=0).sum()
            ix = mt.index.union(fin.index)
            eq = 1 + fin.reindex(ix, fill_value=0).cumsum() + mt.reindex(ix, fill_value=0)
            day = eq.groupby(eq.index.floor("D"))
            print(f"account {rule:14s} cost {100 * cost:.2f}% size 10%: return {100 * fin.sum() / years:+.1f}%/yr  "
                  f"worst day {100 * (day.min() / day.first() - 1).min():.1f}%  max DD {100 * (eq / eq.cummax() - 1).min():.1f}%")


if __name__ == "__main__":
    main()
