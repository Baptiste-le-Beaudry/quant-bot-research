"""Exp 58 (A-JUP-THRESH-001) -- probability-threshold stability, DIAGNOSTIC, executed to the letter of
docs/agents/hypotheses/Exp-58.md (commit 402efb4). Adopts no threshold.

Model: REF of Exp 53 (scripts/agents/exp53_label50.py), reused as is: same 19-fold 24/3/3 grid, BTC+ETH
pooled TRAIN, label 10 min, prune_redundant(0.9), RF 100 trees, 250 000-row sample (random_state 42).
The Exp 53 checkpoints only hold the TEST signal times at 0.70 (no per-bar probabilities), so REF is
retrained per fold (deterministic: random_state 42); its 0.70 TEST signals are checked against the Exp 53
checkpoints (equality reported per fold). The Exp 53 feature/close/time arrays are read memory-mapped,
READ ONLY, from --feat-dir.

Per threshold in THRESHOLDS (6 values, no other): range_pos_60 / realized_vol_30 median cutoffs of the
TRAIN-selected population recomputed at that threshold (per symbol for BTC/ETH, BTC+ETH pooled for SOL, as
the deployed code and Exp 53). Execution identical to Exp 53: signals sequenced one position per symbol,
harness entry next open, time exit 50 bars without stop, cost jupiter_build (principal only), account
500 CAD 33 %, P1 / P2 split at 2025-04-01 00:00 UTC, fixed calendar periods as Exp 53.

Points not fixed by the preregistration -- fixed HERE, before any computation:
  * "net/trade" in the reading rule = pooled SOL+BTC+ETH mean net at size (net_ret_at_size, notional
    116.14 USD), as the Exp 53 criteria.
  * "% plis net > 0" = share of folds (with >= 1 trade in the period) whose pooled mean net at size > 0;
    a fold is the TEST window of the signal time; fold 14 straddles 2025-04-01 and counts in both periods.
  * "par annee" = calendar year of the signal time (UTC).
  * Reading: STABLE if in P1 and P2 the net/trade at 0.65 and at 0.75 is within +-0.05 point of 0.70 and of
    the same sign; FRAGILE if, in P1 or P2, 0.65 or 0.75 has the opposite sign of 0.70 or differs by
    > 0.10 point; otherwise INTERMEDIAIRE (neither, reported as such). If a neighbour threshold has 0
    trades in a period (net undefined; seen in fold-1 bar counts before any harness result: the REF
    RF rarely exceeds 0.75), it cannot be STABLE: FRAGILE if another comparison triggers it, else
    INDETERMINE.

Memory: same guards as Exp 53 (one Python process, n_jobs <= 4, float32 memmaps, wait if free memory is low).
Stages: --stage folds | harness | all.
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
from scripts.agents.exp53_label50 import (ALL_SYMS, DEFAULT_CACHE, FEATURES, FRACTION, H_REF, HOLD_BARS,  # noqa: E402
                                          INITIAL_CAD, P2_START, TRAIN_SYMS, Pooled, cutoffs, fit_model,
                                          free_mb, log, predict, prune_redundant_lowmem, sequence, signal_mask,
                                          train_labels)

THRESHOLDS = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85)
REF_THR = 0.70
STABLE_TOL, FRAGILE_TOL = 0.05, 0.10
PLATFORM = "jupiter_build"
DEFAULT_FEAT = Path("C:/AAProjet/quant_bot_v1/.claude/worktrees/agent-a17639c9ee2636b1f/outputs/exp53")


def thr_key(t: float) -> str:
    return f"{t:.2f}"


def threshold_signals(p_train: dict, tr_rng: dict, tr_vol: dict, p_test: dict, te_rng: dict, te_vol: dict,
                      te_times: dict, thresholds=THRESHOLDS) -> dict:
    """TRAIN-only cutoffs per threshold (per symbol BTC/ETH, pooled for SOL) -> TEST signal times.
    p_train/tr_*: {BTC, ETH} TRAIN arrays; p_test/te_*: {SOL, BTC, ETH} TEST arrays."""
    out = {}
    for t in thresholds:
        per = {s: cutoffs(p_train[s], tr_rng[s], tr_vol[s], t) for s in TRAIN_SYMS}
        pooled = cutoffs(np.concatenate([p_train[s] for s in TRAIN_SYMS]),
                         np.concatenate([tr_rng[s] for s in TRAIN_SYMS]),
                         np.concatenate([tr_vol[s] for s in TRAIN_SYMS]), t)
        cut = {"BTCUSDT": per["BTCUSDT"], "ETHUSDT": per["ETHUSDT"], "SOLUSDT": pooled}
        train_bars = sum(int(signal_mask(p_train[s], tr_rng[s], tr_vol[s], t, per[s]).sum()) for s in TRAIN_SYMS)
        sig = {s: np.asarray(te_times[s])[signal_mask(p_test[s], te_rng[s], te_vol[s], t, cut[s])] for s in ALL_SYMS}
        out[thr_key(t)] = {"cutoffs": cut, "train_signal_bars": train_bars, "signals": sig}
    return out


def run_fold_ref(train: dict, test: dict, n_jobs: int = 4) -> dict:
    X = Pooled([train[s][0] for s in TRAIN_SYMS])
    rj, vj = FEATURES.index("range_pos_60"), FEATURES.index("realized_vol_30")
    y = np.concatenate([train_labels(train[s][1], H_REF) for s in TRAIN_SYMS])
    kept = prune_redundant_lowmem(X, y, FEATURES)
    model = fit_model(X, y, FEATURES, kept, n_jobs)
    del y
    p_tr = {s: predict(model, train[s][0], FEATURES) for s in TRAIN_SYMS}
    tr_rng = {s: np.asarray(train[s][0][:, rj]) for s in TRAIN_SYMS}
    tr_vol = {s: np.asarray(train[s][0][:, vj]) for s in TRAIN_SYMS}
    p_te = {s: predict(model, test[s][0], FEATURES) for s in ALL_SYMS}
    te_rng = {s: np.asarray(test[s][0][:, rj]) for s in ALL_SYMS}
    te_vol = {s: np.asarray(test[s][0][:, vj]) for s in ALL_SYMS}
    res = threshold_signals(p_tr, tr_rng, tr_vol, p_te, te_rng, te_vol, {s: test[s][1] for s in ALL_SYMS})
    del model, X
    gc.collect()
    return {"kept": kept, "thresholds": res}


def stage_folds(feat: Path, work: Path, n_jobs: int, min_free_mb: float) -> None:
    mm = {s: np.load(feat / f"feats_{s}.npy", mmap_mode="r") for s in ALL_SYMS}
    times = {s: np.load(feat / f"times_{s}.npy", mmap_mode="r") for s in ALL_SYMS}
    close = {s: np.load(feat / f"close_{s}.npy", mmap_mode="r") for s in TRAIN_SYMS}
    ts = {s: pd.DatetimeIndex(np.asarray(times[s])).tz_localize("UTC") for s in ALL_SYMS}
    folds = [tuple(pd.Timestamp(x) for x in f) for f in json.loads((feat / "folds.json").read_text())]
    log(f"{len(folds)} folds (Exp 53 grid)")
    for k, (t0, train_end, test_end) in enumerate(folds, 1):
        out = work / f"fold_{k:02d}.pkl"
        if out.exists():
            continue
        waited = 0
        while free_mb() < min_free_mb and waited < 60:
            if waited == 0:
                log(f"waiting before fold {k}: free memory below {min_free_mb} MB")
            time.sleep(60)
            waited += 1
        if free_mb() < min_free_mb:
            log(f"STOP before fold {k}: free memory below {min_free_mb} MB for 60 min; rerun to resume")
            return
        log(f"fold {k}: TRAIN {t0:%Y-%m-%d} -> {train_end:%Y-%m-%d}, TEST -> {test_end:%Y-%m-%d}")
        tr = {}
        for s in TRAIN_SYMS:
            a, b = ts[s].searchsorted(t0), ts[s].searchsorted(train_end)
            tr[s] = (mm[s][a:b], np.asarray(close[s][a:b]))
        te = {}
        for s in ALL_SYMS:
            a, b = ts[s].searchsorted(train_end), ts[s].searchsorted(test_end)
            te[s] = (mm[s][a:b], np.asarray(times[s][a:b]))
        res = run_fold_ref(tr, te, n_jobs)
        # reproduction check vs Exp 53 REF at 0.70 (read-only checkpoint)
        repro = None
        ref_path = feat / f"fold_{k:02d}.pkl"
        if ref_path.exists():
            with open(ref_path, "rb") as fh:
                e53 = pickle.load(fh)
            mine = res["thresholds"][thr_key(REF_THR)]["signals"]
            repro = {s: bool(np.array_equal(np.asarray(mine[s]), np.asarray(e53["signals"]["REF"][s]))) for s in ALL_SYMS}
            repro["kept_equal"] = res["kept"] == e53["info"]["REF_kept"]
        res["repro_exp53_ref_070"] = repro
        res["fold"] = {"k": k, "train_start": str(t0), "train_end": str(train_end), "test_end": str(test_end)}
        with open(work / f"tmp_fold_{k:02d}.pkl", "wb") as fh:
            pickle.dump(res, fh)
        os.replace(work / f"tmp_fold_{k:02d}.pkl", out)
        log(f"fold {k} done: repro {repro} | test bars "
            f"{ {t: sum(len(v) for v in d['signals'].values()) for t, d in res['thresholds'].items()} }")
        del tr, te, res
        gc.collect()


# ----------------------------------------------------------------------------- harness

def fold_of(signal_times: pd.Series, folds: list) -> np.ndarray:
    starts = pd.DatetimeIndex([pd.Timestamp(f[1]) for f in folds])
    return starts.searchsorted(pd.DatetimeIndex(signal_times), side="right")  # 1-based fold number


def reading(net: dict, tol_stable: float = STABLE_TOL, tol_fragile: float = FRAGILE_TOL) -> dict:
    """net[period][thr_key] -> pooled net/trade (points of %)."""
    stable, fragile, undefined, detail = True, False, False, {}
    for pop, d in net.items():
        ref = d[thr_key(REF_THR)]
        for t in (0.65, 0.75):
            x = d.get(thr_key(t), np.nan)
            if not (np.isfinite(x) and np.isfinite(ref)):  # 0 trade at that threshold: net undefined
                detail[f"{pop}_{thr_key(t)}"] = {"net": x, "net_070": ref, "abs_dev": np.nan, "same_sign": None}
                stable, undefined = False, True
                continue
            same = np.sign(x) == np.sign(ref)
            dev = abs(x - ref)
            detail[f"{pop}_{thr_key(t)}"] = {"net": x, "net_070": ref, "abs_dev": dev, "same_sign": bool(same)}
            stable &= bool(same and dev <= tol_stable)
            fragile |= bool((not same) or dev > tol_fragile)
    lab = "STABLE" if stable else ("FRAGILE" if fragile else ("INDETERMINE" if undefined else "INTERMEDIAIRE"))
    return {"detail": detail, "reading": lab}


def stage_harness(feat: Path, work: Path, cache_dir: Path, out_dir: Path, date: str) -> dict:
    from quant_bot.execution_harness import (VERSION, USD_PER_CAD, ExitRule, apply_costs, load_bars,
                                             profit_factor, run_trades, simulate_account)
    folds = json.loads((feat / "folds.json").read_text())
    res = []
    for k in range(1, len(folds) + 1):
        with open(work / f"fold_{k:02d}.pkl", "rb") as fh:
            res.append(pickle.load(fh))
    test_start, data_end_excl = pd.Timestamp(folds[0][1]), pd.Timestamp(folds[-1][2])
    periods = {"P1": (test_start, P2_START), "P2": (P2_START, data_end_excl)}
    notional = INITIAL_CAD * USD_PER_CAD.value * FRACTION
    rule = ExitRule(max_bars=HOLD_BARS)
    loader = lambda s: load_bars(s, cache_dir)  # noqa: E731
    rows, years, fold_rows, accounts = [], [], [], []
    net = {p: {} for p in periods}
    for thr in THRESHOLDS:
        key = thr_key(thr)
        cands = []
        for s in ALL_SYMS:
            tms = np.load(feat / f"times_{s}.npy", mmap_mode="r")
            sig = np.unique(np.concatenate([r["thresholds"][key]["signals"][s] for r in res]))
            idx = np.searchsorted(tms, sig)
            assert (np.asarray(tms)[idx] == sig).all()
            seq = sequence(idx)
            cands.append(pd.DataFrame({"symbol": s, "signal_time": pd.DatetimeIndex(np.asarray(tms)[seq]).tz_localize("UTC"),
                                       "side": 1}))
        cand = pd.concat(cands, ignore_index=True)
        if cand.empty:  # no TEST signal at this threshold in any fold: n = 0, net undefined
            for pop in periods:
                for sym in list(ALL_SYMS) + ["POOLED"]:
                    rows.append({"threshold": key, "period": pop, "symbol": sym, "n": 0})
                net[pop][key] = np.nan
                accounts.append({"threshold": key, "period": pop, "n_trades": 0})
            log(f"harness thr {key}: 0 candidates")
            continue
        sim = run_trades(cand, rule, PLATFORM, loader, entry_mode="next_open", notional_usd=notional)
        sim["period"] = np.where(sim.signal_time < P2_START, "P1", "P2")
        sim["fold"] = fold_of(sim.signal_time, folds)
        sim["year"] = pd.DatetimeIndex(sim.signal_time).year
        t = apply_costs(sim, PLATFORM, notional_usd=notional)
        n_bad = int((t.status != "ok").sum())
        for pop, (p0, p1) in periods.items():
            ok = t[(t.status == "ok") & (t.period == pop)]
            for sym in list(ALL_SYMS) + ["POOLED"]:
                x = ok if sym == "POOLED" else ok[ok.symbol == sym]
                r = x.net_ret_at_size
                fm = x.groupby("fold").net_ret_at_size.mean()
                rows.append({"threshold": key, "period": pop, "symbol": sym, "n": len(x),
                             "mean_gross_pct": 100 * x.gross_ret.mean(), "mean_net_pct_at_size": 100 * r.mean(),
                             "pf_at_size": profit_factor(r), "win_rate": float((r > 0).mean()) if len(x) else np.nan,
                             "t_stat": float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if len(r) > 1 else np.nan,
                             "n_folds": int(len(fm)), "share_folds_net_pos": float((fm > 0).mean()) if len(fm) else np.nan,
                             "n_not_ok": n_bad if sym == "POOLED" else np.nan})
                if sym == "POOLED":
                    net[pop][key] = 100 * float(r.mean())
            tt = t.copy()
            tt.loc[(tt.period != pop) & (tt.status == "ok"), "status"] = "other_period"
            a = simulate_account(tt, PLATFORM, INITIAL_CAD, USD_PER_CAD.value, position_fraction=FRACTION,
                                 max_gross_exposure=1.0, one_position_per_symbol=True, period=(p0, p1))
            accounts.append({"threshold": key, "period": pop, "period_start": str(p0), "period_end": str(p1),
                             **{k: v for k, v in a.items() if k not in ("ledger", "equity_minute", "skips")},
                             **{f"skip_{k}": v for k, v in a.get("skips", {}).items()}})
        okall = t[t.status == "ok"]
        for (yr, sym), g in pd.concat([okall, okall.assign(symbol="POOLED")]).groupby(["year", "symbol"]):
            r = g.net_ret_at_size
            years.append({"threshold": key, "year": int(yr), "symbol": sym, "n": len(g),
                          "mean_net_pct_at_size": 100 * r.mean(), "pf_at_size": profit_factor(r)})
        for f, g in okall.groupby("fold"):
            r = g.net_ret_at_size
            fold_rows.append({"threshold": key, "fold": int(f), "n": len(g), "mean_net_pct_at_size": 100 * r.mean(),
                              "pf_at_size": profit_factor(r)})
        log(f"harness thr {key}: {len(sim)} sequenced candidates, net P1 {net['P1'][key]:.4f} P2 {net['P2'][key]:.4f}")
    pt, yr, fd, ac = pd.DataFrame(rows), pd.DataFrame(years), pd.DataFrame(fold_rows), pd.DataFrame(accounts)
    read = reading(net)
    repro = {r["fold"]["k"]: r["repro_exp53_ref_070"] for r in res}
    out = {"harness_version": VERSION, "platform": PLATFORM, "notional_usd_at_33pct": notional,
           "thresholds": [thr_key(t) for t in THRESHOLDS], "periods": {k: [str(a), str(b)] for k, (a, b) in periods.items()},
           "pooled_net_pct": net, "reading": read, "repro_exp53_ref_070_by_fold": repro,
           "train_signal_bars": {r["fold"]["k"]: {k: v["train_signal_bars"] for k, v in r["thresholds"].items()} for r in res}}
    out_dir.mkdir(parents=True, exist_ok=True)
    pt.to_csv(out_dir / f"Exp-58_{date}_per_trade.csv", index=False)
    yr.to_csv(out_dir / f"Exp-58_{date}_years.csv", index=False)
    fd.to_csv(out_dir / f"Exp-58_{date}_folds.csv", index=False)
    ac.to_csv(out_dir / f"Exp-58_{date}_accounts.csv", index=False)
    (out_dir / f"Exp-58_{date}_criteria.json").write_text(json.dumps(out, indent=2, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(pt.round(4).to_string())
    print(ac[["threshold", "period", "n_trades", "total_return_cad_pct", "cagr_cad_pct", "max_dd_pct", "worst_day_pct",
              "pf_usd"]].round(3).to_string())
    print(json.dumps({k: out[k] for k in ("pooled_net_pct", "reading", "repro_exp53_ref_070_by_fold")}, indent=2, default=str))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["folds", "harness", "all"], default="all")
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE), help="bars cache (read only)")
    ap.add_argument("--feat-dir", default=str(DEFAULT_FEAT), help="Exp 53 arrays + checkpoints (read only)")
    ap.add_argument("--work-dir", default=str(ROOT / "outputs" / "exp58"))
    ap.add_argument("--out-dir", default=str(ROOT / "docs" / "agents" / "results"))
    ap.add_argument("--date", default="2026-10-07")
    ap.add_argument("--n-jobs", type=int, default=4)
    ap.add_argument("--min-free-mb", type=float, default=1200)
    a = ap.parse_args(argv)
    if a.n_jobs > 4:
        raise SystemExit("n_jobs capped at 4 (memory rule)")
    feat, work = Path(a.feat_dir), Path(a.work_dir)
    if feat.resolve() == work.resolve():
        raise SystemExit("work dir must differ from the read-only Exp 53 dir")
    work.mkdir(parents=True, exist_ok=True)
    if a.stage in ("folds", "all"):
        stage_folds(feat, work, a.n_jobs, a.min_free_mb)
    if a.stage in ("harness", "all"):
        stage_harness(feat, work, Path(a.cache_dir), Path(a.out_dir), a.date)


if __name__ == "__main__":
    main()
