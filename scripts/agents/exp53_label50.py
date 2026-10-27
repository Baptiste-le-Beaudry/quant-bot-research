"""Exp 53 (A-JUP-LABEL50-001) -- label 10 min (REF) vs label 50 min (L50), executed to the letter of
docs/agents/hypotheses/Exp-53.md (commit eacf9f8).

Per walk-forward fold (TRAIN expanding from the BTC/ETH common start, TEST 3 months, 24-month first TRAIN,
same grid as scripts/strategy_a/experiment49_crypto_holdout_walkforward.py run_joint):
  * REF  : deployed pipeline (scripts/build_jupiter_refit_bundle.py) -- BTC+ETH pooled TRAIN,
           label build_labels(close, 10, COST_THRESHOLD_PCT), prune_redundant(0.9), RF 100 trees,
           250 000-row sample (random_state 42), threshold 0.70, range_pos_60 / realized_vol_30 median
           cutoffs of the TRAIN-selected population (per symbol for BTC/ETH, pooled BTC+ETH for SOL).
  * L50  : identical except the label build_labels(close, 50, COST_THRESHOLD_PCT) and the threshold,
           chosen on TRAIN ONLY so that the number of TRAIN signal bars (BTC + ETH, deployed per-symbol
           cutoffs) equals REF's at 0.70.
  * L50_070 (reported, no effect): L50 model at the fixed 0.70 threshold.
Execution: harness v1.1.0, entry next open, time exit 50 bars at the close, no stop, one position per
symbol (signals while a position is open are skipped, as in the Jupiter paper runner), cost jupiter_build
(principal) / jupiter_order (stress, reported), account 500 CAD, 33 % per position.

Memory (machine ~10 GB, often 2-3 GB free): features computed once per symbol into float32 .npy files
under --work-dir and memory-mapped; TRAIN matrices are never materialised (prune/fit/predict work on
chunks and on gathered samples, numerically identical to the pandas code path up to float rounding of
the correlation matrix). RF n_jobs <= 4. One checkpoint file per fold (--work-dir/fold_NN.pkl): a rerun
skips finished folds.

Stages: --stage features | folds | harness | all.
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
from quant_bot.config import COST_THRESHOLD_PCT  # noqa: E402
from quant_bot.features.build import build_feature_matrix, build_labels  # noqa: E402
from quant_bot.signal.model import Tier2RandomForestSignal  # noqa: E402

THRESHOLD_REF = 0.70
H_REF, H_L50 = 10, 50
HOLD_BARS = 50
FIT_ROWS, MI_ROWS, CORR_THRESHOLD = 250_000, 150_000, 0.9
TRAIN_MONTHS, TEST_MONTHS, STEP_MONTHS = 24, 3, 3
P2_START = pd.Timestamp("2025-04-01", tz="UTC")
TRAIN_SYMS, ALL_SYMS = ("BTCUSDT", "ETHUSDT"), ("SOLUSDT", "BTCUSDT", "ETHUSDT")
FEATURES = ["vwap_dist_z_60", "vwap_dist_z_240", "autocorr_60", "autocorr_240", "hurst_120", "ret_1", "ret_5",
            "ret_15", "ret_60", "dist_ema20_atr", "dist_ema50_atr", "dist_ema200_atr", "ema_slope_20",
            "dist_high_60_atr", "dist_low_60_atr", "range_pos_60", "atr_norm", "realized_vol_30",
            "realized_vol_ratio", "range_expansion", "rel_volume_20", "volume_accel", "taker_imbalance_20",
            "volume_to_vol_ratio"]
CHUNK = 400_000
DEFAULT_CACHE = Path("C:/AAProjet/quant_bot_v1/docs/_full_data_cache")
INITIAL_CAD, FRACTION = 500.0, 0.33
COSTS = {"principal_build": "jupiter_build", "stress_order": "jupiter_order"}
VARIANTS = ("REF", "L50", "L50_070")


def free_mb() -> float:
    """Available physical memory in MB (Windows); +inf elsewhere."""
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        s = MS()
        s.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
        return s.ullAvailPhys / 2**20
    except Exception:  # pragma: no cover
        return float("inf")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg} (free {free_mb():.0f} MB)", flush=True)


# ----------------------------------------------------------------------------- features (stage 1)

def times_ns(index: pd.DatetimeIndex) -> np.ndarray:
    """UTC bar open times as int64 NANOseconds whatever the index resolution (pandas 3 may use us)."""
    return index.tz_convert("UTC").tz_localize(None).to_numpy().astype("datetime64[ns]").astype("int64")


def build_symbol_arrays(symbol: str, cache_dir: Path, work: Path) -> None:
    """Full-series causal features (float32), close and bar times saved once per symbol."""
    fpath = work / f"feats_{symbol}.npy"
    if fpath.exists() and (work / f"close_{symbol}.npy").exists() and (work / f"times_{symbol}.npy").exists():
        return
    log(f"features {symbol}: start")
    df = pd.read_pickle(cache_dir / f"{symbol}_full.pkl")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    if not (df.index.is_monotonic_increasing and df.index.is_unique):
        raise ValueError(f"{symbol}: bar index not strictly increasing")
    np.save(work / f"close_{symbol}.npy", df["close"].to_numpy(dtype=np.float64))
    np.save(work / f"times_{symbol}.npy", times_ns(df.index))
    if fpath.exists():
        return
    feats = build_feature_matrix(df)
    del df
    gc.collect()
    if list(feats.columns) != FEATURES:
        raise ValueError(f"feature list changed: {list(feats.columns)}")
    arr = np.empty((len(feats), len(FEATURES)), dtype=np.float32)
    for j, c in enumerate(FEATURES):
        arr[:, j] = feats[c].to_numpy(dtype=np.float32)
    del feats
    gc.collect()
    np.save(work / f"tmp_{symbol}.npy", arr)
    os.replace(work / f"tmp_{symbol}.npy", fpath)
    del arr
    gc.collect()
    log(f"features {symbol}: done")


# ----------------------------------------------------------------------------- building blocks (tested)

def train_labels(close_train: np.ndarray, horizon: int) -> np.ndarray:
    """Label on the TRAIN slice only: fwd = close[t+h]/close[t]-1 with t+h inside the slice (else NaN)."""
    return build_labels(pd.Series(np.asarray(close_train, dtype=np.float64)), horizon,
                        COST_THRESHOLD_PCT, direction="long").to_numpy()


def pandas_sample_positions(n_rows: int, n: int, random_state: int = 42) -> np.ndarray:
    """Positions DataFrame.sample(n=min(n, n_rows), random_state=...) would pick (same order)."""
    return np.random.RandomState(random_state).choice(n_rows, size=min(n, n_rows), replace=False).astype(np.intp)


class Pooled:
    """Row-concatenation of memory-mapped float32 blocks without copying them."""

    def __init__(self, blocks: list[np.ndarray]):
        self.blocks = blocks
        self.offsets = np.cumsum([0] + [len(b) for b in blocks])
        self.n = int(self.offsets[-1])

    def take(self, pos: np.ndarray) -> np.ndarray:
        pos = np.asarray(pos)
        out = np.empty((len(pos), self.blocks[0].shape[1]), dtype=np.float32)
        which = np.searchsorted(self.offsets, pos, side="right") - 1
        for b, blk in enumerate(self.blocks):
            m = which == b
            if m.any():
                out[m] = blk[pos[m] - self.offsets[b]]
        return out

    def chunks(self):
        for b, blk in enumerate(self.blocks):
            for i in range(0, len(blk), CHUNK):
                yield int(self.offsets[b] + i), np.asarray(blk[i:i + CHUNK])


def valid_rows(X: Pooled) -> np.ndarray:
    v = np.empty(X.n, dtype=bool)
    for start, c in X.chunks():
        v[start:start + len(c)] = ~np.isnan(c).any(axis=1)
    return v


def corr_abs(X: Pooled, rows: np.ndarray) -> np.ndarray:
    """|Pearson correlation| on the selected rows, two-pass, float64 accumulation, chunked."""
    k = X.blocks[0].shape[1]
    s, n = np.zeros(k), 0
    for start, c in X.chunks():
        m = rows[start:start + len(c)]
        x = c[m].astype(np.float64)
        s += x.sum(axis=0)
        n += len(x)
    mean = s / n
    cp = np.zeros((k, k))
    for start, c in X.chunks():
        m = rows[start:start + len(c)]
        x = c[m].astype(np.float64) - mean
        cp += x.T @ x
    d = np.sqrt(np.diag(cp))
    return np.abs(cp / np.outer(d, d))


def prune_redundant_lowmem(X: Pooled, y: np.ndarray, names: list[str], corr_threshold: float = CORR_THRESHOLD,
                           random_state: int = 42, max_rows: int = MI_ROWS) -> list[str]:
    """Same algorithm/order as quant_bot.features.pipeline.prune_redundant (classification)."""
    from sklearn.feature_selection import mutual_info_classif
    valid = valid_rows(X) & ~np.isnan(y)
    vpos = np.flatnonzero(valid)
    if len(vpos) == 0:
        raise ValueError("No valid (non-NaN) rows to compute redundancy on")
    pick = vpos[pandas_sample_positions(len(vpos), max_rows, random_state)] if len(vpos) > max_rows else vpos
    X_mi = pd.DataFrame(X.take(pick), columns=names)
    mi = mutual_info_classif(X_mi, y[pick], random_state=random_state)
    order = pd.Series(mi, index=names).sort_values(ascending=False).index
    corr = pd.DataFrame(corr_abs(X, valid), index=names, columns=names)
    kept = []
    for f in order:
        if next((k for k in kept if corr.loc[f, k] > corr_threshold), None) is None:
            kept.append(f)
    return kept


def fit_model(X: Pooled, y: np.ndarray, names: list[str], kept: list[str], n_jobs: int) -> Tier2RandomForestSignal:
    """X.sample(n=250000, random_state=42) then Tier2RandomForestSignal(kept, 100).fit (deployed)."""
    pos = pandas_sample_positions(X.n, FIT_ROWS, 42)
    Xs = pd.DataFrame(X.take(pos), columns=names)
    ys = pd.Series(y[pos])
    model = Tier2RandomForestSignal(kept, n_estimators=100)
    model.model.n_jobs = n_jobs
    model.fit(Xs, ys)
    return model


def predict(model: Tier2RandomForestSignal, block: np.ndarray, names: list[str]) -> np.ndarray:
    """model.predict_proba on a (rows x all features) float32 block, chunked; NaN where a kept feature is NaN."""
    cols = [names.index(f) for f in model.feature_names]
    out = np.full(len(block), np.nan)
    for i in range(0, len(block), CHUNK):
        c = np.asarray(block[i:i + CHUNK])[:, cols]
        ok = ~np.isnan(c).any(axis=1)
        if ok.any():
            out[i:i + len(c)][ok] = model.model.predict_proba(pd.DataFrame(c[ok], columns=model.feature_names))[:, 1]
    return out


def cutoffs(p: np.ndarray, rng: np.ndarray, vol: np.ndarray, thr: float):
    """Median range_pos_60 / realized_vol_30 of the TRAIN-selected population (pandas median skips NaN)."""
    sel = p > thr
    if sel.sum() < 20:
        return None
    return float(np.nanmedian(rng[sel].astype(np.float64))), float(np.nanmedian(vol[sel].astype(np.float64)))


def signal_mask(p, rng, vol, thr, cut):
    if cut is None:
        return np.zeros(len(p), dtype=bool)
    with np.errstate(invalid="ignore"):
        return (p > thr) & (rng < cut[0]) & (vol > cut[1])


def train_signal_count(train: dict, thr: float) -> int:
    """Signal bars on TRAIN with the deployed BTC/ETH rule (per-symbol cutoffs): sum over BTC and ETH.
    ``train`` = {sym: (p, range_pos_60, realized_vol_30)} -- TRAIN arrays only."""
    n = 0
    for p, rng, vol in train.values():
        n += int(signal_mask(p, rng, vol, thr, cutoffs(p, rng, vol, thr)).sum())
    return n


def calibrate_threshold(train: dict, target: int, iters: int = 40) -> tuple[float, int]:
    """Threshold whose TRAIN signal count is closest to ``target`` (bisection on [0, 1]; the count is
    non-increasing in the threshold up to the median-cutoff feedback). Ties -> the higher threshold.
    Uses TRAIN arrays only."""
    lo, hi = 0.0, 1.0
    best = (1.0, train_signal_count(train, 1.0))
    for _ in range(iters):
        mid = (lo + hi) / 2
        c = train_signal_count(train, mid)
        if abs(c - target) < abs(best[1] - target) or (abs(c - target) == abs(best[1] - target) and mid > best[0]):
            best = (mid, c)
        if c > target:
            lo = mid
        elif c < target:
            hi = mid
        else:
            lo = mid  # equal: keep moving up to find the highest threshold with this count
    return best


def sequence(sig_idx: np.ndarray, hold: int = HOLD_BARS) -> np.ndarray:
    """One position per symbol: after a signal at bar s (entry s+1, exit at the close of s+hold), the next
    accepted signal is >= s+hold (the runner evaluates exits before entries on that bar)."""
    out, nxt = [], -1
    for s in np.sort(np.asarray(sig_idx)):
        if s >= nxt:
            out.append(int(s))
            nxt = s + hold
    return np.asarray(out, dtype=np.int64)


# ----------------------------------------------------------------------------- folds (stage 2)

def fold_grid(data_start: pd.Timestamp, data_end: pd.Timestamp) -> list[tuple]:
    """24/3/3 expanding grid (Exp 49 run_joint); a final partial TEST window up to the end of the data
    (preregistration: tests up to 2026-08-17)."""
    folds, train_end = [], data_start + pd.DateOffset(months=TRAIN_MONTHS)
    end_excl = data_end + pd.Timedelta(minutes=1)
    while train_end < end_excl:
        test_end = min(train_end + pd.DateOffset(months=TEST_MONTHS), end_excl)
        folds.append((data_start, train_end, test_end))
        train_end = train_end + pd.DateOffset(months=STEP_MONTHS)
    return folds


def run_fold(train: dict, test: dict, n_jobs: int = 4) -> dict:
    """train = {sym: (feats float32 [n, 24], close float64 [n])} for BTC, ETH (TRAIN rows only);
    test = {sym: (feats float32 [m, 24], times int64 [m])} for SOL, BTC, ETH (TEST rows only).
    Returns thresholds, cutoffs and the TEST signal times per variant and symbol."""
    X = Pooled([train[s][0] for s in TRAIN_SYMS])
    rng_j, vol_j = FEATURES.index("range_pos_60"), FEATURES.index("realized_vol_30")
    tr_rng = {s: np.asarray(train[s][0][:, rng_j]) for s in TRAIN_SYMS}
    tr_vol = {s: np.asarray(train[s][0][:, vol_j]) for s in TRAIN_SYMS}
    info, models, thr, cuts = {}, {}, {}, {}
    for name, h in (("REF", H_REF), ("L50", H_L50)):
        y = np.concatenate([train_labels(train[s][1], h) for s in TRAIN_SYMS])
        kept = prune_redundant_lowmem(X, y, FEATURES)
        model = fit_model(X, y, FEATURES, kept, n_jobs)
        del y
        p = {s: predict(model, train[s][0], FEATURES) for s in TRAIN_SYMS}
        models[name] = (model, p)
        info[f"{name}_kept"] = kept
    tr_ref = {s: (models["REF"][1][s], tr_rng[s], tr_vol[s]) for s in TRAIN_SYMS}
    tr_l50 = {s: (models["L50"][1][s], tr_rng[s], tr_vol[s]) for s in TRAIN_SYMS}
    target = train_signal_count(tr_ref, THRESHOLD_REF)
    t_l50, c_l50 = calibrate_threshold(tr_l50, target)
    info.update(train_signals_REF=target, train_signals_L50=c_l50, thr_L50=t_l50,
                train_signals_L50_070=train_signal_count(tr_l50, THRESHOLD_REF),
                train_rows={s: len(train[s][1]) for s in TRAIN_SYMS})
    for var, mname, t in (("REF", "REF", THRESHOLD_REF), ("L50", "L50", t_l50), ("L50_070", "L50", THRESHOLD_REF)):
        p = models[mname][1]
        per = {s: cutoffs(p[s], tr_rng[s], tr_vol[s], t) for s in TRAIN_SYMS}
        pooled = cutoffs(np.concatenate([p[s] for s in TRAIN_SYMS]), np.concatenate([tr_rng[s] for s in TRAIN_SYMS]),
                         np.concatenate([tr_vol[s] for s in TRAIN_SYMS]), t)
        thr[var] = t
        cuts[var] = {"BTCUSDT": per["BTCUSDT"], "ETHUSDT": per["ETHUSDT"], "SOLUSDT": pooled}
    signals = {v: {} for v in VARIANTS}
    test_counts = {}
    for s in ALL_SYMS:
        f, times = test[s]
        pt = {m: predict(models[m][0], f, FEATURES) for m in ("REF", "L50")}
        rng, vol = np.asarray(f[:, rng_j]), np.asarray(f[:, vol_j])
        for var, mname in (("REF", "REF"), ("L50", "L50"), ("L50_070", "L50")):
            m = signal_mask(pt[mname], rng, vol, thr[var], cuts[var][s])
            signals[var][s] = np.asarray(times)[m]
            test_counts[f"{var}_{s}"] = int(m.sum())
    del models, X
    gc.collect()
    info.update(thresholds=thr, cutoffs=cuts, test_signal_bars=test_counts)
    return {"info": info, "signals": signals}


def stage_folds(work: Path, n_jobs: int, max_folds: int | None, min_free_mb: float) -> None:
    mm = {s: np.load(work / f"feats_{s}.npy", mmap_mode="r") for s in ALL_SYMS}
    times = {s: np.load(work / f"times_{s}.npy") for s in ALL_SYMS}
    close = {s: np.load(work / f"close_{s}.npy", mmap_mode="r") for s in TRAIN_SYMS}
    ts = {s: pd.DatetimeIndex(times[s]).tz_localize("UTC") for s in ALL_SYMS}
    data_start = max(ts[s][0] for s in TRAIN_SYMS)
    data_end = min(ts[s][-1] for s in TRAIN_SYMS)
    folds = fold_grid(data_start, data_end)
    (work / "folds.json").write_text(json.dumps([[str(a), str(b), str(c)] for a, b, c in folds], indent=1))
    log(f"{len(folds)} folds, data {data_start} -> {data_end}")
    done = 0
    for k, (t0, train_end, test_end) in enumerate(folds, 1):
        out = work / f"fold_{k:02d}.pkl"
        if out.exists():
            continue
        if max_folds is not None and done >= max_folds:
            break
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
            te[s] = (mm[s][a:b], times[s][a:b])
        res = run_fold(tr, te, n_jobs)
        res["fold"] = {"k": k, "train_start": str(t0), "train_end": str(train_end), "test_end": str(test_end)}
        with open(work / f"tmp_fold_{k:02d}.pkl", "wb") as fh:
            pickle.dump(res, fh)
        os.replace(work / f"tmp_fold_{k:02d}.pkl", out)
        i = res["info"]
        log(f"fold {k} done: thr_L50={i['thr_L50']:.4f} train signals REF={i['train_signals_REF']} "
            f"L50={i['train_signals_L50']} | test {i['test_signal_bars']}")
        del tr, te, res
        gc.collect()
        done += 1


# ----------------------------------------------------------------------------- harness (stage 3)

def stage_harness(work: Path, cache_dir: Path, out_dir: Path, date: str) -> dict:
    from quant_bot.execution_harness import (VERSION, USD_PER_CAD, ExitRule, apply_costs, load_bars,
                                             profit_factor, run_trades, simulate_account)
    folds = json.loads((work / "folds.json").read_text())
    res = []
    for k in range(1, len(folds) + 1):
        with open(work / f"fold_{k:02d}.pkl", "rb") as fh:
            res.append(pickle.load(fh))
    test_start = pd.Timestamp(folds[0][1])
    data_end_excl = pd.Timestamp(folds[-1][2])
    periods = {"P1": (test_start, P2_START), "P2": (P2_START, data_end_excl)}
    notional = INITIAL_CAD * USD_PER_CAD.value * FRACTION
    rule = ExitRule(max_bars=HOLD_BARS)
    loader = lambda s: load_bars(s, cache_dir)  # noqa: E731
    per_trade, accounts, status_rows = [], [], []
    sims = {}
    for var in VARIANTS:
        cands = []
        for s in ALL_SYMS:
            times = np.load(work / f"times_{s}.npy")
            sig = np.unique(np.concatenate([r["signals"][var][s] for r in res]))
            idx = np.searchsorted(times, sig)
            assert (times[idx] == sig).all()
            seq = sequence(idx)
            cands.append(pd.DataFrame({"symbol": s, "signal_time": pd.DatetimeIndex(times[seq]).tz_localize("UTC"),
                                       "side": 1, "raw_signal_bars": len(sig)}))
        cand = pd.concat(cands, ignore_index=True)
        sim = run_trades(cand[["symbol", "signal_time", "side"]], rule, "jupiter_build", loader,
                         entry_mode="next_open", notional_usd=notional)
        sim["period"] = np.where(sim.signal_time < P2_START, "P1", "P2")
        sims[var] = sim
        status_rows.append(sim.groupby(["period", "symbol", "status"]).size().rename("n").reset_index()
                           .assign(variant=var))
        log(f"harness {var}: {len(sim)} sequenced candidates")
        for cost_name, plat in COSTS.items():
            t = apply_costs(sim, plat, notional_usd=notional)
            for pop, (p0, p1) in periods.items():
                ok = t[(t.status == "ok") & (t.period == pop)]
                for sym in list(ALL_SYMS) + ["POOLED"]:
                    x = ok if sym == "POOLED" else ok[ok.symbol == sym]
                    r = x.net_ret_at_size
                    per_trade.append({"variant": var, "period": pop, "cost": cost_name, "symbol": sym, "n": len(x),
                                      "mean_gross_pct": 100 * x.gross_ret.mean(),
                                      "mean_net_pct_at_size": 100 * r.mean(),
                                      "pf_at_size": profit_factor(r),
                                      "win_rate": float((r > 0).mean()) if len(x) else np.nan,
                                      "t_stat": float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if len(r) > 1 else np.nan,
                                      "trades_per_day": len(x) / ((p1 - p0).total_seconds() / 86400)})
                tt = t.copy()
                tt.loc[(tt.period != pop) & (tt.status == "ok"), "status"] = "other_period"
                a = simulate_account(tt, plat, INITIAL_CAD, USD_PER_CAD.value, position_fraction=FRACTION,
                                     max_gross_exposure=1.0, one_position_per_symbol=True, period=(p0, p1))
                accounts.append({"variant": var, "period": pop, "cost": cost_name, "platform": plat,
                                 "period_start": str(p0), "period_end": str(p1),
                                 **{k: v for k, v in a.items() if k not in ("ledger", "equity_minute", "skips")},
                                 **{f"skip_{k}": v for k, v in a.get("skips", {}).items()}})
    pt, ac, st = pd.DataFrame(per_trade), pd.DataFrame(accounts), pd.concat(status_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    pt.to_csv(out_dir / f"Exp-53_{date}_per_trade.csv", index=False)
    ac.to_csv(out_dir / f"Exp-53_{date}_accounts.csv", index=False)
    st.to_csv(out_dir / f"Exp-53_{date}_status.csv", index=False)
    folds_rows = []
    for r in res:
        i = r["info"]
        folds_rows.append({**r["fold"], "thr_REF": i["thresholds"]["REF"], "thr_L50": i["thr_L50"],
                           "train_signals_REF": i["train_signals_REF"], "train_signals_L50": i["train_signals_L50"],
                           "train_signals_L50_070": i["train_signals_L50_070"],
                           "kept_REF": "|".join(i["REF_kept"]), "kept_L50": "|".join(i["L50_kept"]),
                           **{f"test_bars_{k}": v for k, v in i["test_signal_bars"].items()},
                           **{f"cut_{v}_{s[:3]}": (None if c is None else f"{c[0]:.5f}/{c[1]:.6f}")
                              for v, d in i["cutoffs"].items() for s, c in d.items()}})
    pd.DataFrame(folds_rows).to_csv(out_dir / f"Exp-53_{date}_folds.csv", index=False)

    crit = {}
    for pop in periods:
        p = pt[(pt.period == pop) & (pt.cost == "principal_build")].set_index(["variant", "symbol"])["mean_net_pct_at_size"]
        d_sym = {s: float(p[("L50", s)] - p[("REF", s)]) for s in ALL_SYMS}
        crit[pop] = {"REF_net_pct": float(p[("REF", "POOLED")]), "L50_net_pct": float(p[("L50", "POOLED")]),
                     "delta_pct_points": float(p[("L50", "POOLED")] - p[("REF", "POOLED")]),
                     "delta_by_symbol": d_sym, "n_symbols_delta_pos": int(sum(v > 0 for v in d_sym.values()))}
    pass_ = all(c["delta_pct_points"] >= 0.03 and c["L50_net_pct"] > 0 and c["n_symbols_delta_pos"] >= 2
                for c in crit.values())
    reject = any(c["delta_pct_points"] <= 0 for c in crit.values())
    mech = "PASS" if pass_ else ("REJET" if reject else "INCERTAIN")
    out = {"harness_version": VERSION, "notional_usd_at_33pct": notional, "usd_per_cad": USD_PER_CAD.value,
           "p2_start": str(P2_START), "periods": {k: [str(a), str(b)] for k, (a, b) in periods.items()},
           "criteria": crit, "mechanical_reading": mech}
    (out_dir / f"Exp-53_{date}_criteria.json").write_text(json.dumps(out, indent=2))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(pt.round(4).to_string())
    print(ac[["variant", "period", "cost", "n_trades", "total_return_cad_pct", "cagr_cad_pct", "max_dd_pct",
              "worst_day_pct", "worst_day_date", "pf_usd", "skip_symbol_busy", "skip_exposure_cap"]].round(3).to_string())
    print(json.dumps(out, indent=2))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["features", "folds", "harness", "all"], default="all")
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE), help="bars cache (read only)")
    ap.add_argument("--work-dir", default=str(ROOT / "outputs" / "exp53"))
    ap.add_argument("--out-dir", default=str(ROOT / "docs" / "agents" / "results"))
    ap.add_argument("--date", default="2026-10-07")
    ap.add_argument("--n-jobs", type=int, default=4)
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--min-free-mb", type=float, default=1200)
    a = ap.parse_args(argv)
    if a.n_jobs > 4:
        raise SystemExit("n_jobs capped at 4 (memory rule)")
    work, cache = Path(a.work_dir), Path(a.cache_dir)
    work.mkdir(parents=True, exist_ok=True)
    if a.stage in ("features", "all"):
        for s in ALL_SYMS:
            build_symbol_arrays(s, cache, work)
    if a.stage in ("folds", "all"):
        stage_folds(work, a.n_jobs, a.max_folds, a.min_free_mb)
    if a.stage in ("harness", "all"):
        stage_harness(work, cache, Path(a.out_dir), a.date)


if __name__ == "__main__":
    main()
