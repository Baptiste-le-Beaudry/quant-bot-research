"""scripts/strategy_c/experiment_c2_reversal.py — STRATEGY_ID = C,
Experiment C2 (pre-registered in docs/strategy_c/
STRATEGY_C_RESEARCH_LOG.md's "C2 -- PRE-REGISTRATION" section, frozen
2026-08-25 BEFORE any SPY data was inspected): tests H_C2 ("extreme
one-sided aggressive order flow is exhausted-liquidity-demand, not new
information -- extreme aggressive BUYING precedes a short-term negative
reversal (SHORT), extreme aggressive SELLING precedes a short-term
positive reversal (LONG)") on SPY, an independent CONFIRMATION sample
never used to discover this hypothesis (QQQ's C1 discovery sample is
never reused here).

Frozen, non-negotiable per the pre-registration: feature =
trade_flow_imbalance only (60s trailing window, quote-test aggressor
classification -- identical to C1's, no new features/filters), horizons
= 30s/60s/5min (same three as C1, no new sweep), threshold = top/bottom
DECILE computed on SPY's own distribution (one pre-registered method,
not a swept percentile), entry/exit = spread-crossing executable prices
identical in convention to C1's fwd_exec_long_ret/fwd_exec_short_ret.

Usage:
    python scripts/strategy_c/experiment_c2_reversal.py --compute-only
    python scripts/strategy_c/experiment_c2_reversal.py
"""
import gc
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.strategy_c.features import (
    attach_prevailing_quote, classify_aggressor, trade_flow_imbalance,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NORMALIZED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "normalized")
EXPERIMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "experiments")
TRADES_DAILY_DIR = os.path.join(NORMALIZED_DIR, "SPY_trades_daily")
QUOTES_DAILY_DIR = os.path.join(NORMALIZED_DIR, "SPY_mbp-1_daily")
DAILY_OBS_DIR = os.path.join(EXPERIMENTS_DIR, "c2_spy_daily_obs")

RESAMPLE_FREQ = "5s"
HORIZONS = {"30s": pd.Timedelta(seconds=30), "60s": pd.Timedelta(seconds=60), "5min": pd.Timedelta(minutes=5)}
N_DECILES = 10
N_PERMUTATIONS = 200
SESSION_OPEN = pd.Timestamp("09:30").time()
SESSION_CLOSE = pd.Timestamp("16:00").time()
NY_TZ = "America/New_York"


def _list_daily_files(daily_dir: str) -> dict:
    if not os.path.isdir(daily_dir):
        return {}
    out = {}
    for fname in os.listdir(daily_dir):
        m = re.match(r"(\d{8})\.parquet$", fname)
        if m:
            out[m.group(1)] = os.path.join(daily_dir, fname)
    return dict(sorted(out.items()))


def build_observations(trades: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Same conventions as C1's experiment_c1_raw_drift.build_observations: session-filtered,
    crossed quotes dropped, 5s last-observation-carried-forward resample capped at 60s staleness."""
    ny_idx = quotes.index.tz_convert(NY_TZ)
    in_session = (ny_idx.time >= SESSION_OPEN) & (ny_idx.time < SESSION_CLOSE)
    quotes = quotes[in_session]
    valid_quote = (quotes["bid_px_00"] > 0) & (quotes["ask_px_00"] > 0) & (quotes["bid_px_00"] <= quotes["ask_px_00"])
    quotes = quotes[valid_quote]

    mid = (quotes["bid_px_00"] + quotes["ask_px_00"]) / 2.0

    tq = attach_prevailing_quote(trades, quotes)
    tq["aggressor"] = classify_aggressor(tq)
    tfi = trade_flow_imbalance(tq, window="60s")

    obs = pd.DataFrame({"mid": mid, "bid": quotes["bid_px_00"], "ask": quotes["ask_px_00"]})
    obs_resampled = obs.resample(RESAMPLE_FREQ).last().ffill(limit=12)
    tfi_resampled = tfi.resample(RESAMPLE_FREQ).last().reindex(obs_resampled.index).ffill(limit=12)
    obs_resampled["trade_flow_imbalance"] = tfi_resampled

    ny_idx2 = obs_resampled.index.tz_convert(NY_TZ)
    in_session2 = (ny_idx2.time >= SESSION_OPEN) & (ny_idx2.time < SESSION_CLOSE)
    obs_resampled = obs_resampled[in_session2]
    return obs_resampled.dropna(subset=["mid", "trade_flow_imbalance"])


def _forward_rolling_extreme(series: pd.Series, window: str, how: str) -> pd.Series:
    rev = series.iloc[::-1]
    neg_index = pd.DatetimeIndex(-(rev.index.view("int64"))).tz_localize(None)
    rev2 = pd.Series(rev.to_numpy(), index=neg_index)
    rolled = rev2.rolling(window).max() if how == "max" else rev2.rolling(window).min()
    return pd.Series(rolled.to_numpy(), index=rev.index).iloc[::-1]


def attach_forward_returns(obs: pd.DataFrame) -> pd.DataFrame:
    """Identical convention to C1: forward MID and EXECUTABLE (spread-crossing) returns, target
    strictly after signal time via searchsorted 'left' (never at-or-before)."""
    out = obs.copy()
    mid_series, bid_series, ask_series = obs["mid"], obs["bid"], obs["ask"]
    for label, delta in HORIZONS.items():
        target_times = obs.index + delta
        pos = mid_series.index.searchsorted(target_times, side="left")
        valid = pos < len(mid_series)
        fwd_mid = np.full(len(obs), np.nan)
        fwd_bid = np.full(len(obs), np.nan)
        fwd_ask = np.full(len(obs), np.nan)
        fwd_mid[valid] = mid_series.to_numpy()[pos[valid]]
        fwd_bid[valid] = bid_series.to_numpy()[pos[valid]]
        fwd_ask[valid] = ask_series.to_numpy()[pos[valid]]

        out[f"fwd_mid_ret_{label}"] = (fwd_mid - mid_series.to_numpy()) / mid_series.to_numpy()
        out[f"fwd_exec_long_ret_{label}"] = (fwd_bid - ask_series.to_numpy()) / ask_series.to_numpy()
        out[f"fwd_exec_short_ret_{label}"] = (bid_series.to_numpy() - fwd_ask) / bid_series.to_numpy()

        fwd_max = _forward_rolling_extreme(mid_series, delta, "max")
        fwd_min = _forward_rolling_extreme(mid_series, delta, "min")
        out[f"fwd_mfe_{label}"] = (fwd_max.to_numpy() - mid_series.to_numpy()) / mid_series.to_numpy()
        out[f"fwd_mae_{label}"] = (fwd_min.to_numpy() - mid_series.to_numpy()) / mid_series.to_numpy()
    return out


def compute_daily_obs(limit: int = None) -> int:
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


def decile_side_report(obs: pd.DataFrame, horizon_label: str) -> pd.DataFrame:
    """Top/bottom DECILE of trade_flow_imbalance (computed on THIS confirmation sample's own
    distribution -- the one frozen, pre-registered method). Decile 9 (extreme aggressive buying)
    -> SHORT rule; decile 0 (extreme aggressive selling) -> LONG rule. Reported separately."""
    df = obs.dropna(subset=["trade_flow_imbalance", f"fwd_mid_ret_{horizon_label}"]).copy()
    d = pd.qcut(df["trade_flow_imbalance"], N_DECILES, labels=False, duplicates="drop")
    df["decile"] = d
    n_deciles = df["decile"].nunique()

    rows = []
    mid_col, exec_long_col, exec_short_col = (f"fwd_mid_ret_{horizon_label}",
                                               f"fwd_exec_long_ret_{horizon_label}",
                                               f"fwd_exec_short_ret_{horizon_label}")
    mfe_col, mae_col = f"fwd_mfe_{horizon_label}", f"fwd_mae_{horizon_label}"

    top = df[df["decile"] == n_deciles - 1]     # extreme aggressive BUYING -> SHORT
    bot = df[df["decile"] == 0]                  # extreme aggressive SELLING -> LONG

    for side_name, sub, exec_col, mid_sign in [
        ("SHORT (extreme buying, decile 9)", top, exec_short_col, -1.0),
        ("LONG (extreme selling, decile 0)", bot, exec_long_col, 1.0),
    ]:
        n_days = pd.Series(sub.index.tz_convert(NY_TZ).date).nunique() if len(sub) else 0
        mid_ret = sub[mid_col] * mid_sign  # sign-flipped so "positive" always means "the rule was right"
        exec_ret = sub[exec_col]
        rows.append({
            "side": side_name, "n": len(sub), "n_session_days": n_days,
            "mean_mid_ret_bps_signed": round(float(mid_ret.mean()) * 10000, 3) if len(sub) else np.nan,
            "median_mid_ret_bps_signed": round(float(mid_ret.median()) * 10000, 3) if len(sub) else np.nan,
            "win_rate_pct": round(float((mid_ret > 0).mean() * 100), 2) if len(sub) else np.nan,
            "mean_exec_ret_bps": round(float(exec_ret.mean()) * 10000, 3) if len(sub) else np.nan,
            "pct_exec_ret_positive": round(float((exec_ret > 0).mean() * 100), 2) if len(sub) else np.nan,
            "mean_mfe_bps": round(float(sub[mfe_col].mean()) * 10000, 3) if len(sub) and mfe_col in sub.columns else np.nan,
            "mean_mae_bps": round(float(sub[mae_col].mean()) * 10000, 3) if len(sub) and mae_col in sub.columns else np.nan,
        })
    return pd.DataFrame(rows)


def full_decile_report(obs: pd.DataFrame, horizon_label: str) -> pd.DataFrame:
    """Full 10-decile diagnostic (monotonicity check), not just the extremes."""
    df = obs.dropna(subset=["trade_flow_imbalance", f"fwd_mid_ret_{horizon_label}"]).copy()
    try:
        d = pd.qcut(df["trade_flow_imbalance"], N_DECILES, labels=False, duplicates="drop")
    except ValueError:
        return None
    df["decile"] = d
    rows = []
    mid_col = f"fwd_mid_ret_{horizon_label}"
    for dec, sub in df.groupby("decile", observed=True):
        rows.append({
            "decile": int(dec), "n": len(sub),
            "mean_mid_ret_bps": round(float(sub[mid_col].mean()) * 10000, 3),
            "median_mid_ret_bps": round(float(sub[mid_col].median()) * 10000, 3),
            "win_rate_pct": round(float((sub[mid_col] > 0).mean() * 100), 2),
        })
    return pd.DataFrame(rows).sort_values("decile")


def main(limit: int = None, compute_only: bool = False):
    trades_files = _list_daily_files(TRADES_DAILY_DIR)
    quotes_files = _list_daily_files(QUOTES_DAILY_DIR)
    if not trades_files or not quotes_files:
        print("SPY per-day parquet files not found. Run scripts/strategy_c/download_spy_databento.py "
              "--download-and-convert first.")
        return

    print("=" * 100)
    print("  STRATEGY C -- Experiment C2: aggressive-flow reversal, SPY CONFIRMATION sample")
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
    print(f"  distinct session-days: {n_days}  (independent-unit count per the mandate's C21)")

    os.makedirs(EXPERIMENTS_DIR, exist_ok=True)
    for horizon_label in HORIZONS:
        print(f"\n  --- trade_flow_imbalance extreme-decile reversal @ {horizon_label} (SPY) ---")
        side_report = decile_side_report(obs, horizon_label)
        print(side_report.to_string(index=False))
        side_report.to_csv(os.path.join(EXPERIMENTS_DIR, f"c2_spy_sides_{horizon_label}.csv"), index=False)

        full = full_decile_report(obs, horizon_label)
        if full is not None:
            print(f"\n  full decile table @ {horizon_label} (monotonicity check):")
            print(full.to_string(index=False))
            full.to_csv(os.path.join(EXPERIMENTS_DIR, f"c2_spy_full_deciles_{horizon_label}.csv"), index=False)

    obs.to_parquet(os.path.join(EXPERIMENTS_DIR, "c2_spy_observations.parquet"))
    print(f"\nObservations saved -> {os.path.join(EXPERIMENTS_DIR, 'c2_spy_observations.parquet')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--compute-only", action="store_true")
    args = parser.parse_args()
    main(limit=args.limit, compute_only=args.compute_only)
