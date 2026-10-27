"""Exp 63 (C-REBOUND-CONFIRM-001) -- check that the REF models reproduce the Exp 53 REF signals.

Preregistration docs/agents/hypotheses/Exp-63.md, rule C step 1: reuse the REF models saved by Exp 61 if
their signals equal Exp 53's (check to report). Exp 61 saved REF models for folds 1-4 and 10-19 only
(outputs/exp61/model_REF_fold_NN.pkl in worktree agent-ab9ddce1f6630a26d); folds 5-9 are retrained here
exactly as scripts/agents/exp61_signals.py does (BTC+ETH pooled TRAIN, label 10 min, prune_redundant 0.9,
RF 100 trees, 250 000-row sample, random_state 42) and saved under --work-dir.

For every fold 1-19 and every symbol SOL/BTC/ETH: TEST probabilities -> REF rule (p > 0.70, range_pos_60 <
cut, realized_vol_30 > cut, cutoffs read from the Exp 53 checkpoint) -> signal times, compared with the
Exp 53 checkpoint signals (exact equality). Output: --work-dir/model_check.json. Read-only on Exp 53/61.

  python scripts/agents/exp63_verify_models.py
"""
from __future__ import annotations

import argparse
import gc
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.agents.exp53_label50 import (ALL_SYMS, FEATURES, H_REF, THRESHOLD_REF, TRAIN_SYMS, Pooled,  # noqa: E402
                                          fit_model, log, predict, prune_redundant_lowmem, signal_mask,
                                          train_labels)
from scripts.agents.exp61_signals import EXP53  # noqa: E402

EXP61 = Path("C:/AAProjet/quant_bot_v1/.claude/worktrees/agent-ab9ddce1f6630a26d/outputs/exp61")


def signals_for(model, feats: np.ndarray, times: np.ndarray, cut) -> np.ndarray:
    rng_j, vol_j = FEATURES.index("range_pos_60"), FEATURES.index("realized_vol_30")
    p = predict(model, feats, FEATURES)
    m = signal_mask(p, np.asarray(feats[:, rng_j]), np.asarray(feats[:, vol_j]), THRESHOLD_REF, cut)
    return np.asarray(times)[m]


def same(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(len(a) == len(b) and (np.sort(np.asarray(a)) == np.sort(np.asarray(b))).all())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default=str(ROOT / "outputs" / "exp63"))
    ap.add_argument("--n-jobs", type=int, default=4)
    a = ap.parse_args(argv)
    work = Path(a.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    folds = json.loads((EXP53 / "folds.json").read_text())
    mm = {s: np.load(EXP53 / f"feats_{s}.npy", mmap_mode="r") for s in ALL_SYMS}
    times = {s: np.load(EXP53 / f"times_{s}.npy") for s in ALL_SYMS}
    close = {s: np.load(EXP53 / f"close_{s}.npy", mmap_mode="r") for s in TRAIN_SYMS}
    ts = {s: pd.DatetimeIndex(times[s]).tz_localize("UTC") for s in ALL_SYMS}
    out = {"folds": {}}
    for k in range(1, len(folds) + 1):
        t0, train_end, test_end = (pd.Timestamp(x) for x in folds[k - 1])
        with open(EXP53 / f"fold_{k:02d}.pkl", "rb") as fh:
            ck = pickle.load(fh)
        src = EXP61 / f"model_REF_fold_{k:02d}.pkl"
        mine = work / f"model_REF_fold_{k:02d}.pkl"
        if src.exists():
            origin = "exp61_saved"
            with open(src, "rb") as fh:
                model = pickle.load(fh)
        elif mine.exists():
            origin = "exp63_retrained"
            with open(mine, "rb") as fh:
                model = pickle.load(fh)
        else:
            origin = "exp63_retrained"
            log(f"fold {k}: retraining REF (TRAIN {t0:%Y-%m-%d} -> {train_end:%Y-%m-%d})")
            blocks, ys = [], []
            for s in TRAIN_SYMS:
                i0, i1 = ts[s].searchsorted(t0), ts[s].searchsorted(train_end)
                blocks.append(mm[s][i0:i1])
                ys.append(train_labels(np.asarray(close[s][i0:i1]), H_REF))
            X, y = Pooled(blocks), np.concatenate(ys)
            kept = prune_redundant_lowmem(X, y, FEATURES)
            if kept != ck["info"]["REF_kept"]:
                raise SystemExit(f"STOP fold {k}: kept features differ from Exp 53")
            model = fit_model(X, y, FEATURES, kept, a.n_jobs)
            del X, y, blocks, ys
            gc.collect()
            with open(mine, "wb") as fh:
                pickle.dump(model, fh)
        row = {"origin": origin, "kept_equal": list(model.feature_names) == ck["info"]["REF_kept"]}
        for s in ALL_SYMS:
            i0, i1 = ts[s].searchsorted(train_end), ts[s].searchsorted(test_end)
            sig = signals_for(model, mm[s][i0:i1], times[s][i0:i1], ck["info"]["cutoffs"]["REF"][s])
            ref = np.asarray(ck["signals"]["REF"][s])
            row[s] = {"n_model": int(len(sig)), "n_exp53": int(len(ref)), "equal": same(sig, ref)}
        out["folds"][k] = row
        log(f"fold {k} ({origin}): " + ", ".join(f"{s[:3]} {row[s]['n_model']}/{row[s]['n_exp53']} "
                                                 f"{'OK' if row[s]['equal'] else 'DIFF'}" for s in ALL_SYMS))
        del model
        gc.collect()
    out["all_equal"] = all(r[s]["equal"] and r["kept_equal"] for r in out["folds"].values() for s in ALL_SYMS)
    (work / "model_check.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"all_equal": out["all_equal"]}))


if __name__ == "__main__":
    main()
