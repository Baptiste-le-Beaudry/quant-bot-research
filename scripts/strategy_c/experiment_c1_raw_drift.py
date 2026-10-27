"""scripts/strategy_c/experiment_c1_raw_drift.py — STRATEGY_ID = C,
Experiment C1 (pre-registered in docs/strategy_c/
STRATEGY_C_FEASIBILITY_REPORT.md Section 16): raw forward drift +
permutation null baseline diagnostic for quote imbalance and trade flow
imbalance on QQQ, at 30s/60s/5min horizons, bucketed by feature decile.
NO strategy, NO threshold, NO ML at this stage -- pure falsification
diagnostic, exactly matching this project's own established discipline
from the Strategy B cheap-screen work.

Reports MID-TO-MID and EXECUTABLE edge SEPARATELY (per C11): for a
hypothetical LONG at time t, executable entry = ask[t], executable exit
at horizon h = bid[t+h] (conservative: assumes closing out via a
marketable order, not passively waiting at the opposite touch).

Usage:
    python scripts/strategy_c/experiment_c1_raw_drift.py
"""
import gc
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.strategy_c.features import (
    attach_prevailing_quote, classify_aggressor, quote_imbalance, spread_pct,
    trade_flow_imbalance,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NORMALIZED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "normalized")
EXPERIMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "experiments")
TRADES_DAILY_DIR = os.path.join(NORMALIZED_DIR, "QQQ_trades_daily")
QUOTES_DAILY_DIR = os.path.join(NORMALIZED_DIR, "QQQ_mbp-1_daily")


def _list_daily_files(daily_dir: str) -> dict:
    if not os.path.isdir(daily_dir):
        return {}
    out = {}
    for fname in os.listdir(daily_dir):
        m = re.match(r"(\d{8})\.parquet$", fname)
        if m:
            out[m.group(1)] = os.path.join(daily_dir, fname)
    return dict(sorted(out.items()))

RESAMPLE_FREQ = "5s"  # observation cadence: last quote state per 5s bin -- reduces tick-level
                       # redundancy/dependence per the mandate's C21 independent-unit discipline,
                       # without discarding so much granularity that a 30s-horizon signal is lost.
HORIZONS = {"30s": pd.Timedelta(seconds=30), "60s": pd.Timedelta(seconds=60), "5min": pd.Timedelta(minutes=5)}
N_DECILES = 10
N_PERMUTATIONS = 200
SESSION_OPEN = pd.Timestamp("09:30").time()
SESSION_CLOSE = pd.Timestamp("16:00").time()
NY_TZ = "America/New_York"


def build_observations(trades: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """One row per RESAMPLE_FREQ bin: last-known quote state, quote imbalance, trade flow
    imbalance (trailing 60s), spread, and forward mid/executable prices at each horizon."""
    ny_idx = quotes.index.tz_convert(NY_TZ)
    in_session = (ny_idx.time >= SESSION_OPEN) & (ny_idx.time < SESSION_CLOSE)
    quotes = quotes[in_session]
    # Drop crossed quotes (bid > ask, ~0.0007% of rows per the C5 data audit) entirely -- not just
    # from the imbalance/spread features but from mid/bid/ask too, so a bad transient tick never
    # becomes a forward-return TARGET price either (see STRATEGY_C_RESEARCH_LOG.md C5 entry).
    valid_quote = (quotes["bid_px_00"] > 0) & (quotes["ask_px_00"] > 0) & (quotes["bid_px_00"] <= quotes["ask_px_00"])
    quotes = quotes[valid_quote]

    qi = quote_imbalance(quotes)
    sp = spread_pct(quotes)
    mid = (quotes["bid_px_00"] + quotes["ask_px_00"]) / 2.0

    tq = attach_prevailing_quote(trades, quotes)
    tq["aggressor"] = classify_aggressor(tq)
    tfi = trade_flow_imbalance(tq, window="60s")

    obs = pd.DataFrame({
        "mid": mid, "bid": quotes["bid_px_00"], "ask": quotes["ask_px_00"],
        "quote_imbalance": qi, "spread_pct": sp,
    })
    # last-observation-carried-forward RESAMPLE (causal: each bin's value is the state as of the
    # bin's own end, never a future value pulled backward).
    obs_resampled = obs.resample(RESAMPLE_FREQ).last().ffill(limit=12)  # cap staleness at ~60s
    tfi_resampled = tfi.resample(RESAMPLE_FREQ).last().reindex(obs_resampled.index).ffill(limit=12)
    obs_resampled["trade_flow_imbalance"] = tfi_resampled

    ny_idx2 = obs_resampled.index.tz_convert(NY_TZ)
    in_session2 = (ny_idx2.time >= SESSION_OPEN) & (ny_idx2.time < SESSION_CLOSE)
    obs_resampled = obs_resampled[in_session2]
    return obs_resampled.dropna(subset=["mid", "quote_imbalance"])


def _forward_rolling_extreme(series: pd.Series, window: str, how: str) -> pd.Series:
    """Forward-looking rolling max/min over [t, t+window] -- pandas' .rolling() is backward-only
    by construction, so this uses the standard negate-index trick: reverse the series, negate its
    (now-descending) index to make it ascending again, roll backward on THAT (which is forward in
    real time), then reverse back. Used only for MFE/MAE TARGET computation (Section 16's explicit
    requirement) -- targets are allowed to look forward; only FEATURES must be causal (see
    quant_bot/strategy_c/features.py's module docstring)."""
    rev = series.iloc[::-1]
    neg_index = pd.DatetimeIndex(-(rev.index.view("int64"))).tz_localize(None)
    rev2 = pd.Series(rev.to_numpy(), index=neg_index)
    rolled = rev2.rolling(window).max() if how == "max" else rev2.rolling(window).min()
    return pd.Series(rolled.to_numpy(), index=rev.index).iloc[::-1]


def attach_forward_returns(obs: pd.DataFrame) -> pd.DataFrame:
    """For each horizon: MID-TO-MID return, and EXECUTABLE return (long: enter at ask now, exit at
    bid[t+h]; short: enter at bid now, exit at ask[t+h]) -- computed via merge_asof on the FUTURE
    side (forward-looking by construction here, since this is the TARGET, not a feature -- see
    docs/strategy_c/STRATEGY_C_FEASIBILITY_REPORT.md Section 15's leakage-risk list: targets must
    be timestamped strictly AFTER the signal, verified here by using the *_at_or_after horizon
    lookup, never a value at or before the signal time)."""
    out = obs.copy()
    mid_series = obs["mid"]
    bid_series = obs["bid"]
    ask_series = obs["ask"]
    for label, delta in HORIZONS.items():
        target_times = obs.index + delta
        # searchsorted 'left' on the (already sorted, causal) index finds the first observation
        # AT OR AFTER target_times -- i.e. the forward value is never earlier than signal_time+delta.
        pos = mid_series.index.searchsorted(target_times, side="left")
        valid = pos < len(mid_series)
        fwd_mid = np.full(len(obs), np.nan)
        fwd_bid = np.full(len(obs), np.nan)
        fwd_ask = np.full(len(obs), np.nan)
        fwd_mid[valid] = mid_series.to_numpy()[pos[valid]]
        fwd_bid[valid] = bid_series.to_numpy()[pos[valid]]
        fwd_ask[valid] = ask_series.to_numpy()[pos[valid]]

        out[f"fwd_mid_ret_{label}"] = (fwd_mid - mid_series.to_numpy()) / mid_series.to_numpy()
        # executable LONG: buy at current ask, sell at future bid
        out[f"fwd_exec_long_ret_{label}"] = (fwd_bid - ask_series.to_numpy()) / ask_series.to_numpy()
        # executable SHORT: sell at current bid, buy back at future ask
        out[f"fwd_exec_short_ret_{label}"] = (bid_series.to_numpy() - fwd_ask) / bid_series.to_numpy()

        # MFE/MAE (Section 16's explicit requirement): max favorable / max adverse excursion of
        # MID price within (t, t+horizon], from a LONG perspective, relative to entry mid.
        fwd_max = _forward_rolling_extreme(mid_series, delta, "max")
        fwd_min = _forward_rolling_extreme(mid_series, delta, "min")
        out[f"fwd_mfe_{label}"] = (fwd_max.to_numpy() - mid_series.to_numpy()) / mid_series.to_numpy()
        out[f"fwd_mae_{label}"] = (fwd_min.to_numpy() - mid_series.to_numpy()) / mid_series.to_numpy()
    return out


def bucket_report(obs: pd.DataFrame, feature_col: str, horizon_label: str, permute: bool = False, seed: int = 0):
    df = obs.dropna(subset=[feature_col, f"fwd_mid_ret_{horizon_label}"]).copy()
    feature_vals = df[feature_col].to_numpy()
    if permute:
        rng = np.random.default_rng(seed)
        feature_vals = rng.permutation(feature_vals)
    try:
        df["decile"] = pd.qcut(feature_vals, N_DECILES, labels=False, duplicates="drop")
    except ValueError:
        return None
    rows = []
    mfe_col, mae_col = f"fwd_mfe_{horizon_label}", f"fwd_mae_{horizon_label}"
    for d, sub in df.groupby("decile", observed=True):
        mid_ret = sub[f"fwd_mid_ret_{horizon_label}"]
        exec_long_ret = sub[f"fwd_exec_long_ret_{horizon_label}"]
        row = {
            "decile": int(d), "n": len(sub),
            "mean_mid_ret_bps": round(float(mid_ret.mean()) * 10000, 3),
            "median_mid_ret_bps": round(float(mid_ret.median()) * 10000, 3),
            "win_rate_pct": round(float((mid_ret > 0).mean() * 100), 2),
            "mean_exec_long_ret_bps": round(float(exec_long_ret.mean()) * 10000, 3),
        }
        if mfe_col in sub.columns:
            row["mean_mfe_bps"] = round(float(sub[mfe_col].mean()) * 10000, 3)
            row["mean_mae_bps"] = round(float(sub[mae_col].mean()) * 10000, 3)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("decile")


DAILY_OBS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "experiments", "c1_daily_obs")


def compute_daily_obs(limit: int = None) -> int:
    """Process ONE DAY AT A TIME (never holding more than one day's raw trades+quotes in memory --
    this machine has ~1-1.5GB free RAM against a ~33GB raw tick dataset) and checkpoint each day's
    much smaller RESAMPLE_FREQ-resampled, forward-return-attached observation set to its own small
    Parquet file immediately -- resumable across interrupted runs, mirroring
    download_qqq_databento.py's per-day checkpointing (background jobs on this machine have been
    observed to die under memory pressure; without per-day checkpoints here, a mid-run kill would
    lose all progress since concatenation used to happen only at the very end). A trade flow
    imbalance window that starts empty at each day's open (no prior-day lookback) is an accepted,
    deliberate session-reset boundary -- consistent with this project's own session-VWAP convention
    (quant_bot/strategy_c/features.py's distance_to_session_vwap). Returns the number of NEW days
    computed this run."""
    trades_files = _list_daily_files(TRADES_DAILY_DIR)
    quotes_files = _list_daily_files(QUOTES_DAILY_DIR)
    common_dates = sorted(set(trades_files) & set(quotes_files))
    os.makedirs(DAILY_OBS_DIR, exist_ok=True)
    already_done = {f[:8] for f in os.listdir(DAILY_OBS_DIR) if f.endswith(".parquet")}
    print(f"  {len(common_dates)} common trading days found "
          f"(trades-only: {len(set(trades_files) - set(quotes_files))}, "
          f"quotes-only: {len(set(quotes_files) - set(trades_files))}); "
          f"{len(already_done)} already checkpointed")

    computed = 0
    for date_str in common_dates:
        if date_str in already_done:
            continue
        if limit is not None and computed >= limit:
            break
        trades_day = pd.read_parquet(trades_files[date_str])
        quotes_day = pd.read_parquet(quotes_files[date_str])
        obs_day = build_observations(trades_day, quotes_day)
        if len(obs_day):
            obs_day = attach_forward_returns(obs_day)
            obs_day.to_parquet(os.path.join(DAILY_OBS_DIR, f"{date_str}.parquet"))
        else:
            # still checkpoint an empty marker so this (degenerate/holiday) day isn't retried forever
            pd.DataFrame().to_parquet(os.path.join(DAILY_OBS_DIR, f"{date_str}.parquet"))
        print(f"  {date_str}: {len(obs_day):,} observations checkpointed")
        del trades_day, quotes_day, obs_day
        gc.collect()
        computed += 1
    return computed


def load_all_daily_obs() -> pd.DataFrame:
    parts = []
    for fname in sorted(os.listdir(DAILY_OBS_DIR)):
        if fname.endswith(".parquet"):
            df = pd.read_parquet(os.path.join(DAILY_OBS_DIR, fname))
            if len(df):
                parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def main(limit: int = None, compute_only: bool = False):
    trades_files = _list_daily_files(TRADES_DAILY_DIR)
    quotes_files = _list_daily_files(QUOTES_DAILY_DIR)
    if not trades_files or not quotes_files:
        print("Per-day parquet files not found. Run scripts/strategy_c/download_qqq_databento.py "
              "--download-and-convert first.")
        return

    print("=" * 100)
    print("  STRATEGY C -- Experiment C1: raw forward drift + permutation null (QQQ)")
    print("=" * 100)

    n_new = compute_daily_obs(limit=limit)
    print(f"\n  Computed {n_new} new day(s) this run.")
    if compute_only:
        return
    obs = load_all_daily_obs()
    if obs.empty:
        print("  No observations available yet.")
        return
    print(f"  observations (resampled {RESAMPLE_FREQ}, session-only): {len(obs):,}")
    n_days = pd.Series(obs.index.tz_convert(NY_TZ).date).nunique()
    print(f"  distinct session-days: {n_days}  (independent-unit count per the mandate's C21, not raw n)")

    os.makedirs(EXPERIMENTS_DIR, exist_ok=True)
    for feature_col in ["quote_imbalance", "trade_flow_imbalance"]:
        for horizon_label in HORIZONS:
            print(f"\n  --- {feature_col} vs forward return @ {horizon_label} ---")
            real = bucket_report(obs, feature_col, horizon_label, permute=False)
            if real is None:
                print("    insufficient data for decile bucketing")
                continue
            print(real.to_string(index=False))

            # Permutation null: average of N_PERMUTATIONS runs, same decile structure, imbalance
            # values shuffled -- if the REAL bucket pattern isn't meaningfully different from this,
            # the relationship is not distinguishable from chance.
            perm_means = []
            for i in range(N_PERMUTATIONS):
                perm = bucket_report(obs, feature_col, horizon_label, permute=True, seed=i)
                if perm is not None:
                    perm_means.append(perm["mean_mid_ret_bps"].to_numpy())
            if perm_means:
                perm_arr = np.array(perm_means)
                null_mean = perm_arr.mean(axis=0)
                null_std = perm_arr.std(axis=0)
                print(f"    NULL (permuted, {len(perm_means)} draws) mean_mid_ret_bps per decile: "
                      f"{np.round(null_mean, 3)}")
                print(f"    NULL std across draws: {np.round(null_std, 3)}")
                # crude z-score of the real top-vs-bottom decile spread against the null distribution
                if len(real) >= 2:
                    real_spread = real['mean_mid_ret_bps'].iloc[-1] - real['mean_mid_ret_bps'].iloc[0]
                    null_spread = perm_arr[:, -1] - perm_arr[:, 0]
                    z = (real_spread - null_spread.mean()) / (null_spread.std() + 1e-9)
                    print(f"    real top-bottom decile spread = {real_spread:.3f} bps  "
                          f"null spread mean={null_spread.mean():.3f} std={null_spread.std():.3f}  "
                          f"z={z:.2f}")

            out_path = os.path.join(EXPERIMENTS_DIR, f"c1_{feature_col}_{horizon_label}_buckets.csv")
            real.to_csv(out_path, index=False)

    obs.to_parquet(os.path.join(EXPERIMENTS_DIR, "c1_observations.parquet"))
    print(f"\nObservations saved -> {os.path.join(EXPERIMENTS_DIR, 'c1_observations.parquet')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                         help="compute at most this many NEW day-checkpoints, then exit")
    parser.add_argument("--compute-only", action="store_true",
                         help="only checkpoint daily observations, skip the bucket/null report")
    args = parser.parse_args()
    main(limit=args.limit, compute_only=args.compute_only)
