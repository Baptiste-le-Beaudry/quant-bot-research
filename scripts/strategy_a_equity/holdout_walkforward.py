"""scripts/strategy_a_equity/holdout_walkforward.py -- STRATEGY_ID =
A-EQUITY, configuration D, preregistered one-shot HOLDOUT test
(docs/strategy_a_equity/A_FAIRE_HOLDOUT_REENTRAINEMENT.md, Sections 2-3).

Reuses the frozen own_asset_walkforward.py machinery unchanged (imported,
not copied): same safe_end (80% of bars), same fold cadence from
data_start (expanding TRAIN, 3-month TEST, 3-month step), same
process_fold. The only difference: it keeps ONLY the folds whose whole
TEST window lies in the HOLDOUT (train_end >= safe_end, test_end <= last
cached bar), where the frozen script keeps the folds before safe_end.
Outputs go to outputs/strategy_a_equity/holdout/ so configuration D's own
files are never overwritten.

Usage:
    python scripts/strategy_a_equity/holdout_walkforward.py --symbol AMZN --model rf --list-folds
    python scripts/strategy_a_equity/holdout_walkforward.py --symbol AMZN --model rf
    python scripts/strategy_a_equity/holdout_walkforward.py --aggregate
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

from scripts.strategy_a_equity import own_asset_walkforward as wf
from scripts.strategy_a_equity.own_asset_walkforward import (
    STD_INITIAL_TRAIN_MONTHS, STD_STEP_MONTHS, STD_TEST_MONTHS, TRAIN_FRACTION,
    VALIDATION_FRACTION, _load_full_cached, process_fold,
)

# ---- PREREGISTERED (A_FAIRE_HOLDOUT_REENTRAINEMENT.md Section 2) ----
UNIVERSE = ["ADBE", "AMZN", "AVGO", "BA", "BABA", "COST", "CRM", "CSCO",
            "MA", "MCD", "MU", "PEP", "QCOM", "TXN", "V"]
MODELS = ["rf", "logistic"]
PASS_MIN_SYMBOLS = 9
FAIL_MAX_SYMBOLS = 5
# ----------------------------------------------------------------------

OUT_DIR = os.path.join(wf.OUT_DIR, "holdout")


def holdout_folds(full: pd.DataFrame):
    n = len(full)
    data_start = full.index[0]
    safe_end = full.index[int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))]
    data_end = full.index[-1]
    # Every universe symbol has >= 30 months before safe_end, so the frozen
    # script used the standard cadence; assert rather than silently adapt.
    _, _, _, adapted = wf.decide_fold_params(data_start, safe_end)
    if adapted:
        raise SystemExit("short history -> adapted fold params; not preregistered")
    folds = []
    train_end = data_start + pd.DateOffset(months=STD_INITIAL_TRAIN_MONTHS)
    while True:
        test_end = train_end + pd.DateOffset(months=STD_TEST_MONTHS)
        if test_end > data_end:
            break
        if train_end >= safe_end:
            folds.append((data_start, train_end, test_end))
        train_end = train_end + pd.DateOffset(months=STD_STEP_MONTHS)
    return folds, safe_end, data_end


def paths(symbol, model):
    base = os.path.join(OUT_DIR, f"own_asset_{symbol}_{model}_holdout")
    return base + "_summary.csv", base + "_trades.csv", base + "_stress.csv"


def run(symbol, model, list_only):
    full = _load_full_cached(symbol)
    folds, safe_end, data_end = holdout_folds(full)
    print(f"[{symbol}/{model}] {len(folds)} HOLDOUT folds, safe_end={safe_end:%Y-%m-%d} "
          f"data_end={data_end:%Y-%m-%d}")
    if list_only:
        for i, (_, a, b) in enumerate(folds, 1):
            print(f"  fold {i}: TEST[{a:%Y-%m-%d}->{b:%Y-%m-%d}]")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    summary_path, export_path, stress_path = paths(symbol, model)
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

    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        if fold_i in done_folds:
            continue
        train_df = full[(full.index >= t0) & (full.index < train_end)]
        test_df = full[(full.index >= train_end) & (full.index < test_end)]
        print(f"FOLD {fold_i}/{len(folds)}: TRAIN[{t0:%Y-%m-%d}->{train_end:%Y-%m-%d}] "
              f"TEST[{train_end:%Y-%m-%d}->{test_end:%Y-%m-%d}] "
              f"(train_n={len(train_df):,} test_n={len(test_df):,})", flush=True)
        summary, erows, stress, skip_reason = process_fold(symbol, fold_i, train_df, test_df, model)
        if summary is None:
            print(f"  {symbol}: {skip_reason}")
            summary_rows.append({"fold": fold_i, "symbol": symbol, "model": model,
                                  "n_trades": 0, "reason": skip_reason})
        elif summary.get("n_trades", 0) == 0:
            print(f"  {symbol}: {summary.get('reason', 'no trades')}")
            summary_rows.append({"fold": fold_i, "symbol": symbol, "model": model, **summary})
        else:
            print(f"  {symbol}: n={summary['n_trades']:>3} PF_exec={summary['profit_factor_exec']:>7.3f} "
                  f"ret_exec={summary['total_return_pct_exec']:>+7.3f}%", flush=True)
            summary_rows.append({"fold": fold_i, "symbol": symbol, "model": model,
                                  "train_start": t0, "train_end": train_end, "test_end": test_end, **summary})
            export_rows.extend(erows)
            srow = {"fold": fold_i, "symbol": symbol, "model": model}
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
    print(f"[{symbol}/{model}] HOLDOUT complete -> {summary_path}")


def aggregate():
    rows, expectancy = [], {}
    for model in MODELS:
        rets = []
        for symbol in UNIVERSE:
            summary_path, export_path, _ = paths(symbol, model)
            s = pd.read_csv(summary_path)
            t = s[s.n_trades > 0]
            rows.append({
                "symbol": symbol, "model": model,
                "n_folds_traded": len(t), "n_trades": int(t.n_trades.sum()),
                "median_pf_exec": round(t.profit_factor_exec.median(), 3) if len(t) else np.nan,
                "pct_folds_pf_gt1": round((t.profit_factor_exec > 1).mean() * 100, 1) if len(t) else np.nan,
                "mean_mfe_mae_sel": round(t.mfe_over_mae_selected.mean(), 3) if len(t) else np.nan,
                "mean_mfe_mae_gen": round(t.mfe_over_mae_generic.mean(), 3) if len(t) else np.nan,
                "total_return_exec": round(t.total_return_pct_exec.sum(), 2) if len(t) else 0.0,
            })
            if os.path.exists(export_path) and os.path.getsize(export_path) > 1:
                rets.append(pd.read_csv(export_path).exec_return)
        expectancy[model] = float(pd.concat(rets).mean()) if rets else float("nan")
    agg = pd.DataFrame(rows)
    agg.to_csv(os.path.join(OUT_DIR, "AGGREGATE_holdout_results.csv"), index=False)

    pf = agg.pivot(index="symbol", columns="model", values="median_pf_exec")
    passing = sorted(pf.index[(pf > 1).all(axis=1)])
    n_pass = len(passing)
    exp_pos = all(expectancy[m] > 0 for m in MODELS)
    exp_nonpos = all(expectancy[m] <= 0 for m in MODELS)
    if n_pass >= PASS_MIN_SYMBOLS and exp_pos:
        verdict = "PASS"
    elif exp_nonpos or n_pass <= FAIL_MAX_SYMBOLS:
        verdict = "FAIL"
    else:
        verdict = "PARTIAL"
    print(agg.to_string(index=False))
    print(f"\nSymbols passing (median PF_exec > 1, both models): {n_pass}/{len(UNIVERSE)} {passing}")
    for m in MODELS:
        print(f"Trade-weighted expectancy {m}: {expectancy[m] * 100:+.4f}% per trade")
    print(f"VERDICT: {verdict}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol")
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--list-folds", action="store_true")
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    if args.aggregate:
        aggregate()
        return
    if not args.symbol or not args.model:
        parser.error("--symbol and --model are required unless --aggregate")
    symbol = args.symbol.upper()
    if symbol not in UNIVERSE:
        raise SystemExit(f"{symbol} is not in the preregistered universe")
    run(symbol, args.model, args.list_folds)


if __name__ == "__main__":
    main()
