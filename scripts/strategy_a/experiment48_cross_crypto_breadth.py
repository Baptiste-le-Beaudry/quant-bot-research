"""Experiment 48 — cross-crypto breadth confirmation (user-directed 2026-10-05).

Question: when the model takes a dip-buy on one crypto, is the trade better
(or worse) when the same pattern fires on other cryptos at the same time?

Pre-registered before looking at results:
- Population: frozen 9-symbol baseline ledger
  docs/multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv (walk-forward
  TEST trades, one position per symbol, no portfolio cap).
- breadth(t) = number of OTHER symbols with an entry within +/-W minutes.
  Primary W = 5 min; W = 15 and 60 are reported, never selected.
- Metric: net return per trade at 0.14 % round trip (registered cost), PF.
- Robust only if the sign of (confirmed - isolated) mean net return is the
  same in both chronological halves AND in >= 5 of 9 symbols.
- Diagnostic only: no filter is adopted from this; a positive result would
  need its own portfolio-level walk-forward + forward test.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv"
OUT = ROOT / "docs" / "experiment48_cross_crypto_breadth.csv"
COST = 0.0014


def breadth(trades: pd.DataFrame, window_min: int) -> np.ndarray:
    t = trades.entry_time.values.astype("datetime64[m]").astype(np.int64)
    sym = trades.symbol.values
    order = np.argsort(t)
    ts, ss = t[order], sym[order]
    out = np.zeros(len(t), dtype=int)
    for k, i in enumerate(order):
        lo, hi = np.searchsorted(ts, t[i] - window_min), np.searchsorted(ts, t[i] + window_min, side="right")
        out[i] = len(set(ss[lo:hi]) - {sym[i]})
    return out


def stats(net: pd.Series) -> dict:
    wins, losses = net[net > 0].sum(), -net[net < 0].sum()
    return {"n": int(len(net)), "mean_net_pct": 100 * net.mean() if len(net) else np.nan,
            "pf": wins / losses if losses else np.nan, "win_pct": 100 * (net > 0).mean() if len(net) else np.nan}


def main() -> None:
    trades = pd.read_csv(LEDGER, usecols=["symbol", "fold", "entry_time", "exit_time", "raw_return", "was_stopped"],
                         parse_dates=["entry_time", "exit_time"])
    trades["net"] = trades.raw_return - COST
    half = trades.entry_time.quantile(0.5)
    rows = []
    for w in (5, 15, 60):
        trades[f"b{w}"] = breadth(trades, w)
        for label, mask in (("isolated (0)", trades[f"b{w}"] == 0), ("confirmed (>=1)", trades[f"b{w}"] >= 1),
                            ("1-2 others", trades[f"b{w}"].between(1, 2)), ("3+ others", trades[f"b{w}"] >= 3)):
            for part, pmask in (("all", True), ("1st half", trades.entry_time < half), ("2nd half", trades.entry_time >= half)):
                rows.append({"window_min": w, "group": label, "period": part, **stats(trades.net[mask & pmask])})
    res = pd.DataFrame(rows)
    res.to_csv(OUT, index=False)
    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))
    # Per-symbol sign test on the primary window
    w = 5
    per = []
    for s, g in trades.groupby("symbol"):
        c, i = g.net[g[f"b{w}"] >= 1], g.net[g[f"b{w}"] == 0]
        per.append({"symbol": s, "n_conf": len(c), "n_iso": len(i), "mean_conf_pct": 100 * c.mean(),
                    "mean_iso_pct": 100 * i.mean(), "conf_minus_iso_pct": 100 * (c.mean() - i.mean())})
    per = pd.DataFrame(per)
    print(per.round(3).to_string(index=False))
    print("symbols where confirmed > isolated:", int((per.conf_minus_iso_pct > 0).sum()), "/", len(per))
    share = (trades.b5 >= 1).mean()
    print(f"share of trades with breadth>=1 at +/-5min: {100*share:.1f}%")


if __name__ == "__main__":
    main()
