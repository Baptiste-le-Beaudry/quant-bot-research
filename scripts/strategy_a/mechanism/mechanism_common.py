"""scripts/strategy_a/mechanism/mechanism_common.py — shared helpers for the
Strategy A cross-market mechanism diagnostic (docs/strategy_a/
STRATEGY_A_CROSS_MARKET_MECHANISM.md). Read-only w.r.t. Strategy A itself:
imports quant_bot.features.basics.realized_vol and quant_bot.data.splits.
pre_holdout verbatim rather than reimplementing them.

shock_z definition (used identically across BTC/ETH/QQQ/SPY, Analysis B):
  shock_z_30 = close.pct_change(30) / (realized_vol(close, 30) * sqrt(30))
realized_vol(close, 30) is quant_bot's own per-BAR (1-min) return std over a
trailing 30-bar window; multiplying by sqrt(30) scales it to the same
30-minute window as the numerator return, under a random-walk variance
scaling -- this turns a 30-min raw return into a genuine local-volatility
z-score, comparable across markets with very different raw volatility.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import numpy as np
import pandas as pd

from quant_bot.features.basics import realized_vol
from quant_bot.data.splits import pre_holdout, holdout_start

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
DATA_DIR = os.path.join(REPO_ROOT, "data")
MECH_OUT_DIR = os.path.join(REPO_ROOT, "docs", "strategy_a", "mechanism")
os.makedirs(MECH_OUT_DIR, exist_ok=True)

SHOCK_WINDOW = 30  # minutes -- matches Strategy A's own horizon family (HORIZON=10, 3x for a
                    # "recent move" window on the same order as the 5*HORIZON=50min max hold)
SHOCK_BUCKETS = [-1.0, -1.5, -2.0, -2.5]  # sigma thresholds, dip/down-shock only (mean-reversion thesis)
HORIZONS = [5, 10, 20, 30, 50]  # minutes, matches Strategy A's HORIZON=10 and 5*HORIZON=50 max window


def range_pos_60(close: pd.Series, high: pd.Series, low: pd.Series) -> pd.Series:
    """Identical formula to quant_bot/features/build.py's range_pos_60 -- reproduced here
    (not imported) because build_feature_matrix requires taker_buy/sell_volume columns that
    don't exist for equities; this avoids fabricating fake columns just to reuse one line."""
    high_60, low_60 = high.rolling(60).max(), low.rolling(60).min()
    return (close - low_60) / (high_60 - low_60).replace(0, np.nan)


def shock_z(close: pd.Series, window: int = SHOCK_WINDOW) -> pd.Series:
    ret_w = close.pct_change(window)
    vol = realized_vol(close, window) * np.sqrt(window)
    return (ret_w / vol.replace(0, np.nan))


def cluster_events(event_times: pd.DatetimeIndex, gap_minutes: int = 30) -> pd.Series:
    """Assign a cluster/episode id to a sorted set of event timestamps: a new episode starts
    whenever the gap since the previous event exceeds gap_minutes. Returns a Series indexed by
    event_times giving each event's episode id (int, 0-based) -- used to report cluster-adjusted
    n (distinct episodes) per the mandate's Phase 15 event-dependence discipline."""
    ev = pd.Series(event_times).sort_values()
    gaps = ev.diff().dt.total_seconds() / 60.0
    new_episode = (gaps.isna()) | (gaps > gap_minutes)
    episode_id = new_episode.cumsum() - 1
    return pd.Series(episode_id.to_numpy(), index=ev.to_numpy())


def forward_path_metrics(close: pd.Series, event_pos: np.ndarray, max_horizon: int = 50) -> pd.DataFrame:
    """For each event (given as an integer position into `close`), compute the forward return
    path close[i+1..i+max_horizon]/close[i]-1 (bounds-checked against series end and, for
    session-based markets, against the caller's own truncation via event_pos already excluding
    events too close to a session boundary). Returns MFE, MAE, time_to_MFE, time_to_MAE, and
    future_return at each of HORIZONS (NaN where the path is shorter than that horizon)."""
    vals = close.to_numpy()
    n = len(vals)
    rows = []
    for i in event_pos:
        end = min(i + max_horizon, n - 1)
        path = vals[i:end + 1] / vals[i] - 1.0
        if len(path) < 2:
            continue
        mfe = float(np.max(path))
        mae = float(np.min(path))
        t_mfe = int(np.argmax(path))
        t_mae = int(np.argmin(path))
        row = {"mfe": mfe, "mae": mae, "time_to_mfe": t_mfe, "time_to_mae": t_mae,
               "path_len": len(path) - 1}
        for h in HORIZONS:
            row[f"fwd_ret_{h}"] = float(path[h]) if h < len(path) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def bucket_report(df: pd.DataFrame, shock_col: str, event_index: pd.DatetimeIndex,
                   buckets=SHOCK_BUCKETS, gap_minutes: int = 30) -> pd.DataFrame:
    """Per shock_z threshold bucket (events with shock_z <= threshold, i.e. dips at least that
    many sigma), report n, cluster-adjusted n (distinct episodes among events AT OR BELOW that
    threshold), distinct days, MFE/MAE (mean/median), MFE/|MAE| ratio, P(MFE>|MAE|),
    win-rate at each horizon, and skew of MFE/MAE/future returns."""
    rows = []
    for thr in buckets:
        mask = df[shock_col] <= thr
        sub = df[mask]
        if len(sub) == 0:
            rows.append({"shock_threshold": thr, "n": 0})
            continue
        idx = event_index[mask.to_numpy()] if isinstance(mask, pd.Series) else event_index[mask]
        clusters = cluster_events(pd.DatetimeIndex(idx), gap_minutes=gap_minutes)
        n_clusters = clusters.nunique()
        n_days = pd.Series(pd.DatetimeIndex(idx).date).nunique()
        mfe, mae = sub["mfe"], sub["mae"]
        row = {
            "shock_threshold": thr, "n": len(sub), "n_cluster_adjusted": int(n_clusters),
            "n_days": int(n_days),
            "mean_mfe_pct": round(float(mfe.mean()) * 100, 4),
            "median_mfe_pct": round(float(mfe.median()) * 100, 4),
            "mean_mae_pct": round(float(mae.mean()) * 100, 4),
            "median_mae_pct": round(float(mae.median()) * 100, 4),
            "mfe_over_abs_mae": round(float(mfe.mean() / abs(mae.mean())), 4) if mae.mean() != 0 else np.nan,
            "pct_mfe_gt_abs_mae": round(float((mfe > mae.abs()).mean() * 100), 2),
            "skew_mfe": round(float(mfe.skew()), 4),
            "skew_mae": round(float(mae.skew()), 4),
        }
        for h in HORIZONS:
            col = f"fwd_ret_{h}"
            if col in sub.columns:
                valid = sub[col].dropna()
                row[f"median_fwdret_{h}m_pct"] = round(float(valid.median()) * 100, 4) if len(valid) else np.nan
                row[f"winrate_{h}m_pct"] = round(float((valid > 0).mean() * 100), 2) if len(valid) else np.nan
                row[f"skew_fwdret_{h}m"] = round(float(valid.skew()), 4) if len(valid) > 2 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
