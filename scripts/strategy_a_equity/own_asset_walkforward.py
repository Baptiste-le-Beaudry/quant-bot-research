"""scripts/strategy_a_equity/own_asset_walkforward.py -- STRATEGY_ID =
A-EQUITY, Phase 12A (docs/strategy_a_equity/STRATEGY_A_EQUITY_SPEC.md
Section 12A): own-asset walk-forward, one model per symbol, TRAIN=that
symbol's own expanding history, TEST=that symbol's own next fold.

Structurally IDENTICAL to scripts/multi_crypto_walkforward.py (same walk-
forward fold construction, same trailing-stop/protective-stop mechanism,
same minimum-population guards, same stress scenarios) with exactly the
two domain-calibrated substitutions the spec pre-registers:
  - Section 9: entry gate = TRAIN top-decile score, not crypto's absolute
    proba > 0.70.
  - Section 11: label cost threshold = EQUITY_COST_THRESHOLD_PCT (0.02%
    round-trip), not crypto's 0.12%.
Model class is selectable (--model logistic|rf) per Section 8 -- both are
pre-registered, neither is hyperparameter-tuned for equities.

Does not import from or modify scripts/multi_crypto_walkforward.py or any
quant_bot/ frozen module -- only reads them. No Strategy A crypto file
touched. HOLDOUT (this universe's own safe_end, last 20% by bar count) is
never crossed.

Usage:
    python scripts/strategy_a_equity/own_asset_walkforward.py --symbol AMD --model rf --max-folds 3
    python scripts/strategy_a_equity/own_asset_walkforward.py --symbol AMD --model logistic --max-folds 3
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier1LogisticSignal, Tier2RandomForestSignal
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---- FROZEN per SPEC.md -- do not tune after seeing any TEST result ----
# Configuration D (adopted, frozen 2026-08-29) is the default for every
# argument below. --gate/--cost exist ONLY for TASKS_A_E.md Task A's
# descriptive 2x2 attribution (configs A/B/C) -- they do not change D's
# frozen files, they write to separately-tagged output paths.
HORIZON = 10                       # Section 11, unchanged from crypto
GATE_MODE = "topdecile"            # "topdecile" (D, frozen) or "fixed070" (Task A configs A/C)
SELECTION_QUANTILE = 0.90          # Section 9: TRAIN top decile, not crypto's proba>0.70
FIXED_GATE_THRESHOLD = 0.70        # Task A configs A/C only -- crypto's absolute cutoff
COST_MODE = "equity"               # "equity" (D, frozen) or "crypto" (Task A configs B/C)
FILTER_MODE = "model_filters"      # Task C: "model_filters" (D, frozen) / "generic" / "filters_only" / "model_only"
EQUITY_COST_THRESHOLD_PCT = 0.0002  # Section 11: 0.02% round-trip (vs crypto's 0.0012)
CRYPTO_COST_THRESHOLD_PCT = 0.0012  # Task A configs B/C only -- crypto's own label cost
ACTIVATE_AT = 0.0063               # Section 14: unchanged (already TRAIN-relative via stop pctile)
TRAIL_DIST = 0.0080                # unchanged
STOP_PCT_PERCENTILE = 90           # unchanged
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
# Section 13: cost split evenly, per side -- derived from whichever cost
# mode is active (equity=frozen D default, crypto=Task A configs B/C only)
CAPITAL = 10_000.0
RISK_PCT = 0.01
TRAIN_FRACTION, VALIDATION_FRACTION = 0.60, 0.20  # HOLDOUT = remaining 20%, never touched
# --------------------------------------------------------------------

STD_INITIAL_TRAIN_MONTHS, STD_TEST_MONTHS, STD_STEP_MONTHS = 24, 3, 3
MIN_MONTHS_FOR_STANDARD = 30

SCENARIOS = [
    ("frictionless", dict()),
    ("slippage 2x", dict(slip_mult=2.0)),
    ("slippage 3x", dict(slip_mult=3.0)),
    ("gap 0.10%", dict(gap_extra=0.0010)),
    ("gap 0.25%", dict(gap_extra=0.0025)),
    ("latency 1min", dict(entry_delay=1)),
    ("WORST CASE (slip2x+gap.25%+delay1)", dict(slip_mult=2.0, gap_extra=0.0025, entry_delay=1)),
]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CACHE_DIR = os.path.join(REPO_ROOT, "docs", "_full_data_cache_a_equity")
OUT_DIR = os.path.join(REPO_ROOT, "outputs", "strategy_a_equity")


def _load_full_cached(symbol: str) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}_full.pkl")
    if os.path.exists(cache_path):
        return pd.read_pickle(cache_path)
    pattern = os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No klines CSV for {symbol} in {DATA_DIR} -- "
                                 f"run scripts/strategy_a_equity/download_universe.py first")
    if len(files) > 1:
        # Pick the file with the EARLIEST start date embedded in its name
        # (most history), not just the lexicographically last match -- a
        # stray leftover CSV from an earlier, narrower-window batch (e.g.
        # the prior Databento pull) must never silently win over this
        # study's own wider Dukascopy pull for the same symbol.
        def start_token(path):
            base = os.path.basename(path)
            parts = base.split("_")
            return parts[2] if len(parts) > 2 else "99999999"
        files = sorted(files, key=start_token)
        print(f"  [{symbol}] WARNING: {len(files)} candidate CSVs found, "
              f"using widest-history one: {os.path.basename(files[0])}")
    df = pd.read_csv(files[0], index_col=0, parse_dates=True)
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


def make_model(model_name: str, feature_names: list[str]):
    if model_name == "logistic":
        return Tier1LogisticSignal(feature_names)
    if model_name == "rf":
        return Tier2RandomForestSignal(feature_names, n_estimators=100)
    raise ValueError(f"unknown model {model_name!r}")


def active_cost_pct() -> float:
    return CRYPTO_COST_THRESHOLD_PCT if COST_MODE == "crypto" else EQUITY_COST_THRESHOLD_PCT


def fee_per_side() -> float:
    return active_cost_pct() / 4.0


def fit_fold_model(train_df: pd.DataFrame, model_name: str):
    train_feats = build_feature_matrix(train_df)
    train_labels = build_labels(train_df["close"], HORIZON, active_cost_pct(), direction="long")
    kept, _ = prune_redundant(train_feats, train_labels, corr_threshold=0.9)
    fit_n = min(250_000, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = make_model(model_name, kept).fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
    return model, train_feats


def resolve_stressed(path: np.ndarray, protective: float,
                      gap_extra: float = 0.0, slip_mult: float = 1.0, entry_delay: int = 0):
    if entry_delay > 0:
        if entry_delay >= len(path) - 1:
            return None
        new_entry = path[entry_delay]
        path = (1 + path[entry_delay:]) / (1 + new_entry) - 1.0
    fps = fee_per_side()
    cost = (fps + fps * slip_mult) * 2
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


def process_fold(symbol, fold_i, train_df, test_df, model_name):
    model, train_feats = fit_fold_model(train_df, model_name)
    train_proba = model.predict_proba(train_feats)
    valid_proba = train_proba.dropna()
    if len(valid_proba) < 20:
        return None, None, None, "TRAIN scores unavailable"
    if GATE_MODE == "fixed070":
        selection_cut = FIXED_GATE_THRESHOLD
    else:
        selection_cut = float(valid_proba.quantile(SELECTION_QUANTILE))
    train_selected = train_proba > selection_cut

    # TASKS_A_E.md Task C: FILTER_MODE controls which of {model gate,
    # range_pos/vol filter} are active. "model_filters" = configuration D
    # (frozen, default). Cut values are always computed the same way
    # (median over whichever population "owns" them per condition) so the
    # comparison isolates gate-vs-filter contribution, not a cut-formula change.
    if FILTER_MODE == "generic":
        gate_mask = pd.Series(True, index=train_feats.index)
        use_filter = False
    elif FILTER_MODE == "filters_only":
        gate_mask = pd.Series(True, index=train_feats.index)
        use_filter = True
    elif FILTER_MODE == "model_only":
        gate_mask = train_selected
        use_filter = False
    else:  # "model_filters" -- configuration D
        gate_mask = train_selected
        use_filter = True

    if FILTER_MODE in ("model_only", "model_filters") and gate_mask.sum() < 20:
        return None, None, None, f"TRAIN population too small after {GATE_MODE} cut"

    if use_filter:
        range_pos_cut = train_feats.loc[gate_mask, "range_pos_60"].median()
        vol_cut = train_feats.loc[gate_mask, "realized_vol_30"].median()
        train_mask = gate_mask & (train_feats["range_pos_60"] < range_pos_cut) & (train_feats["realized_vol_30"] > vol_cut)
    else:
        range_pos_cut = vol_cut = None
        train_mask = gate_mask

    train_close = train_df["close"].to_numpy()
    train_filtered = train_mask.to_numpy()
    train_trades = build_trades_with_mae_mfe(
        train_close, train_filtered,
        train_feats["ema_slope_20"].to_numpy(), train_feats["ret_1"].to_numpy(),
        horizon=HORIZON)
    if len(train_trades) < 10:
        return None, None, None, "TRAIN trade population too small"
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)

    test_feats = build_feature_matrix(test_df)
    test_proba = model.predict_proba(test_feats)
    if FILTER_MODE == "generic":
        test_gate = pd.Series(True, index=test_feats.index)
    elif FILTER_MODE == "filters_only":
        test_gate = pd.Series(True, index=test_feats.index)
    elif FILTER_MODE == "model_only":
        test_gate = test_proba > selection_cut
    else:
        test_gate = test_proba > selection_cut
    if use_filter:
        test_filtered = (test_gate & (test_feats["range_pos_60"] < range_pos_cut) & (test_feats["realized_vol_30"] > vol_cut)).to_numpy()
    else:
        test_filtered = test_gate.to_numpy()
    test_close = test_df["close"].to_numpy()
    seq_trades = build_trades_with_mae_mfe(
        test_close, test_filtered,
        test_feats["ema_slope_20"].to_numpy(), test_feats["ret_1"].to_numpy(),
        horizon=HORIZON)
    if len(seq_trades) == 0:
        return {"n_trades": 0, "reason": "no TEST entries", "selection_cut": selection_cut}, [], {}, None

    # Generic (unfiltered, unselected) dip population on the same TEST window,
    # for the Section 11 baseline comparison -- any bar, no model/filter.
    generic_mask = np.ones(len(test_close), dtype=bool)
    generic_trades = build_trades_with_mae_mfe(
        test_close, generic_mask,
        test_feats["ema_slope_20"].to_numpy(), test_feats["ret_1"].to_numpy(),
        horizon=HORIZON)
    generic_mfe = np.mean([t["mfe"] for t in generic_trades]) if generic_trades else float("nan")
    generic_mae = np.mean([abs(t["mae"]) for t in generic_trades]) if generic_trades else float("nan")
    selected_mfe = float(np.mean([t["mfe"] for t in seq_trades]))
    selected_mae = float(np.mean([abs(t["mae"]) for t in seq_trades]))

    notional = CAPITAL * RISK_PCT
    export_rows = []
    raw_pnls, exec_pnls, n_forced = [], [], 0
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
        exec_ret = raw_return - active_cost_pct()  # (fee_per_side*2)*2 == full RT cost
        export_rows.append({
            "symbol": symbol, "fold": fold_i, "model": model_name,
            "entry_time": entry_time, "exit_time": exit_time,
            "raw_return": raw_return, "exec_return": exec_ret,
            "stop_distance": stop_distance, "leverage_safe": leverage,
            "was_stopped": was_stopped, "mfe": t["mfe"], "mae": t["mae"],
        })
        n_forced += int(was_stopped and liq_move <= stop_distance)
        raw_pnls.append(raw_return * notional * leverage)
        exec_pnls.append(exec_ret * notional * leverage)

    def pf_of(pnls):
        pnls = np.array(pnls)
        wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
        return float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")

    raw_pnls, exec_pnls = np.array(raw_pnls), np.array(exec_pnls)
    eq = CAPITAL + np.cumsum(exec_pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    summary = {
        "n_trades": len(exec_pnls),
        "selection_cut": selection_cut,
        "profit_factor_raw": round(pf_of(raw_pnls), 3),
        "profit_factor_exec": round(pf_of(exec_pnls), 3),
        "total_return_pct_raw": round(raw_pnls.sum() / CAPITAL * 100, 3),
        "total_return_pct_exec": round(exec_pnls.sum() / CAPITAL * 100, 3),
        "max_dd_pct": round(float(dd.min() * 100), 3),
        "win_rate_pct": round((exec_pnls > 0).mean() * 100, 1),
        "stop_distance_pct": round(stop_distance * 100, 3),
        "leverage": round(leverage, 2),
        "n_forced_liq": n_forced,
        "selected_mfe": round(selected_mfe, 5), "selected_mae": round(selected_mae, 5),
        "generic_mfe": round(float(generic_mfe), 5), "generic_mae": round(float(generic_mae), 5),
        "mfe_over_mae_selected": round(selected_mfe / selected_mae, 3) if selected_mae else float("nan"),
        "mfe_over_mae_generic": round(float(generic_mfe) / float(generic_mae), 3) if generic_mae else float("nan"),
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
        stress[label] = {"n": len(spnls), "pf": pf_of(spnls), "ret": spnls.sum() / CAPITAL * 100}

    return summary, export_rows, stress, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--model", choices=("logistic", "rf"), required=True)
    parser.add_argument("--max-folds", type=int, default=3)
    parser.add_argument("--gate", choices=("topdecile", "fixed070"), default="topdecile",
                         help="TASKS_A_E.md Task A only -- D (frozen, default)=topdecile")
    parser.add_argument("--cost", choices=("equity", "crypto"), default="equity",
                         help="TASKS_A_E.md Task A only -- D (frozen, default)=equity")
    parser.add_argument("--filter-mode", choices=("model_filters", "generic", "filters_only", "model_only"),
                         default="model_filters",
                         help="TASKS_A_E.md Task C only -- D (frozen, default)=model_filters")
    parser.add_argument("--tag", default="",
                         help="output-filename suffix, e.g. _configA -- required whenever "
                              "--gate/--cost/--filter-mode deviate from D's defaults, so D's "
                              "own files (no tag) are never overwritten")
    args = parser.parse_args()
    symbol = args.symbol.upper()

    global GATE_MODE, COST_MODE, FILTER_MODE
    GATE_MODE, COST_MODE, FILTER_MODE = args.gate, args.cost, args.filter_mode
    if (GATE_MODE != "topdecile" or COST_MODE != "equity" or FILTER_MODE != "model_filters") and not args.tag:
        raise SystemExit("--tag is required when --gate/--cost/--filter-mode deviate from "
                          "configuration D (prevents silently overwriting D's frozen output files)")

    full = _load_full_cached(symbol)
    n = len(full)
    data_start = full.index[0]
    safe_end = full.index[int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))]
    initial, test_m, step_m, adapted = decide_fold_params(data_start, safe_end)
    if adapted:
        print(f"[{symbol}/{args.model}] ADAPTED fold params (short history): "
              f"INITIAL_TRAIN={initial}mo TEST={test_m}mo STEP={step_m}mo "
              f"span={(safe_end - data_start).days} days")
    folds = build_folds(data_start, safe_end, initial, test_m, step_m)
    print(f"[{symbol}/{args.model}] {len(folds)} walk-forward folds, data {data_start:%Y-%m-%d} -> "
          f"safe_end(HOLDOUT_START)={safe_end:%Y-%m-%d}")

    os.makedirs(OUT_DIR, exist_ok=True)
    summary_path = os.path.join(OUT_DIR, f"own_asset_{symbol}_{args.model}{args.tag}_summary.csv")
    export_path = os.path.join(OUT_DIR, f"own_asset_{symbol}_{args.model}{args.tag}_trades.csv")
    stress_path = os.path.join(OUT_DIR, f"own_asset_{symbol}_{args.model}{args.tag}_stress.csv")
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
        summary, erows, stress, skip_reason = process_fold(symbol, fold_i, train_df, test_df, args.model)
        if summary is None:
            print(f"  {symbol}: {skip_reason}")
            summary_rows.append({"fold": fold_i, "symbol": symbol, "model": args.model,
                                  "n_trades": 0, "reason": skip_reason})
        elif summary.get("n_trades", 0) == 0:
            print(f"  {symbol}: {summary.get('reason', 'no trades')}")
            summary_rows.append({"fold": fold_i, "symbol": symbol, "model": args.model, **summary})
        else:
            print(f"  {symbol}: n={summary['n_trades']:>3} "
                  f"PF_raw={summary['profit_factor_raw']:>7.3f} PF_exec={summary['profit_factor_exec']:>7.3f} "
                  f"ret_exec={summary['total_return_pct_exec']:>+7.3f}% DD={summary['max_dd_pct']:>+7.3f}% "
                  f"win%={summary['win_rate_pct']:>5.1f} MFE/MAE sel={summary['mfe_over_mae_selected']:.2f} "
                  f"gen={summary['mfe_over_mae_generic']:.2f}")
            summary_rows.append({"fold": fold_i, "symbol": symbol, "model": args.model,
                                  "train_start": t0, "train_end": train_end, "test_end": test_end, **summary})
            export_rows.extend(erows)
            srow = {"fold": fold_i, "symbol": symbol, "model": args.model}
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
        print(f"\nFolds still remaining for {symbol}/{args.model}: {remaining} -- rerun to continue.")
        return

    df_res = pd.DataFrame(summary_rows)
    sub = df_res[df_res.get("n_trades", 0) > 0] if len(df_res) else df_res
    print("\n" + "=" * 100)
    print(f"  {symbol}/{args.model} OWN-ASSET WALK-FORWARD SUMMARY ({len(sub)}/{len(folds)} folds with trades)")
    print("=" * 100)
    if len(sub) == 0:
        print(f"{symbol}/{args.model}: no fold produced trades -- TYPE 1/2 candidate, see failure taxonomy")
    else:
        pf = sub["profit_factor_exec"].replace([np.inf], np.nan).dropna()
        print(f"  total n_trades={sub['n_trades'].sum()}  mean PF_exec={pf.mean():.3f}  median PF_exec={pf.median():.3f}  "
              f"%% folds PF_exec>1: {(sub['profit_factor_exec'] > 1).mean() * 100:.1f}%")
        print(f"  worst fold PF_exec={sub['profit_factor_exec'].min():.3f}  best fold PF_exec={sub['profit_factor_exec'].max():.3f}")
    print(f"\nSaved -> {summary_path}\n         {export_path}\n         {stress_path}")


if __name__ == "__main__":
    main()
