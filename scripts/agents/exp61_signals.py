"""Exp 61 (A-JUP-SOLTOKENS-001) -- per-fold REF signals on the Solana tokens.

Preregistration: docs/agents/hypotheses/Exp-61.md (commit 5dc8b95). Signal = REF model of Exp 53
(scripts/agents/exp53_label50.py): BTC+ETH pooled TRAIN, label 10 min, prune_redundant(0.9), RF 100
trees depth 5, 250 000-row sample (random_state 42), threshold 0.70, range_pos_60 / realized_vol_30
median cutoffs of the TRAIN-selected population pooled over BTC+ETH ("as for SOL"). No per-token tuning.

The Exp 53 / Exp 58 checkpoints hold signal times only (no model, no probabilities), so REF is
retrained per fold (deterministic, random_state 42) from the Exp 53 feature arrays (read only,
memory-mapped). Check per fold: the retrained model's SOL TEST signals must equal the Exp 53 checkpoint
exactly (else STOP). The pooled cutoffs are read from the Exp 53 checkpoint (cutoffs["REF"]["SOLUSDT"]),
i.e. computed by Exp 53 on TRAIN only.

Tokens (fixed a priori): JUP, JTO, PYTH, RAY, WIF, BONK. Binance USDT-M symbols: JUPUSDT, JTOUSDT,
PYTHUSDT, RAYSOLUSDT, WIFUSDT, 1000BONKUSDT. RAY: the RAYUSDT perpetual was delisted (settled
2022-11-15, archives frozen at 0.248 with zero volume afterwards); the Raydium perpetual relisted on
2024-12-10 as RAYSOLUSDT (base asset RAYSOL; price checked = Binance spot RAYUSDT = Jupiter RAY quote).
Decisional RAY series = RAYSOLUSDT. Diagnostic only (no effect on the verdict): RAYUSDT before the
delisting, symbol key "RAYUSDT_2021".

Eligibility: a token enters at the first TEST fold whose start is >= its first bar + 60 days, and stays
in every later fold. Features are computed once on the token's full series (causal), as for SOL.

  python scripts/agents/exp61_signals.py --stage all
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.config import COST_THRESHOLD_PCT  # noqa: E402,F401
from quant_bot.features.build import build_feature_matrix  # noqa: E402
from scripts.agents.exp53_label50 import (FEATURES, H_REF, THRESHOLD_REF, TRAIN_SYMS, Pooled,  # noqa: E402
                                          fit_model, free_mb, log, predict, prune_redundant_lowmem,
                                          signal_mask, times_ns, train_labels)

TOKENS = {"JUPUSDT": "JUPUSDT", "JTOUSDT": "JTOUSDT", "PYTHUSDT": "PYTHUSDT", "RAYSOLUSDT": "RAYSOLUSDT",
          "WIFUSDT": "WIFUSDT", "1000BONKUSDT": "1000BONKUSDT"}
DIAG = {"RAYUSDT_2021": "RAYUSDT"}
RAYUSDT_SETTLE = pd.Timestamp("2022-11-15 04:00", tz="UTC")  # fapi exchangeInfo deliveryDate 1668484800000
MIN_HISTORY = pd.Timedelta(days=60)
DATA = Path("C:/AAProjet/quant_bot_v1/data/exp61")
EXP53 = Path("C:/AAProjet/quant_bot_v1/.claude/worktrees/agent-a17639c9ee2636b1f/outputs/exp53")


def token_bars(key: str, data_dir: Path = DATA) -> pd.DataFrame:
    sym = {**TOKENS, **DIAG}[key]
    df = pd.read_pickle(data_dir / f"{sym}_full.pkl")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    if key == "RAYUSDT_2021":
        df = df[df.index < RAYUSDT_SETTLE]
    if not (df.index.is_monotonic_increasing and df.index.is_unique):
        raise ValueError(f"{key}: bar index not strictly increasing")
    return df


def build_token_arrays(key: str, work: Path, data_dir: Path = DATA) -> None:
    f = work / f"feats_{key}.npy"
    if f.exists() and (work / f"times_{key}.npy").exists():
        return
    df = token_bars(key, data_dir)
    feats = build_feature_matrix(df)
    if list(feats.columns) != FEATURES:
        raise ValueError(f"feature list changed: {list(feats.columns)}")
    arr = np.empty((len(feats), len(FEATURES)), dtype=np.float32)
    for j, c in enumerate(FEATURES):
        arr[:, j] = feats[c].to_numpy(dtype=np.float32)
    np.save(work / f"times_{key}.npy", times_ns(df.index))
    np.save(work / f"tmp_{key}.npy", arr)
    os.replace(work / f"tmp_{key}.npy", f)
    log(f"features {key}: {len(arr)} rows")
    del df, feats, arr
    gc.collect()


def first_eligible_fold(first_bar: pd.Timestamp, folds: list) -> int | None:
    """1-based index of the first fold whose TEST start (= train_end) is >= first_bar + 60 days."""
    for k, (_, train_end, _) in enumerate(folds, 1):
        if pd.Timestamp(train_end) >= first_bar + MIN_HISTORY:
            return k
    return None


def token_signals(model, feats: np.ndarray, times: np.ndarray, cut) -> tuple[np.ndarray, np.ndarray]:
    """TEST signal times (int64 ns) and probabilities at the signal bars, REF rule (0.70, pooled cutoffs)."""
    rng_j, vol_j = FEATURES.index("range_pos_60"), FEATURES.index("realized_vol_30")
    p = predict(model, feats, FEATURES)
    m = signal_mask(p, np.asarray(feats[:, rng_j]), np.asarray(feats[:, vol_j]), THRESHOLD_REF, cut)
    return np.asarray(times)[m], p[m]


def stage_folds(work: Path, n_jobs: int, min_free_mb: float, keys: list[str]) -> None:
    folds = json.loads((EXP53 / "folds.json").read_text())
    mm = {s: np.load(EXP53 / f"feats_{s}.npy", mmap_mode="r") for s in (*TRAIN_SYMS, "SOLUSDT")}
    times = {s: np.load(EXP53 / f"times_{s}.npy") for s in (*TRAIN_SYMS, "SOLUSDT")}
    close = {s: np.load(EXP53 / f"close_{s}.npy", mmap_mode="r") for s in TRAIN_SYMS}
    ts = {s: pd.DatetimeIndex(times[s]).tz_localize("UTC") for s in times}
    tok_t = {k: np.load(work / f"times_{k}.npy") for k in keys}
    tok_f = {k: np.load(work / f"feats_{k}.npy", mmap_mode="r") for k in keys}
    tok_ts = {k: pd.DatetimeIndex(tok_t[k]).tz_localize("UTC") for k in keys}
    elig = {k: first_eligible_fold(tok_ts[k][0], folds) for k in keys}
    last = {k: len(folds) if k != "RAYUSDT_2021" else
            max(i for i, f in enumerate(folds, 1) if pd.Timestamp(f[1]) < tok_ts[k][-1]) for k in keys}
    (work / "eligibility.json").write_text(json.dumps(
        {k: {"first_bar": str(tok_ts[k][0]), "last_bar": str(tok_ts[k][-1]), "first_fold": elig[k],
             "last_fold": last[k],
             "first_test_start": folds[elig[k] - 1][1] if elig[k] else None} for k in keys}, indent=1))
    needed = sorted({i for k in keys if elig[k] for i in range(elig[k], last[k] + 1)})
    log(f"eligibility {elig}; folds to train {needed}")
    for k in needed:
        out = work / f"fold_{k:02d}.pkl"
        if out.exists():
            continue
        while free_mb() < min_free_mb:
            log(f"waiting before fold {k}: free memory below {min_free_mb} MB")
            time.sleep(60)
        t0, train_end, test_end = (pd.Timestamp(x) for x in folds[k - 1])
        with open(EXP53 / f"fold_{k:02d}.pkl", "rb") as fh:
            ck = pickle.load(fh)
        log(f"fold {k}: TRAIN {t0:%Y-%m-%d} -> {train_end:%Y-%m-%d}, TEST -> {test_end:%Y-%m-%d}")
        blocks, ys = [], []
        for s in TRAIN_SYMS:
            a, b = ts[s].searchsorted(t0), ts[s].searchsorted(train_end)
            blocks.append(mm[s][a:b])
            ys.append(train_labels(np.asarray(close[s][a:b]), H_REF))
        X, y = Pooled(blocks), np.concatenate(ys)
        kept = prune_redundant_lowmem(X, y, FEATURES)
        if kept != ck["info"]["REF_kept"]:
            raise SystemExit(f"STOP fold {k}: kept features differ from Exp 53 ({kept} vs {ck['info']['REF_kept']})")
        model = fit_model(X, y, FEATURES, kept, n_jobs)
        del X, y, blocks, ys
        gc.collect()
        cut = ck["info"]["cutoffs"]["REF"]["SOLUSDT"]
        a, b = ts["SOLUSDT"].searchsorted(train_end), ts["SOLUSDT"].searchsorted(test_end)
        sol_sig, _ = token_signals(model, mm["SOLUSDT"][a:b], times["SOLUSDT"][a:b], cut)
        ref_sol = np.asarray(ck["signals"]["REF"]["SOLUSDT"])
        check = bool(len(sol_sig) == len(ref_sol) and (np.sort(sol_sig) == np.sort(ref_sol)).all())
        if not check:
            raise SystemExit(f"STOP fold {k}: SOL TEST signals {len(sol_sig)} != Exp 53 {len(ref_sol)}")
        res = {"fold": {"k": k, "train_start": str(t0), "train_end": str(train_end), "test_end": str(test_end)},
               "kept": kept, "pooled_cutoff": cut, "sol_check_equal": check, "sol_signals": len(sol_sig),
               "signals": {}, "probs": {}, "test_rows": {}}
        for key in keys:
            if not (elig[key] and elig[key] <= k <= last[key]):
                continue
            a, b = tok_ts[key].searchsorted(train_end), tok_ts[key].searchsorted(test_end)
            sig, pr = token_signals(model, tok_f[key][a:b], tok_t[key][a:b], cut)
            res["signals"][key], res["probs"][key], res["test_rows"][key] = sig, pr, int(b - a)
        with open(work / f"model_REF_fold_{k:02d}.pkl", "wb") as fh:
            pickle.dump(model, fh)
        with open(work / f"tmp_fold_{k:02d}.pkl", "wb") as fh:
            pickle.dump(res, fh)
        os.replace(work / f"tmp_fold_{k:02d}.pkl", out)
        log(f"fold {k} done: SOL check {check} ({len(sol_sig)}) | token signal bars "
            f"{ {kk: len(v) for kk, v in res['signals'].items()} }")
        del model, res
        gc.collect()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["features", "folds", "all"], default="all")
    ap.add_argument("--work-dir", default=str(ROOT / "outputs" / "exp61"))
    ap.add_argument("--n-jobs", type=int, default=4)
    ap.add_argument("--min-free-mb", type=float, default=1200)
    a = ap.parse_args(argv)
    if a.n_jobs > 4:
        raise SystemExit("n_jobs capped at 4 (memory rule)")
    work = Path(a.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    keys = list(TOKENS) + list(DIAG)
    if a.stage in ("features", "all"):
        for k in keys:
            build_token_arrays(k, work)
    if a.stage in ("folds", "all"):
        stage_folds(work, a.n_jobs, a.min_free_mb, keys)


if __name__ == "__main__":
    main()
