"""scripts/strategy_a/mechanism/run_crypto_analysis.py — Strategy A cross-
market mechanism diagnostic, CRYPTO side (BTC/ETH). Read-only w.r.t.
Strategy A: loads the FROZEN trade log and raw pre-HOLDOUT klines, writes
only to docs/strategy_a/mechanism/.

Produces:
  1. Analysis A (EXACT Strategy-A trades): MFE/MAE/future-return/rebound
     stats for the real, frozen BTC/ETH trade population, using each
     trade's own `close_path` (raw, unstopped path) -- bucketed by the
     entry's own shock_z (looked up via merge_asof, causal).
  2. Analysis B (generic normalized dip): shock_z-bucketed MFE/MAE/future
     -return population from the FULL pre-HOLDOUT BTC/ETH 1-min history
     (independent of Strategy A's model/filters).
  3. Year-regime stability (2022/2023/2024/2025-partial) on the Analysis B
     population.
  4. 24-hour-UTC-bucket diagnostic on the Analysis B population.
  5. Volume-regime diagnostic (high/normal/low relative volume) on events.
  6. Cost-scale comparison (typical rebound vs typical round-trip cost).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from mechanism_common import (
    shock_z, cluster_events, forward_path_metrics, bucket_report, MECH_OUT_DIR, SHOCK_BUCKETS, HORIZONS,
)
from quant_bot.data.splits import pre_holdout, holdout_start
from quant_bot.features.build import build_feature_matrix
from quant_bot.config import ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, COST_THRESHOLD_PCT

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
CACHE_DIR = os.path.join(REPO_ROOT, "docs", "_full_data_cache")
TRADES_CSV = os.path.join(REPO_ROOT, "docs", "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv")
SYMBOLS = ["BTCUSDT", "ETHUSDT"]


def load_klines(symbol: str) -> pd.DataFrame:
    path = os.path.join(CACHE_DIR, f"{symbol}_full.pkl")
    df = pd.read_pickle(path)
    df = pre_holdout(df, symbol)
    return df


# ---------------------------------------------------------------------
# 1. Analysis A: real frozen Strategy A trades (close_path already computed)
# ---------------------------------------------------------------------

def analysis_a(symbol: str, feats: pd.DataFrame) -> pd.DataFrame:
    trades = pd.read_csv(TRADES_CSV, usecols=["symbol", "entry_time", "raw_return", "was_stopped", "close_path"])
    trades = trades[trades["symbol"] == symbol].copy()
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)

    # VERIFY BEFORE BELIEVE: entry_time must be strictly pre-HOLDOUT already (by construction of
    # the frozen walk-forward TEST folds) -- confirm, don't assume.
    hs = holdout_start(symbol)
    n_post_holdout = int((trades["entry_time"] >= hs).sum())
    print(f"  [{symbol}] Analysis A: {len(trades)} trades loaded, HOLDOUT check: "
          f"{n_post_holdout} entries at/after {hs.date()} (expected 0)")
    trades = trades[trades["entry_time"] < hs]

    def parse_path_metrics(path_str: str) -> dict:
        path = np.array([float(x) for x in path_str.split(";")])
        mfe, mae = float(np.max(path)), float(np.min(path))
        row = {"mfe": mfe, "mae": mae, "time_to_mfe": int(np.argmax(path)),
               "time_to_mae": int(np.argmin(path)), "path_len": len(path) - 1}
        for h in HORIZONS:
            row[f"fwd_ret_{h}"] = float(path[h]) if h < len(path) else np.nan
        return row

    parsed = trades["close_path"].apply(parse_path_metrics).apply(pd.Series)
    trades = pd.concat([trades.reset_index(drop=True), parsed.reset_index(drop=True)], axis=1)

    # attach shock_z at entry (causal, backward-looking -- shock_z at t uses only data <= t)
    sz = shock_z(feats["_close"]).rename("shock_z")
    trades = pd.merge_asof(trades.sort_values("entry_time"), sz.sort_index().to_frame(),
                            left_on="entry_time", right_index=True, direction="backward")

    report = bucket_report(trades, "shock_z", pd.DatetimeIndex(trades["entry_time"]))
    report.insert(0, "symbol", symbol)
    report.insert(1, "population", "A_exact_strategy_a_trades")

    out_path = os.path.join(MECH_OUT_DIR, f"{symbol}_analysis_a.csv")
    report.to_csv(out_path, index=False)
    trades.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_analysis_a_raw_trades.csv"), index=False)
    print(f"  [{symbol}] Analysis A report -> {out_path}  (n={len(trades)})")
    return report


# ---------------------------------------------------------------------
# 2. Analysis B: generic normalized dip, full pre-HOLDOUT history
# ---------------------------------------------------------------------

def analysis_b(symbol: str, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    close = df["close"]
    sz = shock_z(close)
    thr = SHOCK_BUCKETS[0]
    event_mask = sz <= thr  # use the loosest (most inclusive) threshold to build ONE forward-metrics
                             # population; tighter buckets are then just sub-filters of this same set
                             # (avoids recomputing forward_path_metrics per threshold)
    event_pos = np.flatnonzero(event_mask.to_numpy())
    print(f"  [{symbol}] Analysis B: {len(event_pos):,} raw minute-events with shock_z<={thr} "
          f"(of {len(df):,} bars)")

    fpm = forward_path_metrics(close, event_pos, max_horizon=50)
    fpm["shock_z"] = sz.to_numpy()[event_pos][: len(fpm)]
    event_index = close.index[event_pos][: len(fpm)]

    report = bucket_report(fpm, "shock_z", pd.DatetimeIndex(event_index))
    report.insert(0, "symbol", symbol)
    report.insert(1, "population", "B_generic_normalized_dip")

    out_path = os.path.join(MECH_OUT_DIR, f"{symbol}_analysis_b.csv")
    report.to_csv(out_path, index=False)

    fpm_full = fpm.copy()
    fpm_full["entry_time"] = event_index
    return report, fpm_full


# ---------------------------------------------------------------------
# 3. Year-regime stability (Analysis B population, tightest common bucket = -1.5 sigma)
# ---------------------------------------------------------------------

def year_regime_stability(symbol: str, fpm_full: pd.DataFrame, year_thr: float = -1.5) -> pd.DataFrame:
    sub = fpm_full[fpm_full["shock_z"] <= year_thr].copy()
    sub["year"] = pd.DatetimeIndex(sub["entry_time"]).year
    rows = []
    for yr, g in sub.groupby("year"):
        clusters = cluster_events(pd.DatetimeIndex(g["entry_time"]), gap_minutes=30)
        rows.append({
            "symbol": symbol, "year": int(yr), "n": len(g), "n_cluster_adjusted": int(clusters.nunique()),
            "mean_mfe_pct": round(float(g["mfe"].mean()) * 100, 4),
            "mean_mae_pct": round(float(g["mae"].mean()) * 100, 4),
            "mfe_over_abs_mae": round(float(g["mfe"].mean() / abs(g["mae"].mean())), 4) if g["mae"].mean() != 0 else np.nan,
            "median_fwd_ret_30m_pct": round(float(g["fwd_ret_30"].dropna().median()) * 100, 4) if g["fwd_ret_30"].notna().any() else np.nan,
        })
    out = pd.DataFrame(rows).sort_values("year")
    out.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_year_regime_stability.csv"), index=False)
    return out


# ---------------------------------------------------------------------
# 4. 24-hour UTC bucket diagnostic
# ---------------------------------------------------------------------

def hour_of_day(symbol: str, fpm_full: pd.DataFrame, thr: float = -1.5) -> pd.DataFrame:
    sub = fpm_full[fpm_full["shock_z"] <= thr].copy()
    sub["hour_utc"] = pd.DatetimeIndex(sub["entry_time"]).hour
    rows = []
    for hr, g in sub.groupby("hour_utc"):
        rows.append({
            "symbol": symbol, "hour_utc": int(hr), "n": len(g),
            "mean_mfe_pct": round(float(g["mfe"].mean()) * 100, 4),
            "mean_mae_pct": round(float(g["mae"].mean()) * 100, 4),
            "median_fwd_ret_30m_pct": round(float(g["fwd_ret_30"].dropna().median()) * 100, 4) if g["fwd_ret_30"].notna().any() else np.nan,
        })
    out = pd.DataFrame(rows).sort_values("hour_utc")
    out.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_hour_of_day.csv"), index=False)
    return out


# ---------------------------------------------------------------------
# 5. Volume regime diagnostic
# ---------------------------------------------------------------------

def volume_regime(symbol: str, df: pd.DataFrame, fpm_full: pd.DataFrame, thr: float = -1.5) -> pd.DataFrame:
    rel_vol = (df["volume"] / df["volume"].rolling(60).mean()).rename("rel_volume")
    sub = fpm_full[fpm_full["shock_z"] <= thr].copy()
    joined = pd.merge_asof(sub.sort_values("entry_time"), rel_vol.sort_index().to_frame(),
                            left_on="entry_time", right_index=True, direction="backward")
    joined["vol_bucket"] = pd.qcut(joined["rel_volume"], 3, labels=["low", "normal", "high"], duplicates="drop")
    rows = []
    for b, g in joined.groupby("vol_bucket", observed=True):
        rows.append({
            "symbol": symbol, "vol_bucket": str(b), "n": len(g),
            "mean_mfe_pct": round(float(g["mfe"].mean()) * 100, 4),
            "mean_mae_pct": round(float(g["mae"].mean()) * 100, 4),
            "median_fwd_ret_30m_pct": round(float(g["fwd_ret_30"].dropna().median()) * 100, 4) if g["fwd_ret_30"].notna().any() else np.nan,
        })
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_volume_regime.csv"), index=False)
    return out


# ---------------------------------------------------------------------
# 6. Cost scale
# ---------------------------------------------------------------------

def cost_scale(symbol: str, report_b: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in report_b.iterrows():
        rows.append({
            "symbol": symbol, "shock_threshold": r["shock_threshold"],
            "median_mfe_pct": r.get("median_mfe_pct"),
            "round_trip_cost_pct": round(COST_THRESHOLD_PCT * 100, 4),
            "median_mfe_over_cost": round(r["median_mfe_pct"] / (COST_THRESHOLD_PCT * 100), 2) if pd.notna(r.get("median_mfe_pct")) else np.nan,
        })
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_cost_scale.csv"), index=False)
    return out


def main():
    all_a, all_b, all_year, all_hour, all_vol, all_cost = [], [], [], [], [], []
    for symbol in SYMBOLS:
        print(f"=== {symbol} ===")
        df = load_klines(symbol)
        feats_close = df[["close"]].rename(columns={"close": "_close"})
        report_a = analysis_a(symbol, feats_close)
        all_a.append(report_a)

        report_b, fpm_full = analysis_b(symbol, df)
        all_b.append(report_b)

        all_year.append(year_regime_stability(symbol, fpm_full))
        all_hour.append(hour_of_day(symbol, fpm_full))
        all_vol.append(volume_regime(symbol, df, fpm_full))
        all_cost.append(cost_scale(symbol, report_b))

    pd.concat(all_a).to_csv(os.path.join(MECH_OUT_DIR, "crypto_analysis_a_combined.csv"), index=False)
    pd.concat(all_b).to_csv(os.path.join(MECH_OUT_DIR, "crypto_analysis_b_combined.csv"), index=False)
    pd.concat(all_year).to_csv(os.path.join(MECH_OUT_DIR, "crypto_year_regime_combined.csv"), index=False)
    pd.concat(all_hour).to_csv(os.path.join(MECH_OUT_DIR, "crypto_hour_of_day_combined.csv"), index=False)
    pd.concat(all_vol).to_csv(os.path.join(MECH_OUT_DIR, "crypto_volume_regime_combined.csv"), index=False)
    pd.concat(all_cost).to_csv(os.path.join(MECH_OUT_DIR, "crypto_cost_scale_combined.csv"), index=False)
    print("\nDONE -- crypto side combined CSVs written to", MECH_OUT_DIR)


if __name__ == "__main__":
    main()
