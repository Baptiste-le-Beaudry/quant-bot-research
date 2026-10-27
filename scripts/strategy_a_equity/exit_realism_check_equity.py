"""Exit-realism diagnostic for Strategy A-Equity config D (pre-HOLDOUT research
trades of the 15 deployed symbols, RF and logistic). Same three exit models as
scripts/strategy_a/exit_realism_check.py, on the cached Dukascopy 1m bars,
cost 0.02 % round trip (registered)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.strategy_a.exit_realism_check import sim  # noqa: E402

SYMS = ['ADBE', 'AMZN', 'AVGO', 'BA', 'BABA', 'COST', 'CRM', 'CSCO', 'MA', 'MCD', 'MU', 'PEP', 'QCOM', 'TXN', 'V']
COST = 0.0002


def main():
    out = []
    for sym in SYMS:
        bars = pd.read_pickle(ROOT / "docs" / "_full_data_cache_a_equity" / f"{sym}_full.pkl").sort_index()
        bars.index = pd.to_datetime(bars.index, utc=True)
        o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        for model in ("rf", "logistic"):
            led = pd.read_csv(ROOT / "outputs" / "strategy_a_equity" / f"own_asset_{sym}_{model}_trades.csv",
                              parse_dates=["entry_time"])
            idx = bars.index.get_indexer(led.entry_time)
            for (_, r), e in zip(led.iterrows(), idx):
                if e < 0:
                    continue
                row = {"symbol": sym, "model": model, "ledger": r.raw_return}
                for m in ("research", "close", "intrabar"):
                    row[m] = sim(o, h, l, c, e, r.stop_distance, m)
                out.append(row)
        print(sym, flush=True)
    df = pd.DataFrame(out)
    df.to_csv(ROOT / "docs" / "exit_realism_check_equity.csv", index=False)
    print(f"\nmatched {len(df)} trades; research vs ledger mean abs diff {np.abs(df.research - df.ledger).mean():.6f}")
    for model, g in df.groupby("model"):
        for m in ("ledger", "research", "close", "intrabar"):
            net = g[m] - COST
            print(f"{model:8s} {m:9s}: mean net {100 * net.mean():+.4f}%  PF {net[net > 0].sum() / -net[net < 0].sum():.3f}  win {100 * (net > 0).mean():.0f}%")


if __name__ == "__main__":
    main()
