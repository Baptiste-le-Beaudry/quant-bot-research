"""
scripts/multi_crypto_screen.py — multi-crypto expansion plan, Etapes 3-6:
per-symbol data validation + two screening tests against
BASELINE_CANDIDATE_V3 (docs/research_plan_status.md, Experiment 28), BEFORE
spending walk-forward compute on any candidate.

Test A ("transfer", --mode transfer): the model fit on BTC+ETH's OWN
pre-HOLDOUT history (everything before SAFE_END=2025-03-28, i.e. exactly
the same population walk_forward_engine.py's folds are drawn from) plus
BTC/ETH's own TRAIN-derived range_pos_60/realized_vol_30 cutoffs and p90
stop/leverage are applied COMPLETELY UNCHANGED to the new symbol's own
pre-HOLDOUT history (first 80% chronologically) -- zero fitting, zero
recalibration on the new symbol at all. Purest possible generalization
check: does the BTC/ETH-learned pattern even fire on this asset?

Test B ("own", --mode own, the default): identical architecture/features/
horizon=10/threshold=0.70/mandatory filter/dynamic leverage, but everything
TRAIN-derived (range_pos_60/realized_vol_30 cutoffs, p90 stop, leverage) is
recomputed from THIS symbol's OWN TRAIN split (first 60% chronologically).
Single TRAIN->VALIDATION split (NOT walk-forward -- that's the next, more
expensive step, reserved for whichever symbols survive this screen). No
per-symbol hyperparameter tuning of any kind.

Both modes: data validation printed first time a symbol's data is loaded
(NaN, dupes, OHLC sanity, max single gap) and this symbol's fresh 60/20/20
HOLDOUT_START boundary is printed and logged -- HOLDOUT itself is NEVER
touched by this script (only train/validation slices are read).

Appends one row per (symbol, mode) run to docs/multi_crypto_screen_raw.csv.

Usage:
    python scripts/multi_crypto_screen.py --symbol SOLUSDT --mode own
    python scripts/multi_crypto_screen.py --symbol SOLUSDT --mode transfer
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import (
    DATA_DIR, COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT,
    TRAIN_FRACTION, VALIDATION_FRACTION,
)
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
import scripts.fast_trades as _fast_trades_module
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Per-symbol optimization phase (Etape "post-generalization", user's 2026-08-20 extension):
# --threshold/--stop-pct/--horizon on `--mode own` override these module constants (same pattern,
# same horizon-globals caveat, as scripts/multi_crypto_walkforward.py's sweep support).
HORIZON = 10
EXTENSION_CAP = 40
LOOKAHEAD = HORIZON + EXTENSION_CAP
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

BTC_ETH_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
SAFE_END = pd.Timestamp("2025-03-28", tz="UTC")  # min(BTC HOLDOUT_start, ETH HOLDOUT_start) -- Experiment 28

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "_full_data_cache")
RAW_OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "multi_crypto_screen_raw.csv")


def _load_full(symbol: str) -> pd.DataFrame:
    pattern = os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No klines CSV for {symbol} in {DATA_DIR}")
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def _load_full_cached(symbol: str) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}_full.pkl")
    if os.path.exists(cache_path):
        return pd.read_pickle(cache_path)
    df = _load_full(symbol)
    df.to_pickle(cache_path)
    return df


def validate(symbol: str, df: pd.DataFrame) -> dict:
    n_nan = int(df[["open", "high", "low", "close", "volume"]].isna().sum().sum())
    n_dupe = int(df.index.duplicated().sum())
    bad_hl = int((df["high"] < df["low"]).sum())
    bad_close = int(((df["close"] > df["high"]) | (df["close"] < df["low"])).sum())
    bad_open = int(((df["open"] > df["high"]) | (df["open"] < df["low"])).sum())
    gaps_min = df.index.to_series().diff().dt.total_seconds() / 60.0
    max_gap = float(gaps_min.max()) if len(gaps_min) > 1 else 0.0
    span_days = (df.index[-1] - df.index[0]).days
    print(f"\n[{symbol}] VALIDATE: {len(df):,} bars, {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d} "
          f"({span_days} days)")
    print(f"  NaN={n_nan}  dupes={n_dupe}  high<low={bad_hl}  close-out-of-range={bad_close}  "
          f"open-out-of-range={bad_open}  max_gap={max_gap:.1f}min")
    ok = n_nan == 0 and n_dupe == 0 and bad_hl == 0 and bad_close == 0 and bad_open == 0
    print(f"  -> {'CLEAN' if ok else 'ANOMALIES FOUND'}")
    return {"n_bars": len(df), "n_nan": n_nan, "n_dupe": n_dupe, "bad_hl": bad_hl,
            "bad_close": bad_close, "bad_open": bad_open, "max_gap_min": round(max_gap, 1), "clean": ok}


def fit_model(train_df: pd.DataFrame):
    train_feats = build_feature_matrix(train_df)
    train_labels = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    kept, _ = prune_redundant(train_feats, train_labels, corr_threshold=0.9)
    fit_n = min(250_000, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
    return model, train_feats


def fit_model_joint(train_slices: dict):
    train_feats, train_labels = {}, {}
    for symbol, df in train_slices.items():
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    return model, train_feats


def cutoffs_from(model, train_df: pd.DataFrame, train_feats: pd.DataFrame, cutoff_percentile: float = 50.0):
    """Returns (range_pos_cut, vol_cut, stop_distance, leverage) or None if population too small.

    cutoff_percentile=50 (median) is V3's own choice, applied symmetrically: range_pos_cut at the
    P-th percentile (< cut, so a HIGHER P admits MORE bars), vol_cut at the (100-P)-th percentile
    (> cut, so the SAME P also admits more bars there) -- a single knob that loosens/tightens both
    sides of the filter together. Investigation-only (Experiment 33 follow-up, 2026-08-20): does a
    looser percentile rescue a usable sample for symbols where the median cutoff leaves <20 TRAIN-
    selected trades (SOL, AVAX -- the two shortest-history symbols)?
    """
    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > THRESHOLD
    if train_selected.sum() < 20:
        return None
    range_pos_cut = np.percentile(train_feats.loc[train_selected, "range_pos_60"], cutoff_percentile)
    vol_cut = np.percentile(train_feats.loc[train_selected, "realized_vol_30"], 100.0 - cutoff_percentile)
    train_close = train_df["close"].to_numpy()
    train_filtered = (
        train_selected
        & (train_feats["range_pos_60"] < range_pos_cut)
        & (train_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    train_trades = build_trades_with_mae_mfe(
        train_close, train_filtered,
        train_feats["ema_slope_20"].to_numpy(), train_feats["ret_1"].to_numpy())
    if len(train_trades) < 10:
        return None
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    return range_pos_cut, vol_cut, stop_distance, leverage


def evaluate(model, eval_df: pd.DataFrame, range_pos_cut, vol_cut, stop_distance, leverage) -> dict:
    eval_feats = build_feature_matrix(eval_df)
    eval_proba = model.predict_proba(eval_feats)
    eval_filtered = (
        (eval_proba > THRESHOLD)
        & (eval_feats["range_pos_60"] < range_pos_cut)
        & (eval_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    eval_close = eval_df["close"].to_numpy()
    seq_trades = build_trades_with_mae_mfe(
        eval_close, eval_filtered,
        eval_feats["ema_slope_20"].to_numpy(), eval_feats["ret_1"].to_numpy())
    if len(seq_trades) == 0:
        return {"n_trades": 0, "reason": "no entries"}

    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = CAPITAL * RISK_PCT

    pnls, n_forced = [], 0
    for t in seq_trades:
        path = t["close_path"]
        peak, activated = -np.inf, False
        exit_ret = None
        for x in path:
            if x <= -protective:
                exit_ret = -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                n_forced += int(liq_move <= stop_distance)
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    exit_ret = stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                    break
        if exit_ret is None:
            exit_ret = path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        pnls.append(exit_ret * notional * leverage)

    pnls = np.array(pnls)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    n_days = (eval_df.index[-1] - eval_df.index[0]).days
    cagr = ((eq[-1] / CAPITAL) ** (365.25 / max(n_days, 1)) - 1) * 100 if eq[-1] > 0 else float("nan")
    return {
        "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "win_rate_pct": round((pnls > 0).mean() * 100, 1),
        "avg_trade_pct": round(float(pnls.mean() / notional / leverage * 100), 4),
        "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
        "cagr_pct": round(cagr, 2) if cagr == cagr else None,
        "max_dd_pct": round(float(dd.min() * 100), 3),
        "stop_distance_pct": round(stop_distance * 100, 3),
        "leverage": round(leverage, 2),
        "n_forced_liq": n_forced,
    }


def run_own(symbol: str, cutoff_percentile: float = 50.0) -> dict:
    df = _load_full(symbol)
    vstats = validate(symbol, df)
    n = len(df)
    train_end = int(n * TRAIN_FRACTION)
    val_end = int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))
    train_df, val_df = df.iloc[:train_end], df.iloc[train_end:val_end]
    holdout_start = df.index[val_end] if val_end < n else df.index[-1]
    print(f"[{symbol}] split: TRAIN {train_df.index[0]:%Y-%m-%d}->{train_df.index[-1]:%Y-%m-%d} "
          f"({len(train_df):,})  VALIDATION {val_df.index[0]:%Y-%m-%d}->{val_df.index[-1]:%Y-%m-%d} "
          f"({len(val_df):,})  HOLDOUT_START={holdout_start:%Y-%m-%d} (never touched)")
    if cutoff_percentile != 50.0:
        print(f"[{symbol}] INVESTIGATION: cutoff_percentile={cutoff_percentile} (V3 default is 50/median)")

    if len(train_df) < 50_000 or len(val_df) < 5_000:
        print(f"[{symbol}] SKIP: insufficient history for a meaningful TRAIN/VALIDATION split")
        return {"symbol": symbol, "mode": "own", "n_trades": 0, "reason": "insufficient history", **vstats}

    model, train_feats = fit_model(train_df)
    cal = cutoffs_from(model, train_df, train_feats, cutoff_percentile)
    if cal is None:
        print(f"[{symbol}] SKIP: TRAIN-selected population too small to calibrate filter/stop")
        return {"symbol": symbol, "mode": "own", "n_trades": 0, "reason": "train pop too small", **vstats}
    range_pos_cut, vol_cut, stop_distance, leverage = cal
    r = evaluate(model, val_df, range_pos_cut, vol_cut, stop_distance, leverage)
    r.update({"symbol": symbol, "mode": "own", "holdout_start": str(holdout_start.date())})
    r.update(vstats)
    return r


TRANSFER_MODEL_CACHE = os.path.join(CACHE_DIR, "transfer_model_cutoffs.pkl")


def _get_transfer_model():
    """The BTC+ETH-trained model + its derived cutoffs are IDENTICAL for every new symbol's
    Test A run (nothing about the new symbol feeds into fitting it) -- cached to disk so 8
    separate `--mode transfer` invocations don't each pay a full RF-fit-on-2M-rows cost again."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(TRANSFER_MODEL_CACHE):
        print("[transfer] loading cached BTC+ETH-trained model + cutoffs ...")
        return pd.read_pickle(TRANSFER_MODEL_CACHE)

    full = {s: _load_full_cached(s) for s in BTC_ETH_SYMBOLS}
    btc_eth_train = {s: full[s][full[s].index < SAFE_END] for s in BTC_ETH_SYMBOLS}
    model, train_feats = fit_model_joint(btc_eth_train)
    cals = []
    for s in BTC_ETH_SYMBOLS:
        cal = cutoffs_from(model, btc_eth_train[s], train_feats[s])
        if cal is not None:
            cals.append(cal)
    range_pos_cut = float(np.mean([c[0] for c in cals]))
    vol_cut = float(np.mean([c[1] for c in cals]))
    stop_distance = float(np.mean([c[2] for c in cals]))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    result = (model, range_pos_cut, vol_cut, stop_distance, leverage)
    pd.to_pickle(result, TRANSFER_MODEL_CACHE)
    return result


def run_transfer(symbol: str) -> dict:
    df = _load_full(symbol)
    vstats = validate(symbol, df)
    n = len(df)
    eval_end = int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))  # symbol's own pre-HOLDOUT 80%
    eval_df = df.iloc[:eval_end]
    print(f"[{symbol}] transfer-eval population: {eval_df.index[0]:%Y-%m-%d} -> "
          f"{eval_df.index[-1]:%Y-%m-%d} ({len(eval_df):,} bars, symbol's own pre-HOLDOUT 80%)")

    model, range_pos_cut, vol_cut, stop_distance, leverage = _get_transfer_model()
    print(f"[transfer] BTC+ETH-derived cutoffs applied UNCHANGED: range_pos_60<{range_pos_cut:.4f}, "
          f"realized_vol_30>{vol_cut:.6f}, stop={stop_distance*100:.2f}%, leverage={leverage:.2f}x")

    r = evaluate(model, eval_df, range_pos_cut, vol_cut, stop_distance, leverage)
    r.update({"symbol": symbol, "mode": "transfer"})
    r.update(vstats)
    return r


def append_row(row: dict):
    df_row = pd.DataFrame([row])
    if os.path.exists(RAW_OUT):
        prev = pd.read_csv(RAW_OUT)
        out = pd.concat([prev, df_row], ignore_index=True)
    else:
        out = df_row
    out.to_csv(RAW_OUT, index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--mode", choices=["own", "transfer"], default="own")
    parser.add_argument("--cutoff-percentile", type=float, default=50.0,
                         help="own-mode only: investigation flag (Experiment 33 follow-up) for "
                              "symbols where the median cutoff leaves too few TRAIN-selected "
                              "trades. Non-default runs are NOT appended to the shared raw CSV "
                              "(would corrupt the triage table with a non-V3-comparable row).")
    parser.add_argument("--threshold", type=float, default=None, help="own-mode sweep: override V3's 0.70")
    parser.add_argument("--stop-pct", type=int, default=None, help="own-mode sweep: override V3's p90")
    parser.add_argument("--horizon", type=int, default=None, help="own-mode sweep: override V3's 10min")
    args = parser.parse_args()

    global THRESHOLD, STOP_PCT_PERCENTILE, HORIZON
    is_sweep = args.cutoff_percentile != 50.0
    if args.threshold is not None:
        THRESHOLD = args.threshold
        is_sweep = True
    if args.stop_pct is not None:
        STOP_PCT_PERCENTILE = args.stop_pct
        is_sweep = True
    if args.horizon is not None:
        HORIZON = args.horizon
        _fast_trades_module.HORIZON = args.horizon
        _fast_trades_module.LOOKAHEAD = args.horizon + EXTENSION_CAP
        is_sweep = True

    r = run_own(args.symbol, args.cutoff_percentile) if args.mode == "own" else run_transfer(args.symbol)
    print("\n" + "=" * 90)
    print(f"  {args.symbol} [{args.mode.upper()}] SCREEN RESULT" +
          (f"  threshold={THRESHOLD} stop_pct={STOP_PCT_PERCENTILE} horizon={HORIZON} "
           f"cutoff_percentile={args.cutoff_percentile}" if is_sweep else ""))
    print("=" * 90)
    for k, v in r.items():
        print(f"  {k}: {v}")
    if args.mode == "own" and is_sweep:
        print(f"\nNOT appended to {RAW_OUT} (sweep/investigation-only run)")
    else:
        append_row(r)
        print(f"\nAppended -> {RAW_OUT}")


if __name__ == "__main__":
    main()
