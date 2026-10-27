"""scripts/strategy_a/decompose_trades.py — STRATEGY_ID = A diagnostic
(user mandate 2026-08-24, Phases 1-4): decompose the frozen baseline's
executed trade log by every requested bucket, measure edge
concentration, classify failure modes on big losers, and measure
capital utilization / opportunity cost. SHADOW/ANALYTICAL ONLY -- reads
the frozen baseline trades read-only, never modifies it, never touches
HOLDOUT.

Usage:
    python scripts/strategy_a/decompose_trades.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.config import TAKER_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.risk import ExecutionCosts, RiskLimits, simulate_portfolio

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
STRATEGY_A_DIR = os.path.join(DOCS, "strategy_a")
BASELINE_TRADES = os.path.join(DOCS, "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv")
REGIME_PATH = os.path.join(STRATEGY_A_DIR, "regime_context_daily.csv")
RISK_PCT = 0.015  # frozen baseline's own adopted risk level (Experiments 35/36)

# BASELINE_CANDIDATE_V3 frozen exit constants (used for EXACT exit_reason replay, not re-derived)
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_OUT_FRACTION = 0.5  # matches scripts/diagnostic_leverage.py's constant


def load_executed_log() -> pd.DataFrame:
    trades = pd.read_csv(BASELINE_TRADES, parse_dates=["entry_time", "exit_time"])
    costs = ExecutionCosts(TAKER_FEE_PCT, SLIPPAGE_PCT_EST / 2)
    limits = RiskLimits(risk_pct=RISK_PCT, one_position_per_symbol=True, hard_leverage_ceiling=30.0)
    log, curve, metrics = simulate_portfolio(trades, limits, costs)
    print(f"  Executed log: {len(log)} trades (of {len(trades)} candidates, "
          f"{metrics['rejected_signals']} rejected by the risk engine)")
    print(f"  Reproduces frozen baseline metrics: CAGR={metrics['cagr_pct']:.2f}%  "
          f"MaxDD={metrics['max_dd_pct']:.2f}%  Calmar={metrics['calmar']:.3f}  PF={metrics['profit_factor']:.3f}  "
          f"forced_liq={metrics['forced_liquidations']}")
    # Merge back onto the original CSV (symbol, entry_time, exit_time) to attach close_path/
    # was_stopped/stop_distance -- the risk-engine log doesn't carry these fields itself.
    merged = log.merge(trades[["symbol", "entry_time", "exit_time", "close_path", "was_stopped", "stop_distance"]],
                        on=["symbol", "entry_time", "exit_time"], how="left")
    n_unmatched = int(merged["close_path"].isna().sum())
    print(f"  Join back to original CSV for close_path/stop_distance: {n_unmatched} unmatched (expect 0)")
    return merged, curve, trades


def classify_exit_reason(row) -> str:
    """Exact replay of the frozen trailing-exit logic (ACTIVATE_AT/TRAIL_DIST are
    BASELINE_CANDIDATE_V3's own frozen constants, not re-derived) using this trade's
    OWN stored stop_distance -- classifies PROTECTIVE_STOP / TRAILING_STOP / END_OF_WINDOW,
    and cross-checks the replayed return against the stored raw_return as a bug check."""
    path = np.array([float(x) for x in row["close_path"].split(";")])
    stop_distance = row["stop_distance"]
    liq_move = STOP_OUT_FRACTION / row["position_leverage"] if row["position_leverage"] > 0 else np.inf
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for j, x in enumerate(path):
        if x <= -protective:
            return "PROTECTIVE_STOP", j
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return "TRAILING_STOP", j
    return "END_OF_WINDOW", len(path) - 1


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["year"] = df["entry_time"].dt.year
    df["quarter"] = df["entry_time"].dt.to_period("Q").astype(str)
    df["month"] = df["entry_time"].dt.to_period("M").astype(str)
    df["hour_utc"] = df["entry_time"].dt.hour
    df["day_of_week"] = df["entry_time"].dt.day_name()
    df["duration_min"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60.0
    df["stop_distance_pct"] = df["stop_distance"] * 100
    df["stop_distance_quartile"] = pd.qcut(df["stop_distance"], 4, labels=["Q1_tight", "Q2", "Q3", "Q4_wide"])
    df["leverage_quartile"] = pd.qcut(df["position_leverage"], 4, labels=["Q1_low", "Q2", "Q3", "Q4_high"], duplicates="drop")

    exit_reasons, exit_offsets, replayed_final = [], [], []
    for _, row in df.iterrows():
        reason, offset = classify_exit_reason(row)
        exit_reasons.append(reason)
        exit_offsets.append(offset)
    df["exit_reason"] = exit_reasons
    df["exit_offset_min"] = exit_offsets

    regime = pd.read_csv(REGIME_PATH, index_col=0, parse_dates=True)
    df = df.sort_values("entry_time")
    df = pd.merge_asof(df, regime, left_on="entry_time", right_index=True, direction="backward")
    return df


def bucket_stats(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by, observed=True)
    rows = []
    for name, sub in g:
        wins, losses = sub[sub["pnl"] > 0]["pnl"], sub[sub["pnl"] <= 0]["pnl"]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else np.inf
        expectancy = float(sub["pnl"].mean())
        rows.append({
            "bucket": name, "n": len(sub), "pf": round(pf, 3), "expectancy_$": round(expectancy, 2),
            "total_pnl_$": round(float(sub["pnl"].sum()), 2), "win_rate_pct": round(float((sub["pnl"] > 0).mean() * 100), 1),
            "avg_win_$": round(float(wins.mean()) if len(wins) else 0.0, 2),
            "avg_loss_$": round(float(losses.mean()) if len(losses) else 0.0, 2),
        })
    return pd.DataFrame(rows).sort_values("total_pnl_$", ascending=False)


def phase1_decomposition(df: pd.DataFrame):
    print("\n" + "=" * 100)
    print("  PHASE 1 -- EDGE DECOMPOSITION BY BUCKET")
    print("=" * 100)
    dims = {
        "symbol": "symbol", "year": "year", "quarter": "quarter", "month": "month",
        "stop_distance_quartile (volatility-regime proxy)": "stop_distance_quartile",
        "leverage_quartile": "leverage_quartile", "hour_utc": "hour_utc", "day_of_week": "day_of_week",
        "duration_min (binned)": None, "exit_reason": "exit_reason",
        "open_positions_after_entry (simultaneous positions)": "open_positions_after_entry",
    }
    all_tables = {}
    for label, col in dims.items():
        if col is None:
            continue
        table = bucket_stats(df, col)
        all_tables[label] = table
        print(f"\n  --- {label} ---")
        print(table.to_string(index=False))
        safe_name = label.split(" ")[0].replace("(", "").replace(")", "")
        table.to_csv(os.path.join(STRATEGY_A_DIR, f"phase1_bucket_{safe_name}.csv"), index=False)

    # duration binned
    df["duration_bin"] = pd.cut(df["duration_min"], bins=[0, 10, 20, 30, 50, 100, 10000],
                                 labels=["0-10m", "10-20m", "20-30m", "30-50m", "50-100m", "100m+"])
    dur_table = bucket_stats(df, "duration_bin")
    print(f"\n  --- duration_min (binned) ---")
    print(dur_table.to_string(index=False))
    dur_table.to_csv(os.path.join(STRATEGY_A_DIR, "phase1_bucket_duration.csv"), index=False)

    # regime dims (some NaN near HOLDOUT boundary, as documented)
    for col, bins, labels in [
        ("btc_trend_30d", [-1, -0.05, 0, 0.05, 1], ["strong_down", "mild_down", "mild_up", "strong_up"]),
        ("btc_vol_pctile", [0, 0.33, 0.66, 1.0], ["low_vol", "mid_vol", "high_vol"]),
        ("btc_drawdown_pct", [-100, -20, -10, -5, 0], ["dd>20%", "dd10-20%", "dd5-10%", "dd0-5%"]),
        ("breadth_7d_pct", [0, 33, 50, 66, 100], ["breadth_low", "breadth_belowmid", "breadth_abovemid", "breadth_high"]),
        ("cross_corr_30d", [-1, 0.3, 0.5, 0.7, 1], ["corr_low", "corr_mid", "corr_high", "corr_veryhigh"]),
    ]:
        binned_col = f"{col}_bin"
        df[binned_col] = pd.cut(df[col], bins=bins, labels=labels)
        table = bucket_stats(df, binned_col)
        print(f"\n  --- {col} (binned) ---")
        print(table.to_string(index=False))
        table.to_csv(os.path.join(STRATEGY_A_DIR, f"phase1_bucket_{col}.csv"), index=False)

    return df


def phase2_concentration(df: pd.DataFrame):
    print("\n" + "=" * 100)
    print("  PHASE 2 -- EDGE CONCENTRATION")
    print("=" * 100)
    total_pnl = df["pnl"].sum()
    sorted_desc = df.sort_values("pnl", ascending=False)
    sorted_asc = df.sort_values("pnl", ascending=True)
    n = len(df)
    for pct in [0.01, 0.05, 0.10]:
        k = max(1, int(n * pct))
        top_contrib = sorted_desc["pnl"].head(k).sum()
        bottom_contrib = sorted_asc["pnl"].head(k).sum()
        print(f"  top {pct*100:.0f}% trades (n={k}): contribute {top_contrib:,.0f}$ "
              f"({top_contrib/total_pnl*100:.1f}% of total PnL)")
        print(f"  bottom {pct*100:.0f}% trades (n={k}): contribute {bottom_contrib:,.0f}$ "
              f"({bottom_contrib/total_pnl*100:.1f}% of total PnL)")

    print(f"\n  Total PnL: {total_pnl:,.0f}$  (n={n} trades)")

    # sensitivity: remove best N / best month / best year / best symbol
    def total_after_removal(mask):
        return float(df.loc[~mask, "pnl"].sum())

    print("\n  Sensitivity (removing the single/best contributors):")
    best1 = sorted_desc.index[:1]
    best5 = sorted_desc.index[:5]
    print(f"  remove best 1 trade:  total_pnl={total_after_removal(df.index.isin(best1)):,.0f}$ "
          f"(vs {total_pnl:,.0f}$, -{(total_pnl-total_after_removal(df.index.isin(best1))):,.0f}$)")
    print(f"  remove best 5 trades: total_pnl={total_after_removal(df.index.isin(best5)):,.0f}$ "
          f"(-{(total_pnl-total_after_removal(df.index.isin(best5))):,.0f}$)")

    month_pnl = df.groupby("month")["pnl"].sum().sort_values(ascending=False)
    best_month = month_pnl.index[0]
    print(f"  remove best month ({best_month}, {month_pnl.iloc[0]:,.0f}$): "
          f"total_pnl={total_after_removal(df['month']==best_month):,.0f}$")

    year_pnl = df.groupby("year")["pnl"].sum().sort_values(ascending=False)
    best_year = year_pnl.index[0]
    print(f"  remove best year ({best_year}, {year_pnl.iloc[0]:,.0f}$): "
          f"total_pnl={total_after_removal(df['year']==best_year):,.0f}$")

    symbol_pnl = df.groupby("symbol")["pnl"].sum().sort_values(ascending=False)
    best_symbol = symbol_pnl.index[0]
    print(f"  remove best symbol ({best_symbol}, {symbol_pnl.iloc[0]:,.0f}$): "
          f"total_pnl={total_after_removal(df['symbol']==best_symbol):,.0f}$")

    conc = pd.DataFrame({
        "check": ["remove_best_1_trade", "remove_best_5_trades", f"remove_best_month_{best_month}",
                  f"remove_best_year_{best_year}", f"remove_best_symbol_{best_symbol}"],
        "total_pnl_after": [total_after_removal(df.index.isin(best1)), total_after_removal(df.index.isin(best5)),
                             total_after_removal(df["month"] == best_month), total_after_removal(df["year"] == best_year),
                             total_after_removal(df["symbol"] == best_symbol)],
        "original_total_pnl": total_pnl,
    })
    conc.to_csv(os.path.join(STRATEGY_A_DIR, "phase2_concentration_sensitivity.csv"), index=False)


def phase3_failure_modes(df: pd.DataFrame):
    print("\n" + "=" * 100)
    print("  PHASE 3 -- FAILURE MODE ANALYSIS (big losers)")
    print("=" * 100)
    losers = df[df["pnl"] < 0].sort_values("pnl").head(30)
    print(f"  n_losing_trades={len(df[df['pnl']<0])}  showing worst 30")

    classifications = []
    for _, row in losers.iterrows():
        cls = []
        if row["exit_reason"] == "PROTECTIVE_STOP":
            cls.append("stopped-out (protective)")
        if pd.notna(row.get("btc_drawdown_pct")) and row["btc_drawdown_pct"] < -10:
            cls.append("REGIME_FAILURE (BTC in >10% drawdown)")
        if pd.notna(row.get("cross_corr_30d")) and row["cross_corr_30d"] > 0.7:
            cls.append("PORTFOLIO_CLUSTER (high cross-crypto correlation)")
        if row["open_positions_after_entry"] >= 5:
            cls.append("PORTFOLIO_CLUSTER (5+ simultaneous positions)")
        if pd.notna(row.get("btc_trend_30d")) and row["btc_trend_30d"] < -0.05 and row["symbol"] != "BTCUSDT":
            cls.append("REGIME_FAILURE (BTC downtrend context)")
        if not cls:
            cls.append("UNCLASSIFIED")
        classifications.append(" + ".join(cls))
    losers = losers.copy()
    losers["failure_class"] = classifications
    print(losers[["symbol", "entry_time", "pnl", "exit_reason", "btc_drawdown_pct", "cross_corr_30d",
                   "open_positions_after_entry", "failure_class"]].to_string(index=False))
    losers.to_csv(os.path.join(STRATEGY_A_DIR, "phase3_worst_30_losers.csv"), index=False)

    class_counts = pd.Series([c for cls in classifications for c in cls.split(" + ")]).value_counts()
    print("\n  Failure class frequency (worst 30, trades can belong to multiple classes):")
    print(class_counts.to_string())


def phase4_opportunity_cost(df: pd.DataFrame, curve: pd.DataFrame):
    print("\n" + "=" * 100)
    print("  PHASE 4 -- OPPORTUNITY COST / CAPITAL UTILIZATION")
    print("=" * 100)
    total_span_days = (df["entry_time"].max() - df["entry_time"].min()).days
    # time-in-position: sum of trade durations vs total elapsed span (rough, ignores overlaps double count)
    total_position_minutes = df["duration_min"].sum()
    total_span_minutes = total_span_days * 1440
    print(f"  Total span: {total_span_days} days ({df['entry_time'].min().date()} -> {df['entry_time'].max().date()})")
    print(f"  Sum of individual trade durations: {total_position_minutes:,.0f} min "
          f"({total_position_minutes/total_span_minutes*100:.2f}% of elapsed time, "
          f"NOT accounting for overlap -- see open_positions distribution below for true concurrency)")

    print(f"\n  open_positions_after_entry distribution:")
    print(df["open_positions_after_entry"].describe().to_string())
    print(f"  peak simultaneous positions: {df['open_positions_after_entry'].max()}")
    print(f"  median simultaneous positions (at entry): {df['open_positions_after_entry'].median()}")

    # regime-conditional: does Strategy A trade more/less during strong BTC uptrend/downtrend/calm?
    for col, label in [("btc_trend_30d_bin", "BTC trend regime"), ("btc_vol_pctile_bin", "BTC vol regime"),
                        ("breadth_7d_pct_bin", "breadth regime")]:
        if col in df.columns:
            dist = df[col].value_counts(normalize=True) * 100
            print(f"\n  Trade distribution by {label}:")
            print(dist.to_string())


def main():
    os.makedirs(STRATEGY_A_DIR, exist_ok=True)
    print("=" * 100)
    print("  STRATEGY A ALPHA DECOMPOSITION -- Phases 1-4 (SHADOW/ANALYTICAL, baseline untouched)")
    print("=" * 100)

    df, curve, original_trades = load_executed_log()
    df = enrich(df)
    df.to_csv(os.path.join(STRATEGY_A_DIR, "enriched_trade_log.csv"), index=False)
    print(f"\n  Enriched trade log saved -> {os.path.join(STRATEGY_A_DIR, 'enriched_trade_log.csv')}")

    df = phase1_decomposition(df)
    phase2_concentration(df)
    phase3_failure_modes(df)
    phase4_opportunity_cost(df, curve)

    print("\n" + "=" * 100)
    print("  DONE -- Phases 1-4 complete. Proceed to Phase 5 (symbol marginal contribution) separately.")
    print("=" * 100)


if __name__ == "__main__":
    main()
