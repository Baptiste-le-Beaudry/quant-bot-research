"""Multi-year backtest of the crypto bot executed as Jupiter (Solana) spot swaps.

User-directed configuration (2026-10-05): SOL, BTC (cbBTC), ETH (WETH) only;
33 % of current equity per position, no leverage (total exposure <= 100 %);
exit at the 1m close 50 bars after entry, no tight stop (TIME50_NOSTOP);
compounding. Also reported: TIME50_CAT3 (3x catastrophic stop).

Entries: walk-forward TEST trades only —
  2021-11 → 2025-04  frozen 9-symbol baseline ledger (pre-HOLDOUT)
  2025-05 → 2026-05  Experiment 49 retrained walk-forward (HOLDOUT window, already seen)
CAVEAT: the exit rule and the SOL/BTC/ETH subset were chosen after looking at
these same trades (Exp 50 exploration), so this is an in-sample estimate. Only
a forward run on live Jupiter quotes is independent.

Costs: round trip 0.05 % (Jupiter quotes measured 2026-10-05 ~0.00-0.04 % +
tx/priority fees), stressed at 0.10 % and 0.20 % (thinner Solana DEX liquidity
in 2021-2023). Minute mark-to-market uses Binance 1m lows (worst case).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.multi_crypto_walkforward import _load_full_cached  # noqa: E402

SYMS = ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
SIZE, HOLD, START_EQUITY = 0.33, 50, 5_000.0
COSTS = (0.0005, 0.0010, 0.0020)


def load_entries() -> pd.DataFrame:
    base = pd.read_csv(ROOT / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv",
                       usecols=["symbol", "entry_time", "stop_distance"], parse_dates=["entry_time"])
    hold = pd.read_csv(ROOT / "outputs" / "experiment49" / "JOINT_trades.csv",
                       usecols=["symbol", "entry_time", "stop_distance"], parse_dates=["entry_time"])
    base["source"], hold["source"] = "pre-holdout", "holdout-retrained"
    e = pd.concat([base, hold])
    return e[e.symbol.isin(SYMS)].sort_values("entry_time").reset_index(drop=True)


def paths(entries: pd.DataFrame, rule: str) -> list[dict]:
    out = []
    for sym, g in entries.groupby("symbol"):
        b = _load_full_cached(sym)
        idx = b.index.get_indexer(g.entry_time)
        o, l, c = (b[k].to_numpy() for k in ("open", "low", "close"))
        ti = b.index.tz_convert(None)
        for (_, r), e in zip(g.iterrows(), idx):
            if e < 0 or e + HOLD >= len(c):
                continue
            entry, end, ret = c[e], e + HOLD, None
            if rule == "CAT3":
                for j in range(1, HOLD + 1):
                    if l[e + j] / entry - 1 <= -3 * r.stop_distance:
                        ret, end = min(-3 * r.stop_distance, o[e + j] / entry - 1), e + j
                        break
            if ret is None:
                ret = c[e + HOLD] / entry - 1
            low_path = l[e + 1:end] / entry - 1
            if rule == "CAT3":
                low_path = np.maximum(low_path, -3 * r.stop_distance)
            out.append({"symbol": sym, "t_in": ti[e], "t_out": ti[end], "ret": ret,
                        "mtm_t": ti[e + 1:end].values, "mtm": low_path, "source": r.source})
        del b
    return sorted(out, key=lambda x: x["t_in"])


def simulate(trades: list[dict], cost: float) -> dict:
    events = sorted([(t["t_in"], 1, i) for i, t in enumerate(trades)] + [(t["t_out"], 0, i) for i, t in enumerate(trades)])
    equity, invested, open_n, notional = START_EQUITY, 0.0, {}, {}
    realized_curve, skipped = [], 0
    for ts, kind, i in events:
        if kind == 1:
            n = min(SIZE * equity, equity - invested)   # no leverage: never more than 100 % invested
            if n <= equity * 0.01:
                skipped += 1
                continue
            notional[i] = n
            invested += n
        elif i in notional:
            n = notional[i]
            equity += n * (trades[i]["ret"] - cost)
            invested -= n
            realized_curve.append((ts, equity))
    # minute MTM (worst case on lows) for drawdown / worst day
    rc = pd.Series([v for _, v in realized_curve], index=pd.DatetimeIndex([t for t, _ in realized_curve])).groupby(level=0).last()
    mt = pd.Series(np.concatenate([trades[i]["mtm"] * n for i, n in notional.items()]),
                   index=pd.DatetimeIndex(np.concatenate([trades[i]["mtm_t"] for i in notional]))).groupby(level=0).sum()
    ix = rc.index.union(mt.index)
    eq = rc.reindex(ix).ffill().fillna(START_EQUITY) + mt.reindex(ix, fill_value=0)
    day = eq.groupby(eq.index.floor("D"))
    years = (ix.max() - ix.min()).days / 365.25
    yearly = rc.groupby(rc.index.year).last()
    prev = START_EQUITY
    yr = {}
    for y, v in yearly.items():
        yr[int(y)] = round(100 * (v / prev - 1), 1)
        prev = v
    nets = np.array([trades[i]["ret"] - cost for i in notional])
    return {"trades": len(notional), "skipped_no_cash": skipped, "end_equity": round(equity),
            "cagr_pct": round(100 * ((equity / START_EQUITY) ** (1 / years) - 1), 1),
            "max_dd_pct": round(100 * (eq / eq.cummax() - 1).min(), 1),
            "worst_day_pct": round(100 * (day.min() / day.first() - 1).min(), 1),
            "pf_per_trade": round(nets[nets > 0].sum() / -nets[nets < 0].sum(), 3),
            "mean_net_pct": round(100 * nets.mean(), 3), "yearly_pct": yr}


def main():
    entries = load_entries()
    print(f"entries {len(entries)} ({entries.entry_time.min():%Y-%m-%d} -> {entries.entry_time.max():%Y-%m-%d}), "
          f"by symbol {entries.symbol.value_counts().to_dict()}")
    rows = []
    for rule in ("NOSTOP", "CAT3"):
        tr = paths(entries, rule)
        for cost in COSTS:
            r = {"rule": rule, "cost_rt_pct": 100 * cost, **simulate(tr, cost)}
            rows.append(r)
            print(r, flush=True)
    pd.DataFrame(rows).to_csv(ROOT / "docs" / "jupiter_backtest_summary.csv", index=False)


if __name__ == "__main__":
    main()
