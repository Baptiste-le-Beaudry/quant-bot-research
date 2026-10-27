"""
scripts/multi_crypto_walkforward.py — multi-crypto expansion plan, Etapes
7-9: full walk-forward (INDEPENDENT single-symbol model, NOT jointly
trained with BTC/ETH -- matches how Test B/multi_crypto_screen.py already
screened each symbol on its own TRAIN, and nasdaq_baseline_test.py's
single-market precedent) + trade export (same schema as
docs/walk_forward_v3_trades_export.csv, for later portfolio construction)
+ stress test, all computed from the SAME per-fold model fit in one pass
(fitting the RF per fold is the expensive step -- no reason to pay it three
times like the original BTC/ETH scripts did across separate files).

Expanding-TRAIN walk-forward, same shape as scripts/walk_forward_engine.py,
but INITIAL_TRAIN_MONTHS/TEST_MONTHS/STEP_MONTHS adapt to each symbol's own
available pre-HOLDOUT history (BTC/ETH-standard 24/3/3 if there's enough
history for it; otherwise scaled down proportionally, printed explicitly --
per the plan's own "Etape 7" instruction not to force a fold count that
doesn't fit the data). HOLDOUT = last 20% of this symbol's own history by
bar count (same boundary multi_crypto_screen.py's Test B used) -- SAFE_END
for the walk-forward folds, never crossed, never touched here.

Resumable via --max-folds N (checkpoint CSVs, one per output kind).

Per-symbol OPTIMIZATION support (multi-crypto expansion plan, post-
generalization-confirmation phase -- user's 2026-08-20 extension: for any
symbol that clears the base walk-forward bar with V3's frozen parameters,
also try a targeted, TRAIN-only, walk-forward-validated sweep of
threshold/stop-percentile/trailing-distance/horizon, mirroring BTC/ETH's
own Experiments 5/6/10/29/30 -- NOT applied by default, only via explicit
flags so every existing call with no flags reproduces V3 exactly):
  --threshold, --stop-pct, --activate-at, --trail-dist override the
  corresponding module constants directly (safe: every function that uses
  them is defined in THIS file and reads the module-level name at call
  time, so reassigning after argparse propagates correctly).
  --horizon is passed explicitly into the trade builder. Its maximum exit
  window is always 5*horizon (base horizon + four horizon extensions), so
  no import-time module global can silently retain an old value.

Usage:
    python scripts/multi_crypto_walkforward.py --symbol SOLUSDT --max-folds 3
    python scripts/multi_crypto_walkforward.py --symbol SOLUSDT --threshold 0.75 --max-folds 3
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR, COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HORIZON = 10
THRESHOLD = 0.70
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01
TRAIN_FRACTION, VALIDATION_FRACTION = 0.60, 0.20  # HOLDOUT = remaining 20%, never touched

STD_INITIAL_TRAIN_MONTHS, STD_TEST_MONTHS, STD_STEP_MONTHS = 24, 3, 3
MIN_MONTHS_FOR_STANDARD = 30  # need >= INITIAL(24)+TEST(3)+buffer to get >=1 standard fold

SCENARIOS = [
    ("frictionless", dict()),
    ("slippage 2x", dict(slip_mult=2.0)),
    ("slippage 3x", dict(slip_mult=3.0)),
    ("gap 0.10%", dict(gap_extra=0.0010)),
    ("gap 0.25%", dict(gap_extra=0.0025)),
    ("gap 0.50%", dict(gap_extra=0.0050)),
    ("latency 1min", dict(entry_delay=1)),
    ("latency 2min", dict(entry_delay=2)),
    ("WORST CASE (slip2x+gap.25%+delay1)", dict(slip_mult=2.0, gap_extra=0.0025, entry_delay=1)),
]

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "_full_data_cache")


def _load_full_cached(symbol: str) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}_full.pkl")
    if os.path.exists(cache_path):
        return pd.read_pickle(cache_path)
    pattern = os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No klines CSV for {symbol} in {DATA_DIR}")
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    df.to_pickle(cache_path)
    return df


def decide_fold_params(data_start: pd.Timestamp, safe_end: pd.Timestamp):
    total_months = (safe_end - data_start).days / 30.44
    if total_months >= MIN_MONTHS_FOR_STANDARD:
        return STD_INITIAL_TRAIN_MONTHS, STD_TEST_MONTHS, STD_STEP_MONTHS, False
    initial = max(6, int(total_months * 0.55))
    step = max(1, int(total_months * 0.11))
    return initial, step, step, True


def build_folds(data_start, safe_end, initial_train_months, test_months, step_months):
    folds = []
    train_end = data_start + pd.DateOffset(months=initial_train_months)
    while True:
        test_end = train_end + pd.DateOffset(months=test_months)
        if test_end > safe_end:
            break
        folds.append((data_start, train_end, test_end))
        train_end = train_end + pd.DateOffset(months=step_months)
    return folds


def fit_fold_model(train_df: pd.DataFrame):
    train_feats = build_feature_matrix(train_df)
    train_labels = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    kept, _ = prune_redundant(train_feats, train_labels, corr_threshold=0.9)
    fit_n = min(250_000, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
    return model, train_feats


def resolve_stressed(path: np.ndarray, protective: float,
                      gap_extra: float = 0.0, slip_mult: float = 1.0, entry_delay: int = 0):
    if entry_delay > 0:
        if entry_delay >= len(path) - 1:
            return None
        new_entry = path[entry_delay]
        path = (1 + path[entry_delay:]) / (1 + new_entry) - 1.0
    cost = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - gap_extra - cost
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - gap_extra - cost
    return path[-1] - cost


def process_fold(symbol, fold_i, train_df, test_df):
    model, train_feats = fit_fold_model(train_df)
    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > THRESHOLD
    if train_selected.sum() < 20:
        return None, None, None
    range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
    vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()

    train_close = train_df["close"].to_numpy()
    train_filtered = (
        train_selected
        & (train_feats["range_pos_60"] < range_pos_cut)
        & (train_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    train_trades = build_trades_with_mae_mfe(
        train_close, train_filtered,
        train_feats["ema_slope_20"].to_numpy(), train_feats["ret_1"].to_numpy(),
        horizon=HORIZON)
    if len(train_trades) < 10:
        return None, None, None
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)

    test_feats = build_feature_matrix(test_df)
    test_proba = model.predict_proba(test_feats)
    test_filtered = (
        (test_proba > THRESHOLD)
        & (test_feats["range_pos_60"] < range_pos_cut)
        & (test_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    test_close = test_df["close"].to_numpy()
    seq_trades = build_trades_with_mae_mfe(
        test_close, test_filtered,
        test_feats["ema_slope_20"].to_numpy(), test_feats["ret_1"].to_numpy(),
        horizon=HORIZON)
    if len(seq_trades) == 0:
        return {"n_trades": 0, "reason": "no TEST entries"}, [], {}

    notional = CAPITAL * RISK_PCT
    export_rows = []
    pnls, n_forced = [], 0
    for t in seq_trades:
        i = t["entry_idx"]
        path = t["close_path"]
        peak, activated, was_stopped = -np.inf, False, False
        raw_return, exit_offset = None, len(path) - 1
        for j, x in enumerate(path):
            if x <= -protective:
                raw_return, was_stopped, exit_offset = -protective, True, j
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    raw_return, exit_offset = stop_level, j
                    break
        if raw_return is None:
            raw_return = path[-1]
        entry_time = test_df.index[i]
        exit_time = test_df.index[min(i + exit_offset, len(test_df) - 1)]
        export_rows.append({
            "symbol": symbol, "fold": fold_i, "entry_time": entry_time, "exit_time": exit_time,
            "raw_return": raw_return, "stop_distance": stop_distance, "leverage_safe": leverage,
            "was_stopped": was_stopped, "close_path": ";".join(f"{v:.8f}" for v in path),
        })
        exit_ret = raw_return - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        n_forced += int(was_stopped and liq_move <= stop_distance)
        pnls.append(exit_ret * notional * leverage)

    pnls = np.array(pnls)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    summary = {
        "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
        "max_dd_pct": round(float(dd.min() * 100), 3),
        "win_rate_pct": round((pnls > 0).mean() * 100, 1),
        "stop_distance_pct": round(stop_distance * 100, 3),
        "leverage": round(leverage, 2),
        "n_forced_liq": n_forced,
    }

    stress = {}
    for label, kwargs in SCENARIOS:
        spnls = []
        for t in seq_trades:
            ret = resolve_stressed(t["close_path"], protective, **kwargs)
            if ret is not None:
                spnls.append(ret * notional * leverage)
        if not spnls:
            continue
        spnls = np.array(spnls)
        swins, slosses = spnls[spnls > 0], spnls[spnls <= 0]
        spf = float(swins.sum() / -slosses.sum()) if slosses.sum() < 0 else float("inf")
        stress[label] = {"n": len(spnls), "pf": spf, "ret": spnls.sum() / CAPITAL * 100}

    return summary, export_rows, stress


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--max-folds", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=None, help="override V3's 0.70 (per-symbol optimization sweep)")
    parser.add_argument("--stop-pct", type=int, default=None, help="override V3's p90 protective-stop percentile")
    parser.add_argument("--activate-at", type=float, default=None, help="override V3's 0.0063 trailing-activate distance")
    parser.add_argument("--trail-dist", type=float, default=None, help="override V3's 0.0080 trailing distance")
    parser.add_argument("--horizon", type=int, default=None, help="override V3's 10min label horizon")
    parser.add_argument("--tag", default=None, help="output-file suffix for a sweep run (default: derived from overridden params, empty for a plain V3 run)")
    args = parser.parse_args()
    symbol = args.symbol.upper()

    global THRESHOLD, STOP_PCT_PERCENTILE, ACTIVATE_AT, TRAIL_DIST, HORIZON
    overrides = []
    if args.threshold is not None:
        THRESHOLD = args.threshold
        overrides.append(f"threshold{args.threshold}")
    if args.stop_pct is not None:
        STOP_PCT_PERCENTILE = args.stop_pct
        overrides.append(f"stop{args.stop_pct}")
    if args.activate_at is not None:
        ACTIVATE_AT = args.activate_at
        overrides.append(f"act{args.activate_at}")
    if args.trail_dist is not None:
        TRAIL_DIST = args.trail_dist
        overrides.append(f"trail{args.trail_dist}")
    if args.horizon is not None:
        HORIZON = args.horizon
        overrides.append(f"h{args.horizon}")
    tag = args.tag if args.tag is not None else ("_" + "_".join(overrides) if overrides else "")
    if overrides:
        print(f"[{symbol}] PARAMETER OVERRIDE sweep run: {', '.join(overrides)} (V3 defaults otherwise)")

    full = _load_full_cached(symbol)
    n = len(full)
    data_start = full.index[0]
    safe_end = full.index[int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))]
    initial, test_m, step_m, adapted = decide_fold_params(data_start, safe_end)
    if adapted:
        print(f"[{symbol}] ADAPTED fold params (short history): "
              f"INITIAL_TRAIN={initial}mo TEST={test_m}mo STEP={step_m}mo "
              f"(vs standard 24/3/3) -- span={(safe_end - data_start).days} days")
    folds = build_folds(data_start, safe_end, initial, test_m, step_m)
    print(f"[{symbol}] {len(folds)} walk-forward folds, data {data_start:%Y-%m-%d} -> "
          f"safe_end(HOLDOUT_START)={safe_end:%Y-%m-%d}")

    docs = os.path.join(os.path.dirname(__file__), "..", "docs")
    summary_path = os.path.join(docs, f"multi_crypto_wf_{symbol}{tag}_summary.csv")
    export_path = os.path.join(docs, f"multi_crypto_wf_{symbol}{tag}_trades.csv")
    stress_path = os.path.join(docs, f"multi_crypto_wf_{symbol}{tag}_stress.csv")
    done_marker = summary_path + ".done_folds.txt"

    summary_rows, export_rows, stress_rows = [], [], []
    if os.path.exists(summary_path):
        summary_rows = pd.read_csv(summary_path).to_dict("records")
    if os.path.exists(export_path):
        export_rows = pd.read_csv(export_path).to_dict("records")
    if os.path.exists(stress_path):
        stress_rows = pd.read_csv(stress_path).to_dict("records")
    done_folds = set()
    if os.path.exists(done_marker):
        with open(done_marker) as f:
            done_folds = {int(x) for x in f.read().split() if x.strip()}
        print(f"Resuming: folds already done = {sorted(done_folds)}")

    processed = 0
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        if fold_i in done_folds:
            continue
        if processed >= args.max_folds:
            print(f"Reached --max-folds={args.max_folds}, exiting cleanly.")
            break
        train_df = full[(full.index >= t0) & (full.index < train_end)]
        test_df = full[(full.index >= train_end) & (full.index < test_end)]
        print(f"FOLD {fold_i}/{len(folds)}: TRAIN[{t0:%Y-%m-%d}->{train_end:%Y-%m-%d}] "
              f"TEST[{train_end:%Y-%m-%d}->{test_end:%Y-%m-%d}] "
              f"(train_n={len(train_df):,} test_n={len(test_df):,})")
        summary, erows, stress = process_fold(symbol, fold_i, train_df, test_df)
        if summary is None:
            print(f"  {symbol}: TRAIN population too small, skipping fold")
            summary_rows.append({"fold": fold_i, "symbol": symbol, "n_trades": 0, "reason": "train pop too small"})
        elif summary.get("n_trades", 0) == 0:
            print(f"  {symbol}: {summary.get('reason', 'no trades')}")
            summary_rows.append({"fold": fold_i, "symbol": symbol, **summary})
        else:
            print(f"  {symbol}: n={summary['n_trades']:>3} PF={summary['profit_factor']:>7.3f} "
                  f"ret={summary['total_return_pct']:>+7.3f}% DD={summary['max_dd_pct']:>+7.3f}% "
                  f"win%={summary['win_rate_pct']:>5.1f} stop={summary['stop_distance_pct']:.2f}% "
                  f"lev={summary['leverage']:.2f}x forced_liq={summary['n_forced_liq']}")
            summary_rows.append({"fold": fold_i, "symbol": symbol,
                                  "train_start": t0, "train_end": train_end, "test_end": test_end, **summary})
            export_rows.extend(erows)
            srow = {"fold": fold_i, "symbol": symbol}
            for label, m in stress.items():
                srow[f"{label}__n"] = m["n"]
                srow[f"{label}__pf"] = m["pf"]
                srow[f"{label}__ret"] = m["ret"]
            stress_rows.append(srow)

        pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
        pd.DataFrame(export_rows).to_csv(export_path, index=False)
        pd.DataFrame(stress_rows).to_csv(stress_path, index=False)
        done_folds.add(fold_i)
        with open(done_marker, "w") as f:
            f.write(" ".join(str(x) for x in sorted(done_folds)))
        processed += 1

    remaining = [i for i in range(1, len(folds) + 1) if i not in done_folds]
    if remaining:
        print(f"\nFolds still remaining for {symbol}: {remaining} -- rerun to continue.")
        return

    df_res = pd.DataFrame(summary_rows)
    sub = df_res[df_res.get("n_trades", 0) > 0] if len(df_res) else df_res
    print("\n" + "=" * 100)
    print(f"  {symbol} WALK-FORWARD SUMMARY ({len(sub)}/{len(folds)} folds with trades)")
    print("=" * 100)
    if len(sub) == 0:
        print(f"{symbol}: no fold produced trades -- REJECT (no viable walk-forward population)")
    else:
        pf = sub["profit_factor"].replace([np.inf], np.nan).dropna()
        print(f"  total n_trades={sub['n_trades'].sum()}  mean PF={pf.mean():.3f}  median PF={pf.median():.3f}  "
              f"%% folds PF>1: {(sub['profit_factor'] > 1).mean() * 100:.1f}%")
        print(f"  worst fold PF={sub['profit_factor'].min():.3f}  best fold PF={sub['profit_factor'].max():.3f}")
        print(f"  total return summed across folds: {sub['total_return_pct'].sum():+.2f}%")
        print(f"  total forced liquidations across folds: {sub['n_forced_liq'].sum()}")
    print(f"\nSaved -> {summary_path}\n         {export_path}\n         {stress_path}")


if __name__ == "__main__":
    main()
