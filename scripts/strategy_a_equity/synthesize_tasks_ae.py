"""Reproducible post-hoc aggregation for Strategy A-Equity Tasks A-E.

Reads only the frozen pre-HOLDOUT exports. It does not fit a model, tune a
parameter, or access HOLDOUT data. The main purpose is to make Task C's final
comparison auditable and to expose the headline counts used by the A-E report.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "strategy_a_equity"
SYMBOLS = ["AMD", "PLTR", "UBER", "INTC", "BAC", "FB", "NFLX", "GOOGL",
           "PYPL", "DIS", "JNJ", "PG", "KO", "XOM", "WMT"]
MODELS = ["rf", "logistic"]
CONDITIONS = {
    "generic": "_1generic",
    "filters_only": "_2filtersonly",
    "model_only": "_3modelonly",
    "model_filters_D": "",
}


def read_trades(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=["symbol", "fold", "model", "exec_return",
                                     "mfe", "mae"])


def metrics(path: Path) -> dict[str, float | int]:
    frame = read_trades(path)
    if frame.empty:
        return {"n": 0, "pf_exec": np.nan, "expectancy_exec_pct": np.nan,
                "mfe_mae": np.nan}
    wins = frame.loc[frame.exec_return > 0, "exec_return"].sum()
    losses = -frame.loc[frame.exec_return < 0, "exec_return"].sum()
    pf = wins / losses if losses > 0 else np.inf
    mae = -frame.mae.mean()
    return {
        "n": int(len(frame)),
        "pf_exec": float(pf),
        "expectancy_exec_pct": float(100 * frame.exec_return.mean()),
        "mfe_mae": float(frame.mfe.mean() / mae) if mae > 0 else np.nan,
    }


def task_c() -> tuple[pd.DataFrame, dict]:
    rows = []
    for symbol in SYMBOLS:
        for model in MODELS:
            for condition, suffix in CONDITIONS.items():
                path = OUT / f"own_asset_{symbol}_{model}{suffix}_trades.csv"
                rows.append({"symbol": symbol, "model": model,
                             "condition": condition, **metrics(path)})
    detail = pd.DataFrame(rows)
    aggregate = []
    for condition, group in detail.groupby("condition", sort=False):
        paths = []
        suffix = CONDITIONS[condition]
        for symbol in SYMBOLS:
            for model in MODELS:
                paths.append(read_trades(
                    OUT / f"own_asset_{symbol}_{model}{suffix}_trades.csv"))
        all_trades = pd.concat(paths, ignore_index=True)
        aggregate.append({"condition": condition, **metrics_frame(all_trades),
                          "median_cell_pf": float(group.pf_exec.median()),
                          "cells_pf_gt1": int((group.pf_exec > 1).sum())})
    agg = pd.DataFrame(aggregate).set_index("condition")
    wide = detail.pivot(index=["symbol", "model"], columns="condition")
    d_pf = wide["pf_exec"]["model_filters_D"]
    d_mm = wide["mfe_mae"]["model_filters_D"]
    beats_both_pf = d_pf > wide["pf_exec"][["filters_only", "model_only"]].max(axis=1)
    beats_both_mm = d_mm > wide["mfe_mae"][["filters_only", "model_only"]].max(axis=1)
    synergy = {
        "cells_D_beats_both_on_pf": int(beats_both_pf.sum()),
        "cells_D_beats_both_on_mfe_mae": int(beats_both_mm.sum()),
        "cells_D_beats_both_on_both_metrics": int((beats_both_pf & beats_both_mm).sum()),
        "cells_total": int(len(beats_both_pf)),
        "aggregate": agg.reset_index().to_dict("records"),
    }
    return detail, synergy


def metrics_frame(frame: pd.DataFrame) -> dict[str, float | int]:
    if frame.empty:
        return {"n": 0, "pf_exec": np.nan, "expectancy_exec_pct": np.nan,
                "mfe_mae": np.nan}
    wins = frame.loc[frame.exec_return > 0, "exec_return"].sum()
    losses = -frame.loc[frame.exec_return < 0, "exec_return"].sum()
    mae = -frame.mae.mean()
    return {"n": int(len(frame)), "pf_exec": float(wins / losses),
            "expectancy_exec_pct": float(100 * frame.exec_return.mean()),
            "mfe_mae": float(frame.mfe.mean() / mae)}


def headline_counts() -> dict:
    discovery = pd.read_csv(OUT / "AGGREGATE_own_asset_results.csv")
    discovery = discovery[discovery.kind == "primary"]
    d_both = discovery.pivot(index="symbol", columns="model",
                             values="median_pf_exec")
    confirmation = pd.read_csv(OUT / "AGGREGATE_taskE_confirmation_results.csv")
    e_both = confirmation.pivot(index="symbol", columns="model",
                                values="median_pf_exec")
    fixed = pd.read_csv(OUT / "TASK_D_fixed_exit_results.csv")
    return {
        "discovery_assets_both_models_median_pf_gt1": int((d_both > 1).all(axis=1).sum()),
        "discovery_assets_total": int(len(d_both)),
        "confirmation_assets_both_models_median_pf_gt1": int((e_both > 1).all(axis=1).sum()),
        "confirmation_assets_total": int(len(e_both)),
        "fixed_20m_cells_pf_gt1": int((fixed.pf_20m > 1).sum()),
        "fixed_30m_cells_pf_gt1": int((fixed.pf_30m > 1).sum()),
        "fixed_cells_total": int(len(fixed)),
    }


def task_a() -> list[dict]:
    configs = {"A_fixed070_crypto_cost": "_configA",
               "B_topdecile_crypto_cost": "_configB",
               "C_fixed070_equity_cost": "_configC",
               "D_topdecile_equity_cost": ""}
    rows = []
    for label, suffix in configs.items():
        frames = []
        fold_rows = []
        for symbol in SYMBOLS:
            for model in MODELS:
                frames.append(read_trades(
                    OUT / f"own_asset_{symbol}_{model}{suffix}_trades.csv"))
                fold_rows.append(pd.read_csv(
                    OUT / f"own_asset_{symbol}_{model}{suffix}_summary.csv"))
        trades = pd.concat(frames, ignore_index=True)
        folds = pd.concat(fold_rows, ignore_index=True)
        traded = folds[folds.n_trades > 0]
        rows.append({"configuration": label, **metrics_frame(trades),
                     "folds": int(len(folds)),
                     "folds_with_trades": int(len(traded)),
                     "population_failure_fraction": float(1 - len(traded) / len(folds)),
                     "median_fold_pf": float(traded.profit_factor_exec.median()),
                     "pct_folds_pf_gt1": float(100 * (traded.profit_factor_exec > 1).mean())})
    return rows


def task_b() -> dict:
    rows = []
    for model in MODELS:
        frame = pd.read_csv(OUT / f"pooled_{model}_trades.csv")
        for symbol, group in frame.groupby("symbol"):
            rows.append({"symbol": symbol, "model": model, **metrics_frame(group)})
    detail = pd.DataFrame(rows)
    both = detail.pivot(index="symbol", columns="model", values="pf_exec")
    return {"assets_both_models_pf_gt1": int((both > 1).all(axis=1).sum()),
            "assets_either_model_pf_gt1": int((both > 1).any(axis=1).sum()),
            "assets_total": int(len(both)), "detail": rows}


def main() -> None:
    detail, synergy = task_c()
    detail.to_csv(OUT / "AGGREGATE_taskC_filter_ablation.csv", index=False)
    result = {"task_a": task_a(), "task_b": task_b(), "task_c": synergy,
              "headline_counts": headline_counts()}
    path = OUT / "TASKS_A_E_SYNTHESIS.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
