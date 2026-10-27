"""scripts/strategy_a_equity/pooled_walkforward.py -- Task B pooled equity
model (docs/strategy_a_equity/STRATEGY_A_EQUITY_TASKS_A_E.md). ONE model
per walk-forward period, fit on the union of all 15 discovery-sample
symbols' TRAIN rows for that period; TEST scored and reported per symbol.
Configuration D's frozen gate/cost/filters/model-specs/walk-forward-shape/
cost-model are reused unmodified -- this is the "one equity-wide dip
model" architecture test, not a retune.

Fold alignment: computed once, symbol-agnostic, using the shortest common
pre-HOLDOUT span across the 15 symbols (data_start = latest per-symbol
start i.e. PLTR/UBER's 2020-10-01; safe_end = earliest per-symbol 80%-
mark). Strict causality: TRAIN/TEST boundaries are the same calendar
dates for every symbol in a fold, so no symbol's TEST-period row can ever
appear in another symbol's TRAIN.

Usage:
    python scripts/strategy_a_equity/pooled_walkforward.py --model rf --max-folds 3
    python scripts/strategy_a_equity/pooled_walkforward.py --model logistic --max-folds 3
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades_with_mae_mfe
from scripts.strategy_a_equity.own_asset_walkforward import (
    _load_full_cached, decide_fold_params, build_folds, make_model,
    resolve_stressed, HORIZON, EQUITY_COST_THRESHOLD_PCT, SELECTION_QUANTILE,
    ACTIVATE_AT, TRAIL_DIST, STOP_PCT_PERCENTILE, SAFETY_MARGIN,
    MAX_LEVERAGE_CAP, CAPITAL, RISK_PCT, TRAIN_FRACTION, VALIDATION_FRACTION,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PRIMARY = ["AMD", "PLTR", "UBER", "INTC", "BAC", "FB", "NFLX", "GOOGL",
           "PYPL", "DIS", "JNJ", "PG", "KO", "XOM", "WMT"]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "outputs", "strategy_a_equity")


def pooled_fold_bounds(series_by_symbol: dict[str, pd.DataFrame]):
    data_starts, safe_ends = [], []
    for sym, df in series_by_symbol.items():
        n = len(df)
        data_starts.append(df.index[0])
        safe_ends.append(df.index[int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))])
    return max(data_starts), min(safe_ends)


def build_pooled_train(series_by_symbol: dict[str, pd.DataFrame], t0, train_end):
    """Per-symbol feature computation (rolling windows must never mix
    symbols), then concatenated into one pooled TRAIN matrix."""
    frames, labels = [], []
    for sym, full in series_by_symbol.items():
        train_df = full[(full.index >= t0) & (full.index < train_end)]
        if len(train_df) < 300:
            continue
        feats = build_feature_matrix(train_df)
        lbl = build_labels(train_df["close"], HORIZON, EQUITY_COST_THRESHOLD_PCT, direction="long")
        feats["_symbol"] = sym
        frames.append(feats)
        labels.append(lbl)
    pooled_feats = pd.concat(frames)
    pooled_labels = pd.concat(labels)
    pooled_labels.index = range(len(pooled_labels))
    pooled_feats.index = range(len(pooled_feats))
    return pooled_feats, pooled_labels


def process_pooled_fold(fold_i, series_by_symbol, t0, train_end, test_end, model_name):
    pooled_feats, pooled_labels = build_pooled_train(series_by_symbol, t0, train_end)
    symbol_col = pooled_feats.pop("_symbol")
    feature_cols = [c for c in pooled_feats.columns]
    kept, _ = prune_redundant(pooled_feats[feature_cols], pooled_labels, corr_threshold=0.9)
    fit_n = min(250_000, len(pooled_feats))
    fit_idx = pooled_feats.sample(n=fit_n, random_state=42).index
    model = make_model(model_name, kept).fit(pooled_feats.loc[fit_idx, kept], pooled_labels.loc[fit_idx])

    pooled_proba = model.predict_proba(pooled_feats[kept])
    valid = pooled_proba.dropna()
    if len(valid) < 20:
        return None, None, "pooled TRAIN scores unavailable"
    selection_cut = float(valid.quantile(SELECTION_QUANTILE))
    pooled_selected = pooled_proba > selection_cut
    if pooled_selected.sum() < 20:
        return None, None, "pooled TRAIN population too small after top-decile cut"
    range_pos_cut = pooled_feats.loc[pooled_selected, "range_pos_60"].median()
    vol_cut = pooled_feats.loc[pooled_selected, "realized_vol_30"].median()

    # stop_distance/leverage: derived from the POOLED selected-TRAIN MAE
    # distribution (one shared value per fold, applied to every symbol) --
    # matches the "one equity-wide dip model" architecture, not a per-symbol
    # tune. Recomputed per symbol (not sliced from the pooled frame) to
    # avoid any index-alignment risk between the reset pooled index and
    # each symbol's own feature rows.
    stop_maes = []
    for sym, full in series_by_symbol.items():
        train_df = full[(full.index >= t0) & (full.index < train_end)]
        if len(train_df) < 300:
            continue
        feats = build_feature_matrix(train_df)
        proba = model.predict_proba(feats[kept])
        sel = (proba > selection_cut) & (feats["range_pos_60"] < range_pos_cut) & (feats["realized_vol_30"] > vol_cut)
        trades = build_trades_with_mae_mfe(
            train_df["close"].to_numpy(), sel.fillna(False).to_numpy(),
            feats["ema_slope_20"].to_numpy(), feats["ret_1"].to_numpy(), horizon=HORIZON)
        stop_maes.extend(abs(t["mae"]) for t in trades)
    if len(stop_maes) < 10:
        return None, None, "pooled TRAIN trade population too small"
    stop_distance = float(np.percentile(stop_maes, STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)

    notional = CAPITAL * RISK_PCT
    per_symbol_rows = []
    export_rows = []
    for sym, full in series_by_symbol.items():
        test_df = full[(full.index >= train_end) & (full.index < test_end)]
        if len(test_df) < 30:
            continue
        test_feats = build_feature_matrix(test_df)
        test_proba = model.predict_proba(test_feats[kept])
        test_filtered = ((test_proba > selection_cut) & (test_feats["range_pos_60"] < range_pos_cut) & (test_feats["realized_vol_30"] > vol_cut)).fillna(False).to_numpy()
        test_close = test_df["close"].to_numpy()
        seq_trades = build_trades_with_mae_mfe(
            test_close, test_filtered, test_feats["ema_slope_20"].to_numpy(),
            test_feats["ret_1"].to_numpy(), horizon=HORIZON)
        if not seq_trades:
            continue
        raw_pnls, exec_pnls = [], []
        for t in seq_trades:
            i = t["entry_idx"]
            path = t["close_path"]
            peak, activated = -np.inf, False
            raw_return, exit_offset = None, len(path) - 1
            for j, x in enumerate(path):
                if x <= -protective:
                    raw_return, exit_offset = -protective, j
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
            exec_ret = raw_return - EQUITY_COST_THRESHOLD_PCT
            raw_pnls.append(raw_return * notional * leverage)
            exec_pnls.append(exec_ret * notional * leverage)
            export_rows.append({"symbol": sym, "fold": fold_i, "model": model_name,
                                 "entry_time": test_df.index[i], "raw_return": raw_return,
                                 "exec_return": exec_ret, "mfe": t["mfe"], "mae": t["mae"]})
        raw_pnls, exec_pnls = np.array(raw_pnls), np.array(exec_pnls)
        wins, losses = exec_pnls[exec_pnls > 0], exec_pnls[exec_pnls <= 0]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
        per_symbol_rows.append({
            "fold": fold_i, "symbol": sym, "n_trades": len(exec_pnls),
            "profit_factor_exec": round(pf, 3),
            "total_return_pct_exec": round(exec_pnls.sum() / CAPITAL * 100, 3),
            "mean_mfe": round(float(np.mean([t["mfe"] for t in seq_trades])), 5),
            "mean_mae": round(float(np.mean([abs(t["mae"]) for t in seq_trades])), 5),
        })
    return per_symbol_rows, export_rows, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("logistic", "rf"), required=True)
    parser.add_argument("--max-folds", type=int, default=3)
    args = parser.parse_args()

    series_by_symbol = {sym: _load_full_cached(sym) for sym in PRIMARY}
    data_start, safe_end = pooled_fold_bounds(series_by_symbol)
    print(f"[POOLED/{args.model}] common data_start={data_start:%Y-%m-%d} "
          f"safe_end(HOLDOUT_START)={safe_end:%Y-%m-%d} "
          f"(driven by PLTR/UBER's later start)")
    initial, test_m, step_m, adapted = decide_fold_params(data_start, safe_end)
    if adapted:
        print(f"[POOLED/{args.model}] ADAPTED fold params: "
              f"INITIAL_TRAIN={initial}mo TEST={test_m}mo STEP={step_m}mo")
    folds = build_folds(data_start, safe_end, initial, test_m, step_m)
    print(f"[POOLED/{args.model}] {len(folds)} walk-forward folds")

    os.makedirs(OUT_DIR, exist_ok=True)
    summary_path = os.path.join(OUT_DIR, f"pooled_{args.model}_summary.csv")
    export_path = os.path.join(OUT_DIR, f"pooled_{args.model}_trades.csv")
    done_marker = summary_path + ".done_folds.txt"

    summary_rows, export_rows = [], []
    if os.path.exists(summary_path):
        summary_rows = pd.read_csv(summary_path).to_dict("records")
    if os.path.exists(export_path):
        export_rows = pd.read_csv(export_path).to_dict("records")
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
        print(f"FOLD {fold_i}/{len(folds)}: TRAIN[{t0:%Y-%m-%d}->{train_end:%Y-%m-%d}] "
              f"TEST[{train_end:%Y-%m-%d}->{test_end:%Y-%m-%d}]")
        rows, erows, skip_reason = process_pooled_fold(fold_i, series_by_symbol, t0, train_end, test_end, args.model)
        if rows is None:
            print(f"  POOLED: {skip_reason}")
            summary_rows.append({"fold": fold_i, "symbol": "ALL", "n_trades": 0, "reason": skip_reason})
        else:
            total_n = sum(r["n_trades"] for r in rows)
            print(f"  POOLED: {len(rows)} symbols traded, total n={total_n}")
            for r in rows:
                print(f"    {r['symbol']:6s} n={r['n_trades']:>4} PF={r['profit_factor_exec']:>7.3f} "
                      f"ret={r['total_return_pct_exec']:>+7.3f}%")
            summary_rows.extend(rows)
            export_rows.extend(erows)
        pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
        pd.DataFrame(export_rows).to_csv(export_path, index=False)
        done_folds.add(fold_i)
        with open(done_marker, "w") as f:
            f.write(" ".join(str(x) for x in sorted(done_folds)))
        processed += 1

    remaining = [i for i in range(1, len(folds) + 1) if i not in done_folds]
    if remaining:
        print(f"\nFolds still remaining: {remaining} -- rerun to continue.")
        return
    print(f"\nSaved -> {summary_path}\n         {export_path}")


if __name__ == "__main__":
    main()
