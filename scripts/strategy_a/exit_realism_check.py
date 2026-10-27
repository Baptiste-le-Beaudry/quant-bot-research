"""Exit-realism diagnostic on the frozen 9-symbol baseline (pre-HOLDOUT only).

The research ledger evaluates stops/trailing on the 1m CLOSE path and exits
AT the stop level when a close breaches it. A real stop order fills when the
price touches it intrabar, and a close-only rule can only exit at the close.
Re-simulates every baseline trade (same entry, stop distance, trailing
0.63 %/0.8 %, 50-bar cap) on the cached 1m OHLC bars three ways:
  A research : close path, exit at the stop/trail level   (= ledger)
  B close    : close path, exit at that bar's CLOSE         (achievable by a bot checking closes)
  C intrabar : stop/trail touched on high/low, peak on high (= server-side stop, paper runner)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.multi_crypto_walkforward import _load_full_cached  # noqa: E402

LEDGER = ROOT / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv"
ACT, TRAIL, MAXBARS, COST = 0.0063, 0.0080, 50, 0.0014


def sim(o, h, l, c, e, stop_d, mode):
    entry = c[e]
    stop = -stop_d
    peak, active = -np.inf, False
    for k in range(1, MAXBARS + 1):
        if e + k >= len(c):
            break
        hi, lo, cl = h[e + k] / entry - 1, l[e + k] / entry - 1, c[e + k] / entry - 1
        if mode == "intrabar":
            level = max(stop, peak - TRAIL) if active else stop
            if lo <= level:
                return min(level, o[e + k] / entry - 1)   # gap through the stop fills at the open
            peak = max(peak, hi)
            active = active or peak >= ACT
        else:
            x = cl
            if x <= stop:
                return stop if mode == "research" else x
            peak = max(peak, x)
            active = active or peak >= ACT
            if active and x <= peak - TRAIL:
                return peak - TRAIL if mode == "research" else x
    return c[min(e + MAXBARS, len(c) - 1)] / entry - 1


def main():
    led = pd.read_csv(LEDGER, parse_dates=["entry_time"])
    out = []
    for sym, g in led.groupby("symbol"):
        bars = _load_full_cached(sym)
        idx = bars.index.get_indexer(g.entry_time)
        o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
        for (_, r), e in zip(g.iterrows(), idx):
            if e < 0:
                continue
            row = {"symbol": sym, "entry_time": r.entry_time, "ledger": r.raw_return}
            for m in ("research", "close", "intrabar"):
                row[m] = sim(o, h, l, c, e, r.stop_distance, m)
            out.append(row)
        del bars
        print(sym, len(g), flush=True)
    df = pd.DataFrame(out)
    df.to_csv(ROOT / "docs" / "exit_realism_check.csv", index=False)
    print(f"\nmatched {len(df)} / {len(led)} trades; research vs ledger mean abs diff {np.abs(df.research - df.ledger).mean():.5f}")
    for m in ("ledger", "research", "close", "intrabar"):
        net = df[m] - COST
        print(f"{m:9s}: mean net {100 * net.mean():+.3f}%  PF {net[net > 0].sum() / -net[net < 0].sum():.3f}  win {100 * (net > 0).mean():.0f}%")
    for m in ("close", "intrabar"):
        net = df[m] - COST
        per = df.assign(n=net).groupby("symbol").n.mean().mul(100).round(3).to_dict()
        print(f"{m} by symbol mean net %:", per)


if __name__ == "__main__":
    main()
