"""scripts/strategy_a_equity/run_task_d.py -- Task D fixed-exit diagnostic
(docs/strategy_a_equity/STRATEGY_A_EQUITY_TASKS_A_E.md). Reuses
configuration D's already-selected TEST entries (own_asset_{symbol}_
{model}_trades.csv, entry_time column) -- recomputes the outcome under a
20-minute and 30-minute FIXED exit (no trailing stop) directly from the
cached full price series, instead of rerunning any model. Descriptive
only: does not change the adopted configuration D.

Usage:
    python scripts/strategy_a_equity/run_task_d.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CACHE_DIR = os.path.join(REPO_ROOT, "docs", "_full_data_cache_a_equity")
OUT_DIR = os.path.join(REPO_ROOT, "outputs", "strategy_a_equity")

PRIMARY = ["AMD", "PLTR", "UBER", "INTC", "BAC", "FB", "NFLX", "GOOGL",
           "PYPL", "DIS", "JNJ", "PG", "KO", "XOM", "WMT"]
MODELS = ["rf", "logistic"]
EQUITY_COST_THRESHOLD_PCT = 0.0002  # same frozen equity cost as configuration D
FIXED_HORIZONS = [20, 30]


def pf_of(pnls: np.ndarray) -> float:
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    return float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")


def main():
    rows = []
    for symbol in PRIMARY:
        cache_path = os.path.join(CACHE_DIR, f"{symbol}_full.pkl")
        if not os.path.exists(cache_path):
            print(f"[{symbol}] SKIP -- no cached price series (run own_asset_walkforward.py first)")
            continue
        full = pd.read_pickle(cache_path)
        close = full["close"]
        n = len(close)
        for model in MODELS:
            trades_path = os.path.join(OUT_DIR, f"own_asset_{symbol}_{model}_trades.csv")
            summary_path = os.path.join(OUT_DIR, f"own_asset_{symbol}_{model}_summary.csv")
            if not os.path.exists(trades_path):
                print(f"[{symbol}/{model}] SKIP -- no config D trades export")
                continue
            trades = pd.read_csv(trades_path, parse_dates=["entry_time"])
            if len(trades) == 0:
                continue
            entry_idx = close.index.get_indexer(trades["entry_time"], method=None)
            row = {"symbol": symbol, "model": model, "n_trades": len(trades)}
            for h in FIXED_HORIZONS:
                rets = []
                for i in entry_idx:
                    if i < 0 or i + h >= n:
                        continue
                    entry_price = close.iloc[i]
                    exit_price = close.iloc[i + h]
                    ret = (exit_price / entry_price - 1.0) - EQUITY_COST_THRESHOLD_PCT
                    rets.append(ret)
                rets = np.array(rets)
                if len(rets) == 0:
                    row[f"n_{h}m"] = 0
                    continue
                row[f"n_{h}m"] = len(rets)
                row[f"pf_{h}m"] = round(pf_of(rets), 3)
                row[f"expectancy_{h}m"] = round(float(rets.mean()) * 100, 4)
                row[f"win_rate_{h}m"] = round(float((rets > 0).mean()) * 100, 1)
            if os.path.exists(summary_path):
                summ = pd.read_csv(summary_path)
                traded = summ[summ.get("n_trades", 0) > 0]
                if len(traded):
                    row["actual_median_pf_exec"] = round(traded["profit_factor_exec"].replace([np.inf], np.nan).median(), 3)
            rows.append(row)
            print(f"[{symbol}/{model}] n={row['n_trades']} "
                  f"PF20={row.get('pf_20m','-')} PF30={row.get('pf_30m','-')} "
                  f"actual(trailing)={row.get('actual_median_pf_exec','-')}")

    res = pd.DataFrame(rows)
    out_path = os.path.join(OUT_DIR, "TASK_D_fixed_exit_results.csv")
    res.to_csv(out_path, index=False)
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
