"""
scripts/step1_stress_test.py — Étape 1 (TEST A) of the iterative research
plan (docs/research_plan_status.md): does BASELINE_CANDIDATE_V1 survive
less-optimistic execution assumptions? Everything downstream of this test
assumes exact-price fills at the stop/trailing level and the current flat
cost model (TAKER_FEE_PCT*2 + SLIPPAGE_PCT_EST, no funding, no latency) --
this checks whether the edge is robust to that being wrong.

BASELINE_CANDIDATE_V1 (frozen, registered in docs/research_plan_status.md):
  model: Tier2RandomForestSignal, BTC+ETH joint TRAIN, horizon=10min, thr=0.75
  entry filter: range_pos_60 / realized_vol_30, cutoffs from TRAIN-selected pop
  exit: trailing (activate +0.63%, trail 0.30%) + protective stop (p90 MAE)
        + time-exit at the 50min window boundary if neither triggers
  leverage: ETHUSDT 12.1x, BTCUSDT 9.9x (registered exact values, not "~12x/7-10x")

Entry selection reuses scripts.mae_mfe_analysis.build_trades_with_mae_mfe,
which walks ONE POSITION AT A TIME (SPEC.md section 11) -- an earlier
version of this script iterated every True index in filtered_mask
independently, which allows overlapping/concurrent positions and silently
inflated n (145 vs the correct 89 for ETH, 82 vs 42 for BTC). Reusing the
established sequential-entry function fixes that and keeps entry timing
consistent with every other script in this project.

Four stress dimensions, each swept independently (holding the others at
baseline) so the matrix shows which one the strategy is actually sensitive
to, plus a "combined worst case" row:

  4.1 slippage multiplier (0/0.5/1/2/3/5x SLIPPAGE_PCT_EST), tested both
      combined (all legs) and broken out per exit-leg type (entry/
      trailing/protective-stop/time-exit) since a trailing/stop fill in a
      fast market is a very different risk than a scheduled time-exit fill.
  4.2 stop/trailing fill gap: extra adverse distance beyond the nominal
      trigger level (0/0.05/0.10/0.25/0.50/1.00/2.00%), applied whenever a
      stop or trailing exit fires.
  4.3 execution latency: entry filled N bars late (0/1/2/3 min) instead of
      on the signal bar's own close. Re-walks the price path from
      entry_idx+delay (needs the raw close array, not just the stored
      close_path, since the window itself shifts).
  4.4 funding cost: real historical funding-rate history
      (data/{symbol}_funding_20230506_20260818.csv, 8h settlement) charged
      against the holding period, at 0x/1x/2x/3x the real historical rate.

Usage:
    python scripts/step1_stress_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR, COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
EXTENSION_CAP = 40
LOOKAHEAD = HORIZON + EXTENSION_CAP
CAPITAL = 10_000.0
RISK_PCT = 0.01

ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0030
STOP_PCT_PERCENTILE = 90  # p90, the registered BASELINE_CANDIDATE_V1 protective stop

# Registered EXACT leverage per symbol (BASELINE_CANDIDATE_V1) -- see docs/research_plan_status.md
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}

FEE_PER_SIDE = TAKER_FEE_PCT           # 0.05%, fixed -- not a slippage assumption
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0  # 0.01% baseline per side

FUNDING_FILES = {
    "BTCUSDT": os.path.join(DATA_DIR, "BTCUSDT_funding_20230506_20260818.csv"),
    "ETHUSDT": os.path.join(DATA_DIR, "ETHUSDT_funding_20230506_20260818.csv"),
}


def load_funding(symbol: str) -> pd.Series:
    df = pd.read_csv(FUNDING_FILES[symbol])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    return df.set_index("timestamp")["fundingRate"].sort_index()


def funding_cost_for_window(funding: pd.Series, start_ts, end_ts, mult: float) -> float:
    window = funding.loc[(funding.index > start_ts) & (funding.index <= end_ts)]
    return float(window.sum()) * mult


def get_setup(symbol: str, model):
    train_df_sym = load_split(symbol, "train", verbose=False)
    train_feats_sym = build_feature_matrix(train_df_sym)
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
    vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

    df_val = load_split(symbol, "validation", verbose=False)
    feats_val = build_feature_matrix(df_val)
    proba = model.predict_proba(feats_val)
    filtered_mask = (
        (proba > THRESHOLD)
        & (feats_val["range_pos_60"] < range_pos_cut)
        & (feats_val["realized_vol_30"] > vol_cut)
    ).to_numpy()
    ema_slope_arr = feats_val["ema_slope_20"].to_numpy()
    ret_1_arr = feats_val["ret_1"].to_numpy()
    return df_val, filtered_mask, ema_slope_arr, ret_1_arr


def get_sequential_trades(df_val, filtered_mask, ema_slope_arr, ret_1_arr) -> list:
    """ONE POSITION AT A TIME entries (SPEC.md section 11), reusing the
    established build_trades_with_mae_mfe walk. Only `entry_idx`, `mae` and
    `close_path` are used downstream -- the dca_rescue_trend `pnl_return` it
    also computes is discarded here since this script replaces the exit
    logic entirely."""
    close_arr = df_val["close"].to_numpy()
    return build_trades_with_mae_mfe(close_arr, filtered_mask, ema_slope_arr, ret_1_arr)


def historical_mae_stop_distance(trades: list) -> float:
    maes = np.array([abs(t["mae"]) for t in trades])
    return float(np.percentile(maes, STOP_PCT_PERCENTILE))


def simulate_stressed(trades: list, close_arr: np.ndarray, timestamps, funding: pd.Series,
                       stop_distance: float, leverage: float,
                       entry_delay: int = 0,
                       slip_mult_entry: float = 1.0, slip_mult_trailing: float = 1.0,
                       slip_mult_stop: float = 1.0, slip_mult_time: float = 1.0,
                       gap_extra: float = 0.0, funding_mult: float = 0.0,
                       activate_at: float = ACTIVATE_AT, trail_dist: float = TRAIL_DIST) -> dict:
    n = len(close_arr)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    is_liq = liq_move <= stop_distance

    notional = CAPITAL * RISK_PCT
    pnls, n_forced = [], 0
    for t in trades:
        i = t["entry_idx"] + entry_delay
        if i < 0 or i >= n - LOOKAHEAD - 1:
            continue
        entry_price = close_arr[i]
        entry_ts = timestamps[i]
        cost_entry = FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult_entry

        path = close_arr[i:i + LOOKAHEAD + 1] / entry_price - 1.0
        peak, activated = -np.inf, False
        exit_ret, exit_offset, forced = None, LOOKAHEAD, False

        for j, x in enumerate(path):
            if x <= -protective:
                fill = -protective - gap_extra
                cost_exit = FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult_stop
                exit_ret, exit_offset, forced = fill - cost_exit, j, is_liq
                break
            if x > peak:
                peak = x
            if not activated and peak >= activate_at:
                activated = True
            if activated:
                stop_level = peak - trail_dist
                if x <= stop_level:
                    fill = stop_level - gap_extra
                    cost_exit = FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult_trailing
                    exit_ret, exit_offset = fill - cost_exit, j
                    break
        if exit_ret is None:
            cost_exit = FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult_time
            exit_ret = path[-1] - cost_exit

        exit_ts = timestamps[min(i + exit_offset, n - 1)]
        fcost = funding_cost_for_window(funding, entry_ts, exit_ts, funding_mult) if funding_mult > 0 else 0.0

        net_ret = exit_ret - cost_entry - fcost
        pnls.append(net_ret * notional * leverage)
        n_forced += int(forced)

    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    return {
        "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
        "max_dd_pct": round(float(dd.min() * 100), 3),
        "win_rate_pct": round((pnls > 0).mean() * 100, 1),
        "n_forced_liq": n_forced,
    }


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min...")
    train_feats, train_labels = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.\n")

    all_rows = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        df_val, filtered_mask, ema_slope_arr, ret_1_arr = get_setup(symbol, model)
        funding = load_funding(symbol)
        close_arr = df_val["close"].to_numpy()
        timestamps = df_val.index
        trades = get_sequential_trades(df_val, filtered_mask, ema_slope_arr, ret_1_arr)
        stop_distance = historical_mae_stop_distance(trades)
        leverage = LEVERAGE[symbol]
        print("=" * 100)
        print(f"  {symbol} — {len(trades)} sequential (one-position-at-a-time) entries, "
              f"leverage={leverage}x, protective stop (p{STOP_PCT_PERCENTILE})={stop_distance*100:.2f}%")
        print(f"  funding coverage: {funding.index[0]:%Y-%m-%d} -> {funding.index[-1]:%Y-%m-%d} "
              f"(VALIDATION: {df_val.index[0]:%Y-%m-%d} -> {df_val.index[-1]:%Y-%m-%d})")
        print("=" * 100)

        def run(label, **kw):
            r = simulate_stressed(trades, close_arr, timestamps, funding, stop_distance, leverage, **kw)
            print(f"  {label:<28} n={r.get('n_trades',0):>4} PF={r.get('profit_factor',float('nan')):>7.3f} "
                  f"ret={r.get('total_return_pct',float('nan')):>+7.3f}% DD={r.get('max_dd_pct',float('nan')):>+7.3f}% "
                  f"win%={r.get('win_rate_pct',float('nan')):>5.1f} forced_liq={r.get('n_forced_liq','-')}")
            all_rows.append({"symbol": symbol, "scenario": label, **r})
            return r

        print("\n-- 4.1a Combined slippage multiplier (all legs) --")
        for m in [0, 0.5, 1, 2, 3, 5]:
            run(f"slippage {m}x" + (" (BASE)" if m == 1 else ""),
                slip_mult_entry=m, slip_mult_trailing=m, slip_mult_stop=m, slip_mult_time=m)

        print("\n-- 4.1b Per-leg slippage sensitivity (one leg at Nx, others at baseline 1x) --")
        for leg, key in [("entry", "slip_mult_entry"), ("trailing", "slip_mult_trailing"),
                          ("stop", "slip_mult_stop"), ("time-exit", "slip_mult_time")]:
            for m in [2, 5]:
                run(f"{leg} slippage {m}x only", **{key: m})

        print("\n-- 4.2 Stop/trailing fill gap (extra adverse move beyond nominal trigger) --")
        for gap in [0.0, 0.0005, 0.0010, 0.0025, 0.0050, 0.0100, 0.0200]:
            run(f"gap +{gap*100:.2f}%", gap_extra=gap)

        print("\n-- 4.3 Execution latency (entry filled N bars late) --")
        for lat in [0, 1, 2, 3]:
            run(f"latency {lat}min", entry_delay=lat)

        print("\n-- 4.4 Funding cost (real historical rate x multiplier) --")
        for fm in [0, 1, 2, 3]:
            run(f"funding {fm}x", funding_mult=fm)

        print("\n-- 4.5 Combined worst-plausible case (slippage 2x, gap 0.25%, funding 2x, latency 1min) --")
        run("COMBINED WORST CASE", slip_mult_entry=2, slip_mult_trailing=2, slip_mult_stop=2, slip_mult_time=2,
            gap_extra=0.0025, funding_mult=2, entry_delay=1)
        print()

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step1_stress_test_raw.csv")
    pd.DataFrame(all_rows).to_csv(out_path, index=False)
    print(f"Raw results saved -> {out_path}")


if __name__ == "__main__":
    main()
