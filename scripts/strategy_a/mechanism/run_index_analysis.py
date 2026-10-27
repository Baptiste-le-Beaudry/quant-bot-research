"""scripts/strategy_a/mechanism/run_index_analysis.py — Strategy A cross-
market mechanism diagnostic, INDEX side (QQQ/SPY). Reads the 1-min bars
built by build_index_bars.py. Read-only w.r.t. Strategy C's tick data.

IMPORTANT session-boundary guard: index bars are RTH-only (09:30-16:00 NY),
concatenated day-by-day -- the last bar of one day is NOT temporally
adjacent to the first bar of the next day. A naive forward-window slice
across that boundary would silently splice a synthetic overnight return
into the path. This script's forward_path_metrics_session_aware() ONLY
uses bars from the SAME session-day as the event, truncating (not
fabricating) the horizon at session close, and drops events with fewer
than 2 remaining same-day bars.

Produces the index-side counterparts to run_crypto_analysis.py's outputs:
  1. Analysis A-index-approx (structural filter only, NO ML gate -- see
     module docstring in mechanism_common.py / the report for why).
  2. Analysis B (generic normalized dip), identical shock_z formula.
  3. Time-of-day (NY session sub-period) diagnostic.
  4. Volume-regime diagnostic.
  5. Cost-scale (median rebound vs. median bid/ask spread, NOT a fixed fee
     estimate like crypto -- spread is directly measured from the tick data).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from mechanism_common import shock_z, range_pos_60, cluster_events, bucket_report, MECH_OUT_DIR, SHOCK_BUCKETS, HORIZONS
from quant_bot.features.basics import realized_vol

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
NY_TZ = "America/New_York"
SYMBOLS = ["QQQ", "SPY"]
SUBPERIODS = [
    ("09:30-10:00", "09:30", "10:00"), ("10:00-12:00", "10:00", "12:00"),
    ("12:00-14:00", "12:00", "14:00"), ("14:00-15:30", "14:00", "15:30"),
    ("15:30-16:00", "15:30", "16:00"),
]


def load_bars(symbol: str) -> pd.DataFrame:
    return pd.read_parquet(os.path.join(MECH_OUT_DIR, f"{symbol}_1min_bars.parquet"))


def forward_path_metrics_session_aware(bars: pd.DataFrame, event_pos: np.ndarray, max_horizon: int = 50) -> pd.DataFrame:
    close = bars["close"].to_numpy()
    ny_date = bars.index.tz_convert(NY_TZ).date
    n = len(close)
    rows = []
    for i in event_pos:
        today = ny_date[i]
        end = i
        while end + 1 < n and ny_date[end + 1] == today and (end - i) < max_horizon:
            end += 1
        path = close[i:end + 1] / close[i] - 1.0
        if len(path) < 2:
            continue  # truncated at session close with <2 bars remaining -- dropped, not faked
        mfe, mae = float(np.max(path)), float(np.min(path))
        row = {"mfe": mfe, "mae": mae, "time_to_mfe": int(np.argmax(path)),
               "time_to_mae": int(np.argmin(path)), "path_len": len(path) - 1,
               "truncated": (end - i) < max_horizon}
        for h in HORIZONS:
            row[f"fwd_ret_{h}"] = float(path[h]) if h < len(path) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def analysis_a_index_approx(symbol: str, bars: pd.DataFrame) -> pd.DataFrame:
    close, high, low = bars["close"], bars["high"], bars["low"]
    rp60 = range_pos_60(close, high, low)
    rv30 = realized_vol(close, 30)
    valid = rp60.notna() & rv30.notna()
    rp_med, rv_med = rp60[valid].median(), rv30[valid].median()
    qualify = valid & (rp60 < rp_med) & (rv30 > rv_med)
    raw_n = int(qualify.sum())

    qualify_times = bars.index[qualify.to_numpy()]
    clusters = cluster_events(pd.DatetimeIndex(qualify_times), gap_minutes=10)
    # keep only the FIRST bar of each cluster/episode as the "event" (adjacent qualifying
    # minutes are highly dependent -- see mandate Phase 15)
    first_per_cluster = clusters.groupby(clusters.to_numpy()).apply(lambda s: s.index.min())
    event_times = pd.DatetimeIndex(sorted(first_per_cluster.to_numpy()))
    event_pos = bars.index.get_indexer(event_times)
    event_pos = event_pos[event_pos >= 0]

    print(f"  [{symbol}] Analysis A-index-approx: raw_n={raw_n} qualifying bars -> "
          f"{len(event_pos)} cluster-first events (self-referential median split, NO ML gate)")

    fpm = forward_path_metrics_session_aware(bars, event_pos, max_horizon=50)
    fpm["shock_z"] = shock_z(close).to_numpy()[event_pos][: len(fpm)]
    ev_idx = bars.index[event_pos][: len(fpm)]

    report = bucket_report(fpm, "shock_z", pd.DatetimeIndex(ev_idx), gap_minutes=10)
    report.insert(0, "symbol", symbol)
    report.insert(1, "population", "A_index_approx_structural_filter_only_NO_ML")
    report.insert(2, "raw_qualifying_bars", raw_n)
    report.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_analysis_a_index_approx.csv"), index=False)
    return report, fpm.assign(entry_time=ev_idx[: len(fpm)])


def analysis_b(symbol: str, bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    close = bars["close"]
    sz = shock_z(close)
    thr = SHOCK_BUCKETS[0]
    event_mask = sz <= thr
    event_pos = np.flatnonzero(event_mask.to_numpy())
    print(f"  [{symbol}] Analysis B: {len(event_pos):,} raw minute-events with shock_z<={thr} "
          f"(of {len(bars):,} bars)")

    fpm = forward_path_metrics_session_aware(bars, event_pos, max_horizon=50)
    fpm["shock_z"] = sz.to_numpy()[event_pos][: len(fpm)]
    ev_idx = bars.index[event_pos][: len(fpm)]

    report = bucket_report(fpm, "shock_z", pd.DatetimeIndex(ev_idx), gap_minutes=30)
    report.insert(0, "symbol", symbol)
    report.insert(1, "population", "B_generic_normalized_dip")
    report.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_analysis_b.csv"), index=False)
    return report, fpm.assign(entry_time=ev_idx[: len(fpm)])


def time_of_day(symbol: str, fpm_full: pd.DataFrame, thr: float = -1.5) -> pd.DataFrame:
    sub = fpm_full[fpm_full["shock_z"] <= thr].copy()
    ny_idx = pd.DatetimeIndex(sub["entry_time"]).tz_convert(NY_TZ)
    rows = []
    for label, start_str, end_str in SUBPERIODS:
        start_t, end_t = pd.Timestamp(start_str).time(), pd.Timestamp(end_str).time()
        mask = (ny_idx.time >= start_t) & (ny_idx.time < end_t)
        g = sub[mask]
        if len(g) == 0:
            rows.append({"symbol": symbol, "subperiod": label, "n": 0})
            continue
        rows.append({
            "symbol": symbol, "subperiod": label, "n": len(g),
            "mean_mfe_pct": round(float(g["mfe"].mean()) * 100, 4),
            "mean_mae_pct": round(float(g["mae"].mean()) * 100, 4),
            "median_fwd_ret_30m_pct": round(float(g["fwd_ret_30"].dropna().median()) * 100, 4) if g["fwd_ret_30"].notna().any() else np.nan,
        })
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_time_of_day.csv"), index=False)
    return out


def volume_regime(symbol: str, bars: pd.DataFrame, fpm_full: pd.DataFrame, thr: float = -1.5) -> pd.DataFrame:
    rel_vol = (bars["volume"] / bars["volume"].rolling(60).mean()).rename("rel_volume")
    sub = fpm_full[fpm_full["shock_z"] <= thr].copy()
    joined = pd.merge_asof(sub.sort_values("entry_time"), rel_vol.sort_index().to_frame(),
                            left_on="entry_time", right_index=True, direction="backward")
    joined = joined.dropna(subset=["rel_volume"])
    if len(joined) < 3:
        return pd.DataFrame()
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


def cost_scale(symbol: str, bars: pd.DataFrame, report_b: pd.DataFrame) -> pd.DataFrame:
    median_spread_pct = float(bars["median_spread_pct"].median()) * 100
    rows = []
    for _, r in report_b.iterrows():
        rows.append({
            "symbol": symbol, "shock_threshold": r["shock_threshold"],
            "median_mfe_pct": r.get("median_mfe_pct"),
            "median_bidask_spread_pct": round(median_spread_pct, 5),
            "median_mfe_over_spread": round(r["median_mfe_pct"] / median_spread_pct, 2) if pd.notna(r.get("median_mfe_pct")) and median_spread_pct else np.nan,
        })
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(MECH_OUT_DIR, f"{symbol}_cost_scale.csv"), index=False)
    return out


def main():
    all_a, all_b, all_tod, all_vol, all_cost = [], [], [], [], []
    for symbol in SYMBOLS:
        print(f"=== {symbol} ===")
        bars = load_bars(symbol)
        report_a, fpm_a = analysis_a_index_approx(symbol, bars)
        all_a.append(report_a)
        report_b, fpm_b = analysis_b(symbol, bars)
        all_b.append(report_b)
        all_tod.append(time_of_day(symbol, fpm_b))
        vr = volume_regime(symbol, bars, fpm_b)
        if len(vr):
            all_vol.append(vr)
        all_cost.append(cost_scale(symbol, bars, report_b))

    pd.concat(all_a).to_csv(os.path.join(MECH_OUT_DIR, "index_analysis_a_combined.csv"), index=False)
    pd.concat(all_b).to_csv(os.path.join(MECH_OUT_DIR, "index_analysis_b_combined.csv"), index=False)
    pd.concat(all_tod).to_csv(os.path.join(MECH_OUT_DIR, "index_time_of_day_combined.csv"), index=False)
    if all_vol:
        pd.concat(all_vol).to_csv(os.path.join(MECH_OUT_DIR, "index_volume_regime_combined.csv"), index=False)
    pd.concat(all_cost).to_csv(os.path.join(MECH_OUT_DIR, "index_cost_scale_combined.csv"), index=False)
    print("\nDONE -- index side combined CSVs written to", MECH_OUT_DIR)


if __name__ == "__main__":
    main()
