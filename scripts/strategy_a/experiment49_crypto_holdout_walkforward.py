"""Experiment 49 — crypto 9-symbol walk-forward with retraining on the HOLDOUT
window (preregistered in docs/research_plan_status.md before any result).

Replicates the frozen baseline population's per-symbol procedures, importing
the original helpers unchanged:
  - BTC/ETH: joint BTC+ETH model, per-symbol cutoffs + p90 stop
    (scripts/walk_forward_v3_trade_export.py export_fold_symbol logic,
    slow trade builder from scripts/mae_mfe_analysis.py);
  - SOL: same joint model, POOLED BTC+ETH cutoffs/stop applied unchanged
    (scripts/multi_crypto_transfer_walkforward.py process_fold logic);
  - ADA/BNB/DOGE/LTC p90, XRP p80, LINK p95: own model
    (scripts/multi_crypto_walkforward.py process_fold logic).
Only folds whose TRAIN end is >= the mode's HOLDOUT start and whose TEST end
is <= the cached data end are run. TRAIN features: computed once on the full
series (float32) and sliced (identical to the TRAIN-prefix computation since
TRAIN starts at the data start and every feature is causal; sklearn trees use
float32 internally). TEST features: recomputed on each TEST slice alone.

Resource limits (user: stay under 60 %): random forests use 6 jobs; one mode
group at a time; refuses the joint BTC+ETH group with < 2.5 GB free RAM.

Usage: python scripts/strategy_a/experiment49_crypto_holdout_walkforward.py [--only SYM ...]
"""
import argparse
import gc
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from quant_bot.config import COST_THRESHOLD_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT  # noqa: E402
from quant_bot.features.build import build_feature_matrix, build_labels  # noqa: E402
from quant_bot.features.pipeline import prune_redundant  # noqa: E402
from quant_bot.signal.model import Tier2RandomForestSignal  # noqa: E402
from scripts.diagnostic_leverage import STOP_OUT_FRACTION  # noqa: E402
from scripts.fast_trades import build_trades_with_mae_mfe_fast  # noqa: E402
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe as build_trades_slow  # noqa: E402
from scripts.multi_crypto_walkforward import _load_full_cached, decide_fold_params  # noqa: E402

HORIZON, THRESHOLD, ACTIVATE_AT, TRAIL_DIST = 10, 0.70, 0.0063, 0.0080
SAFETY_MARGIN, MAX_LEVERAGE_CAP = 0.75, 30.0
COST_RT = (TAKER_FEE_PCT + SLIPPAGE_PCT_EST / 2.0) * 2
JOINT_HOLDOUT_START = pd.Timestamp("2025-03-28", tz="UTC")
OWN = {"ADAUSDT": 90, "BNBUSDT": 90, "DOGEUSDT": 90, "LTCUSDT": 90, "XRPUSDT": 80, "LINKUSDT": 95}
OUT = ROOT / "outputs" / "experiment49"


def capped(signal_model):
    """Half the cores (user: stay under 60 %); RF output does not depend on n_jobs."""
    signal_model.model.n_jobs = 6
    return signal_model


def free_mb() -> float:
    """Available physical memory in MB (Windows GlobalMemoryStatusEx; no psutil)."""
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return stat.ullAvailPhys / 2**20


def features32(df: pd.DataFrame) -> pd.DataFrame:
    return build_feature_matrix(df).astype("float32")


def grid(data_start, train_months, test_months, step_months, holdout_start, data_end):
    folds, train_end = [], data_start + pd.DateOffset(months=train_months)
    while True:
        test_end = train_end + pd.DateOffset(months=test_months)
        if test_end > data_end:
            return folds
        if train_end >= holdout_start:
            folds.append((data_start, train_end, test_end))
        train_end = train_end + pd.DateOffset(months=step_months)


def stop_and_leverage(close, filtered, feats, stop_pct, builder, **kw):
    trades = builder(close, filtered, feats["ema_slope_20"].to_numpy(), feats["ret_1"].to_numpy(), **kw)
    if len(trades) < 10:
        return None
    stop = float(np.percentile(np.abs([t["mae"] for t in trades]), stop_pct))
    lev = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop, MAX_LEVERAGE_CAP)
    return stop, lev, min(stop, STOP_OUT_FRACTION / lev)


def score_test(symbol, fold_i, model, test_df, rcut, vcut, stop, lev, protective, builder, **kw):
    tf = build_feature_matrix(test_df)
    p = model.predict_proba(tf)
    filt = ((p > THRESHOLD) & (tf["range_pos_60"] < rcut) & (tf["realized_vol_30"] > vcut)).to_numpy()
    seq = builder(test_df["close"].to_numpy(), filt, tf["ema_slope_20"].to_numpy(), tf["ret_1"].to_numpy(), **kw)
    rows = []
    for t in seq:
        i, path = t["entry_idx"], t["close_path"]
        peak, active, stopped, ret, off = -np.inf, False, False, None, len(path) - 1
        for j, x in enumerate(path):
            if x <= -protective:
                ret, stopped, off = -protective, True, j
                break
            peak = max(peak, x)
            active = active or peak >= ACTIVATE_AT
            if active and x <= peak - TRAIL_DIST:
                ret, off = peak - TRAIL_DIST, j
                break
        if ret is None:
            ret = path[-1]
        rows.append({"symbol": symbol, "fold": fold_i, "entry_time": test_df.index[i],
                     "exit_time": test_df.index[min(i + off, len(test_df) - 1)], "raw_return": ret,
                     "stop_distance": stop, "leverage_safe": lev, "was_stopped": stopped})
    return rows


def fold_summary(rows, symbol, fold_i, train_end, test_end):
    if not rows:
        return {"symbol": symbol, "fold": fold_i, "train_end": train_end, "test_end": test_end, "n_trades": 0}
    net = np.array([r["raw_return"] for r in rows]) - COST_RT
    lev = rows[0]["leverage_safe"]
    pnl = net * lev
    pf = pnl[pnl > 0].sum() / -pnl[pnl <= 0].sum() if (pnl <= 0).any() and pnl[pnl <= 0].sum() < 0 else np.inf
    return {"symbol": symbol, "fold": fold_i, "train_end": train_end, "test_end": test_end,
            "n_trades": len(rows), "pf_exec": pf, "mean_net_pct": 100 * net.mean(), "win_pct": 100 * (net > 0).mean()}


def run_own(symbol, stop_pct):
    full = _load_full_cached(symbol)
    n = len(full)
    data_start, data_end = full.index[0], full.index[-1]
    holdout_start = full.index[int(n * 0.8)]
    init, test_m, step_m, _ = decide_fold_params(data_start, holdout_start)
    folds = grid(data_start, init, test_m, step_m, holdout_start, data_end)
    print(f"[{symbol}] own p{stop_pct}: HOLDOUT_START {holdout_start:%Y-%m-%d}, {len(folds)} folds", flush=True)
    feats = features32(full)
    summaries, trades = [], []
    for k, (t0, train_end, test_end) in enumerate(folds, 1):
        mask = (full.index >= t0) & (full.index < train_end)
        tr_df, tr_f = full[mask], feats[mask]
        y = build_labels(tr_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
        kept, _ = prune_redundant(tr_f, y, corr_threshold=0.9)
        idx = tr_f.sample(n=min(250_000, len(tr_f)), random_state=42).index
        model = capped(Tier2RandomForestSignal(kept, n_estimators=100)).fit(tr_f.loc[idx], y.loc[idx])
        p = model.predict_proba(tr_f)
        sel = p > THRESHOLD
        rows = []
        if sel.sum() >= 20:
            rcut, vcut = tr_f.loc[sel, "range_pos_60"].median(), tr_f.loc[sel, "realized_vol_30"].median()
            filt = (sel & (tr_f["range_pos_60"] < rcut) & (tr_f["realized_vol_30"] > vcut)).to_numpy()
            slv = stop_and_leverage(tr_df["close"].to_numpy(), filt, tr_f, stop_pct, build_trades_with_mae_mfe_fast, horizon=HORIZON)
            if slv:
                test_df = full[(full.index >= train_end) & (full.index < test_end)]
                rows = score_test(symbol, k, model, test_df, rcut, vcut, *slv, build_trades_with_mae_mfe_fast, horizon=HORIZON)
        s = fold_summary(rows, symbol, k, train_end, test_end)
        print(f"  fold {k}: TEST {train_end:%Y-%m-%d}->{test_end:%Y-%m-%d} n={s['n_trades']} PF={s.get('pf_exec', float('nan')):.3f}", flush=True)
        summaries.append(s)
        trades += rows
        del tr_f, tr_df, model, p
        gc.collect()
    del feats
    gc.collect()
    return summaries, trades


def run_joint():
    btc, eth, sol = (_load_full_cached(s) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT"))
    data_start = max(btc.index[0], eth.index[0])
    data_end = min(btc.index[-1], eth.index[-1])
    folds = grid(data_start, 24, 3, 3, JOINT_HOLDOUT_START, data_end)
    print(f"[BTC/ETH/SOL] joint: {len(folds)} folds", flush=True)
    fb = features32(btc[btc.index >= data_start])
    fe = features32(eth[eth.index >= data_start])
    btc, eth = btc[btc.index >= data_start], eth[eth.index >= data_start]
    summaries, trades = [], []
    for k, (t0, train_end, test_end) in enumerate(folds, 1):
        trb, tre = btc[btc.index < train_end], eth[eth.index < train_end]
        Fb, Fe = fb[fb.index < train_end], fe[fe.index < train_end]
        X = pd.concat([Fb, Fe], ignore_index=True)
        y = pd.concat([build_labels(trb["close"], HORIZON, COST_THRESHOLD_PCT, direction="long"),
                       build_labels(tre["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")], ignore_index=True)
        kept, _ = prune_redundant(X, y, corr_threshold=0.9)
        idx = X.sample(n=min(250_000, len(X)), random_state=42).index
        model = capped(Tier2RandomForestSignal(kept, n_estimators=100)).fit(X.loc[idx], y.loc[idx])
        pooled_p = model.predict_proba(X)
        # BTC / ETH: per-symbol cutoffs and stop (v3 export logic, slow trade builder)
        for sym, tr_df, F, full in (("BTCUSDT", trb, Fb, btc), ("ETHUSDT", tre, Fe, eth)):
            p = model.predict_proba(F)
            sel = p > THRESHOLD
            rows = []
            if sel.sum() >= 20:
                rcut, vcut = F.loc[sel, "range_pos_60"].median(), F.loc[sel, "realized_vol_30"].median()
                filt = (sel & (F["range_pos_60"] < rcut) & (F["realized_vol_30"] > vcut)).to_numpy()
                slv = stop_and_leverage(tr_df["close"].to_numpy(), filt, F, 90, build_trades_slow)
                if slv:
                    test_df = full[(full.index >= train_end) & (full.index < test_end)]
                    rows = score_test(sym, k, model, test_df, rcut, vcut, *slv, build_trades_slow)
            s = fold_summary(rows, sym, k, train_end, test_end)
            print(f"  {sym} fold {k}: n={s['n_trades']} PF={s.get('pf_exec', float('nan')):.3f}", flush=True)
            summaries.append(s)
            trades += rows
        # SOL: pooled BTC+ETH cutoffs and stop, applied unchanged (transfer logic, fast builder)
        sel = pooled_p > THRESHOLD
        rows = []
        if sel.sum() >= 20:
            rcut, vcut = X.loc[sel, "range_pos_60"].median(), X.loc[sel, "realized_vol_30"].median()
            filt = (sel & (X["range_pos_60"] < rcut) & (X["realized_vol_30"] > vcut)).to_numpy()
            pooled_close = np.concatenate([trb["close"].to_numpy(), tre["close"].to_numpy()])
            slv = stop_and_leverage(pooled_close, filt, X, 90, build_trades_with_mae_mfe_fast, horizon=HORIZON)
            if slv:
                test_df = sol[(sol.index >= train_end) & (sol.index < test_end)]
                rows = score_test("SOLUSDT", k, model, test_df, rcut, vcut, *slv, build_trades_with_mae_mfe_fast, horizon=HORIZON)
        s = fold_summary(rows, "SOLUSDT", k, train_end, test_end)
        print(f"  SOLUSDT fold {k}: n={s['n_trades']} PF={s.get('pf_exec', float('nan')):.3f}", flush=True)
        summaries.append(s)
        trades += rows
        del X, y, model, pooled_p
        gc.collect()
    return summaries, trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    todo = a.only or list(OWN) + ["JOINT"]
    for job in todo:
        done = OUT / f"{job}_done.txt"
        if done.exists():
            print(f"{job}: already done", flush=True)
            continue
        if job == "JOINT":
            if free_mb() < 2500:
                print(f"JOINT skipped: only {free_mb():.0f} MB free RAM (< 2500). Close apps and rerun with --only JOINT.", flush=True)
                continue
            summaries, trades = run_joint()
        else:
            summaries, trades = run_own(job, OWN[job])
        pd.DataFrame(summaries).to_csv(OUT / f"{job}_summary.csv", index=False)
        pd.DataFrame(trades).to_csv(OUT / f"{job}_trades.csv", index=False)
        done.write_text("done")


if __name__ == "__main__":
    main()
