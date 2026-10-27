"""Run the registered A-Equity shared-capital baseline and risk frontier."""
from __future__ import annotations

import json
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quant_bot.strategy_a_equity.portfolio import PortfolioLimits, simulate

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "strategy_a_equity" / "portfolio"
RISKS = [.0025,.005,.0075,.01,.0125,.015,.02]
OPEN_CAPS = [.05,.075,.10,.125,.15]
GROSS_CAPS = [1.,1.5,2.,3.]


class Prices:
    def __init__(self, symbols):
        self.data = {}
        self.symbol_col = {symbol:i for i,symbol in enumerate(symbols)}
        self.event_row = {}
        self.matrix = None
        for symbol in symbols:
            frame = pd.read_pickle(ROOT / "docs" / "_full_data_cache_a_equity" / f"{symbol}_full.pkl").sort_index()
            idx = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True))
            self.data[symbol] = (idx, frame.close.to_numpy(float))

    def prepare(self, timestamps):
        times = pd.DatetimeIndex(sorted(pd.unique(pd.to_datetime(timestamps, utc=True))))
        self.event_row = {value:i for i,value in enumerate(times)}
        self.matrix = np.empty((len(times), len(self.symbol_col)), dtype=float)
        for symbol, col in self.symbol_col.items():
            idx, values = self.data[symbol]
            locs = idx.searchsorted(times, side="right") - 1
            valid = locs >= 0
            self.matrix[:,col] = np.nan
            self.matrix[valid,col] = values[locs[valid]]

    def __call__(self, symbol, timestamp):
        row = self.event_row.get(timestamp)
        if row is not None:
            return self.matrix[row, self.symbol_col[symbol]]
        idx, values = self.data[symbol]
        loc = idx.searchsorted(timestamp, side="right") - 1
        if loc < 0:
            raise ValueError(f"no causal price for {symbol} at {timestamp}")
        return values[loc]


def metrics(ledger, states, rejected, initial=100_000.):
    if ledger.empty:
        return {"starting_equity": initial, "ending_equity": initial, "trades": 0}
    ordered = ledger.sort_values(["exit_time","symbol","fold"])
    exit_pnl = ordered.groupby("exit_time").pnl.sum()
    realized = initial + exit_pnl.cumsum()
    # Primary drawdown uses event-time mark-to-market equity, not merely
    # realized exits; the latter would hide adverse excursions in open trades.
    curve = np.concatenate([[initial], states.equity.to_numpy(float)])
    dd = curve / np.maximum.accumulate(curve) - 1
    years = (ordered.exit_time.max()-ordered.entry_time.min()).total_seconds()/(365.25*86400)
    end = initial + ordered.pnl.sum()
    wins = ordered.loc[ordered.pnl>0,"pnl"].sum(); losses = -ordered.loc[ordered.pnl<0,"pnl"].sum()
    maxdd = float(dd.min()*100); cagr = float(((end/initial)**(1/years)-1)*100) if end>0 else -100.
    return {"starting_equity": initial, "ending_equity": float(end), "total_pnl": float(end-initial),
            "total_return_pct": float((end/initial-1)*100), "cagr_pct": cagr,
            "max_dd_pct": maxdd, "calmar": cagr/abs(maxdd) if maxdd else np.inf,
            "profit_factor": float(wins/losses) if losses else np.inf,
            "expectancy_dollars": float(ordered.pnl.mean()), "win_rate_pct": float((ordered.pnl>0).mean()*100),
            "candidate_signals": int(len(ordered)+len(rejected)), "trades": int(len(ordered)),
            "rejected_trades": int(len(rejected)),
            "acceptance_rate_pct": float(100*len(ordered)/(len(ordered)+len(rejected))),
            "fees": 0., "spread": float(ordered.notional.sum()*.0001),
            "slippage": float(ordered.notional.sum()*.0001), "total_cost": float(ordered.total_cost.sum()),
            "average_holding_minutes": float((ordered.exit_time-ordered.entry_time).dt.total_seconds().mean()/60),
            "median_holding_minutes": float((ordered.exit_time-ordered.entry_time).dt.total_seconds().median()/60),
            "max_simultaneous_positions": int(states.open_positions.max()),
            "peak_open_risk": float(states.open_risk.max()),
            "peak_gross_exposure": float(states.gross_exposure.max())}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--baseline-only",action="store_true"); args=parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    candidates = {m: pd.read_pickle(OUT/f"audited_candidates_{m}.pkl") for m in ("rf","logistic")}
    symbols = sorted(set(pd.concat(candidates.values()).symbol))
    prices = Prices(symbols)
    prices.prepare(pd.concat(candidates.values()).entry_time)
    for data in candidates.values():
        sample = data.groupby("symbol", sort=False).head(3)
        for row in sample.itertuples():
            if not np.isclose(prices(row.symbol, row.entry_time), row.entry_price, rtol=0, atol=1e-12):
                raise RuntimeError(f"price alignment audit failed: {row.symbol} {row.entry_time}")
    frontier_path = OUT / "equity_portfolio_risk_frontier.csv"
    done = pd.read_csv(frontier_path).to_dict("records") if frontier_path.exists() else []
    keys = {(r["universe"],r["model"],float(r["risk_pct"]),float(r["open_risk_cap"]),float(r["gross_cap"])) for r in done}
    universes = {"DISCOVERY": "discovery", "CONFIRMATION": "confirmation", "COMBINED": None}
    if not args.baseline_only:
      for universe, label in universes.items():
        for model, all_data in candidates.items():
          data = all_data if label is None else all_data[all_data.universe==label]
          for risk in RISKS:
            for open_cap in OPEN_CAPS:
              for gross in GROSS_CAPS:
                key=(universe,model,risk,open_cap,gross)
                if key in keys: continue
                ledger, states, rejected = simulate(data, PortfolioLimits(risk,open_cap,gross), prices)
                row={"universe":universe,"model":model,"risk_pct":risk,
                     "open_risk_cap":open_cap,"gross_cap":gross,
                     **metrics(ledger,states,rejected)}
                done.append(row); keys.add(key)
                pd.DataFrame(done).to_csv(frontier_path,index=False)
                print(f"{universe} {model} risk={risk:.4f} open={open_cap:.3f} gross={gross:.1f} "
                      f"CAGR={row['cagr_pct']:.2f} DD={row['max_dd_pct']:.2f} PF={row['profit_factor']:.3f}",flush=True)
    baseline={}
    for universe,label in universes.items():
        for model,all_data in candidates.items():
            data=all_data if label is None else all_data[all_data.universe==label]
            ledger,states,rejected=simulate(data,PortfolioLimits(.01,.10,2.),prices)
            key=f"{universe}_{model}"; baseline[key]=metrics(ledger,states,rejected)
            if universe=="COMBINED":
                ledger.to_csv(OUT/f"baseline_{model}_trade_ledger.csv",index=False)
                rejected.to_csv(OUT/f"baseline_{model}_signal_rejections.csv",index=False)
                states.to_pickle(OUT/f"baseline_{model}_states.pkl")
    (OUT/"baseline_summary.json").write_text(json.dumps(baseline,indent=2),encoding="utf-8")


if __name__ == "__main__": main()
