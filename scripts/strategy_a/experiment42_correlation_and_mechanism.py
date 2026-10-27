"""scripts/strategy_a/experiment42_correlation_and_mechanism.py —
STRATEGY_ID = A, Experiment 42, Steps 4-5: for BTC/ETH/BNB/LTC, measure
trade-PnL correlation with the rest of the portfolio, loss correlation,
simultaneous protective stops, drawdown-period performance, and the
per-fold protective-stop-vs-trailing-stop mechanism breakdown. SHADOW/
ANALYTICAL ONLY.

Usage:
    python scripts/strategy_a/experiment42_correlation_and_mechanism.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from scripts.walk_forward_engine import build_folds, SAFE_END

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
STRATEGY_A_DIR = os.path.join(DOCS, "strategy_a")
ENRICHED_LOG_PATH = os.path.join(STRATEGY_A_DIR, "enriched_trade_log.csv")
PRIORITY_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "LTCUSDT"]
DATA_START = pd.Timestamp("2019-11-27", tz="UTC")


def main():
    print("=" * 100)
    print("  STRATEGY A -- Experiment 42 Steps 4-5: correlation + stop-mechanism analysis")
    print("=" * 100)

    df = pd.read_csv(ENRICHED_LOG_PATH, parse_dates=["entry_time", "exit_time"])

    # STEP 4a: daily PnL correlation between each priority symbol and the REST of the portfolio.
    print("\n  STEP 4a -- daily PnL correlation: symbol X vs REST of portfolio")
    df["date"] = df["entry_time"].dt.date
    daily_symbol_pnl = df.groupby(["date", "symbol"])["pnl"].sum().unstack(fill_value=0.0)
    daily_symbol_pnl.index = pd.to_datetime(daily_symbol_pnl.index)
    corr_rows = []
    for sym in PRIORITY_SYMBOLS:
        if sym not in daily_symbol_pnl.columns:
            continue
        rest = daily_symbol_pnl.drop(columns=[sym]).sum(axis=1)
        corr = daily_symbol_pnl[sym].corr(rest)
        # loss-day correlation: correlation restricted to days where the REST of the portfolio lost money
        rest_loss_days = rest[rest < 0].index
        loss_corr_n = len(rest_loss_days)
        sym_pnl_on_rest_loss_days = daily_symbol_pnl.loc[daily_symbol_pnl.index.isin(rest_loss_days), sym]
        pct_sym_also_negative = float((sym_pnl_on_rest_loss_days < 0).mean() * 100) if loss_corr_n else np.nan
        corr_rows.append({
            "symbol": sym, "daily_pnl_corr_vs_rest": round(corr, 3),
            "rest_loss_days": loss_corr_n,
            "pct_of_rest_loss_days_where_symbol_ALSO_lost": round(pct_sym_also_negative, 1),
        })
    corr_df = pd.DataFrame(corr_rows)
    print(corr_df.to_string(index=False))
    corr_df.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_pnl_correlation.csv"), index=False)

    # STEP 4b: simultaneous protective stops -- for each priority symbol's protective stops, what
    # fraction occur within 90min of ANOTHER symbol's protective stop (reusing the alpha
    # decomposition's own definition).
    print("\n  STEP 4b -- simultaneous protective stops (within 90min of a DIFFERENT symbol's stop)")
    stops = df[df["exit_reason"] == "PROTECTIVE_STOP"].sort_values("entry_time").reset_index(drop=True)
    sim_rows = []
    for sym in PRIORITY_SYMBOLS:
        sym_stops = stops[stops["symbol"] == sym]
        n_simultaneous = 0
        for _, row in sym_stops.iterrows():
            window = stops[(stops["entry_time"] >= row["entry_time"] - pd.Timedelta(minutes=90)) &
                            (stops["entry_time"] <= row["entry_time"] + pd.Timedelta(minutes=90)) &
                            (stops["symbol"] != sym)]
            if len(window) > 0:
                n_simultaneous += 1
        pct = n_simultaneous / len(sym_stops) * 100 if len(sym_stops) else np.nan
        sim_rows.append({"symbol": sym, "n_protective_stops": len(sym_stops),
                          "n_simultaneous_with_other_symbol": n_simultaneous,
                          "pct_simultaneous": round(pct, 1)})
    sim_df = pd.DataFrame(sim_rows)
    print(sim_df.to_string(index=False))
    sim_df.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_simultaneous_stops.csv"), index=False)

    # STEP 4c: performance during PORTFOLIO drawdown periods (using the equity curve from the
    # frozen baseline's own executed log -- approximate via cumulative pnl of ALL trades).
    print("\n  STEP 4c -- symbol performance during PORTFOLIO drawdown episodes")
    all_daily_pnl = daily_symbol_pnl.sum(axis=1).sort_index()
    cum_pnl = all_daily_pnl.cumsum()
    running_max = cum_pnl.cummax()
    in_drawdown = (cum_pnl < running_max * 0.98) if running_max.max() > 0 else pd.Series(False, index=cum_pnl.index)
    # simpler: drawdown = cum_pnl below its own running max by ANY amount
    in_dd_mask = cum_pnl < running_max
    dd_dates = set(cum_pnl.index[in_dd_mask])
    dd_perf_rows = []
    for sym in PRIORITY_SYMBOLS:
        if sym not in daily_symbol_pnl.columns:
            continue
        sym_daily = daily_symbol_pnl[sym]
        in_dd_pnl = sym_daily[sym_daily.index.isin(dd_dates)].sum()
        not_dd_pnl = sym_daily[~sym_daily.index.isin(dd_dates)].sum()
        dd_perf_rows.append({"symbol": sym, "pnl_during_portfolio_drawdown": round(in_dd_pnl, 0),
                              "pnl_outside_drawdown": round(not_dd_pnl, 0),
                              "pct_of_total_pnl_lost_during_dd": round(in_dd_pnl / (in_dd_pnl + not_dd_pnl) * 100, 1)
                              if (in_dd_pnl + not_dd_pnl) != 0 else np.nan})
    dd_perf_df = pd.DataFrame(dd_perf_rows)
    print(dd_perf_df.to_string(index=False))
    dd_perf_df.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_drawdown_period_performance.csv"), index=False)

    # STEP 5: per-fold stop-mechanism breakdown for each priority symbol.
    print("\n  STEP 5 -- per-fold protective-stop / trailing-stop mechanism breakdown")
    folds = build_folds(DATA_START, SAFE_END)
    mech_rows = []
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        fold_trades = df[(df["entry_time"] >= t0) & (df["entry_time"] < test_end)]
        for sym in PRIORITY_SYMBOLS:
            sub = fold_trades[fold_trades["symbol"] == sym]
            if len(sub) == 0:
                continue
            trail_pnl = sub[sub["exit_reason"] == "TRAILING_STOP"]["pnl"].sum()
            stop_pnl = sub[sub["exit_reason"] == "PROTECTIVE_STOP"]["pnl"].sum()
            net_pnl = sub["pnl"].sum()
            ratio = abs(stop_pnl) / abs(net_pnl) if net_pnl != 0 else np.nan
            mech_rows.append({
                "fold": fold_i, "symbol": sym, "n": len(sub),
                "trailing_stop_gross_profit": round(trail_pnl, 0), "protective_stop_gross_loss": round(stop_pnl, 0),
                "net_pnl": round(net_pnl, 0), "protective_loss_over_net_profit_ratio": round(ratio, 2),
                "protective_stop_rate_pct": round((sub["exit_reason"] == "PROTECTIVE_STOP").mean() * 100, 1),
            })
    mech_df = pd.DataFrame(mech_rows)
    mech_df.to_csv(os.path.join(STRATEGY_A_DIR, "experiment42_stop_mechanism_by_fold.csv"), index=False)
    for sym in PRIORITY_SYMBOLS:
        sub = mech_df[mech_df["symbol"] == sym]
        print(f"\n  {sym} protective_stop_rate_pct by fold: {list(sub['protective_stop_rate_pct'])}")
        print(f"    median={sub['protective_stop_rate_pct'].median():.1f}%  "
              f"std={sub['protective_stop_rate_pct'].std():.1f}pp  "
              f"(low std relative to median = consistent mechanism across folds; high std = "
              f"dominated by a subset of periods)")


if __name__ == "__main__":
    main()
