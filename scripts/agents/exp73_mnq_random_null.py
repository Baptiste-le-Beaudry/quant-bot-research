"""Exp 73 -- MNQ noise-area (Exp 65) against random entries (null A: random direction; null B:
random entry time + direction + duration).

Preregistration: docs/agents/hypotheses/Exp-73.md (commit 2617cc1, frozen). Diagnostic only: the
index HOLDOUT was consumed by Exp 65; the rule is NOT re-run, the real trades are read from the
Exp 65 / Exp 64 trade CSVs.

Conventions (identical to scripts/agents/exp64_noise_momentum.py): bar 0 = 09:30 ET, execution at
the bar open, a decision at HH:MM (bar index 29 + 30k) executes at the open of bar 30 + 30k (first
available bar at or after it, else the 15:59 bar), exit-of-day at the open of bar 389 (15:59),
multiplier 2 USD/pt, cost 2.22 USD round trip per trade.

Statistic: total net PnL in USD over the window (days without trades count 0).
p = (1 + #draws with net >= real net) / (1 + n_draws).

Each (window, null) pair uses a fresh numpy Generator seeded with SEED; draws are produced in
chunks of CHUNK draws (null A is chunk-size invariant; null B depends on CHUNK, fixed at 500).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_spec = importlib.util.spec_from_file_location("exp64", Path(__file__).with_name("exp64_noise_momentum.py"))
e64 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e64)

SEED = 20261011
N_DRAWS = 10_000
MULT = 2.0
COST_RT = 2.22
EXIT_IDX = e64.EXIT_IDX                                    # 389
ENTRY_BARS = np.array([di + 1 for di in e64.DECISION_IDX])  # 30, 60, ..., 360
H_START = dt.date(2024, 3, 5)
H_POST_START = dt.date(2024, 11, 27)
P1_END = dt.date(2024, 10, 31)
PREREG_BEST_DAY = dt.date(2025, 4, 9)
QUANTILES = (0.50, 0.95, 0.99)
CHUNK = 500


# --------------------------------------------------------------------------- inputs
def load_trades(path, start: dt.date | None = None, end: dt.date | None = None) -> pd.DataFrame:
    """MNQ noise-area trades of an Exp 64/65 trade CSV, restricted to [start, end]."""
    t = pd.read_csv(path)
    t = t[t["future"] == "MNQ"]
    if "variant" in t.columns:
        t = t[t["variant"] == "noise_area"]
    t = t.copy()
    t["date"] = pd.to_datetime(t["date"]).dt.date
    if start is not None:
        t = t[t["date"] >= start]
    if end is not None:
        t = t[t["date"] <= end]
    t = t.sort_values(["date", "entry_bar"]).reset_index(drop=True)
    t["side"] = t["side"].astype(int)
    t["entry_bar"] = t["entry_bar"].astype(int)
    t["exit_bar"] = t["exit_bar"].astype(int)
    return t


def recompute_net(t: pd.DataFrame) -> np.ndarray:
    return t["side"].to_numpy() * (t["exit_px"].to_numpy() - t["entry_px"].to_numpy()) * MULT - COST_RT


# --------------------------------------------------------------------------- price tables
def exec_tables(open_grid: np.ndarray):
    """fwd_px[i, b] / fwd_idx[i, b] = price/bar actually filled for an order at the open of bar b,
    with exp64._exec_price semantics: first available bar in [b, 389), else bar 389."""
    n, m = open_grid.shape
    idx = np.where(~np.isnan(open_grid[:, :EXIT_IDX]), np.arange(EXIT_IDX), EXIT_IDX)
    # backward "next available" : reverse cumulative minimum
    idx = np.minimum.accumulate(idx[:, ::-1], axis=1)[:, ::-1]
    idx = np.concatenate([idx, np.full((n, m - EXIT_IDX), EXIT_IDX)], axis=1)
    idx[:, EXIT_IDX:] = np.arange(EXIT_IDX, m)
    px = open_grid[np.arange(n)[:, None], idx]
    return px, idx


def day_rows(dates_grid, trade_dates) -> np.ndarray:
    pos = {d: i for i, d in enumerate(dates_grid)}
    missing = sorted({d for d in trade_dates if d not in pos})
    if missing:
        raise ValueError(f"trade days absent from the bar grid: {missing[:5]}")
    return np.array([pos[d] for d in trade_dates], dtype=int)


def reprice_check(t: pd.DataFrame, open_grid: np.ndarray, rows: np.ndarray, tol: float = 1e-4) -> dict:
    """Do the bars give back the real trades' entry/exit prices at their recorded bars?"""
    e = open_grid[rows, t["entry_bar"].to_numpy()]
    x = open_grid[rows, t["exit_bar"].to_numpy()]
    de = np.abs(e - t["entry_px"].to_numpy())
    dx = np.abs(x - t["exit_px"].to_numpy())
    bad = ~((de <= tol) & (dx <= tol))
    return {"n_trades": int(len(t)), "n_mismatch": int(np.nansum(bad) + 0),
            "max_abs_diff_entry": float(np.nanmax(de)) if len(t) else 0.0,
            "max_abs_diff_exit": float(np.nanmax(dx)) if len(t) else 0.0,
            "n_nan": int(np.isnan(e).sum() + np.isnan(x).sum())}


# --------------------------------------------------------------------------- nulls
def _draw_sides(rng, q, shape):
    return np.where(rng.random(shape) < q, 1.0, -1.0)


def null_a(moves: np.ndarray, q: float, masks: dict, n_draws: int = N_DRAWS, seed: int = SEED) -> dict:
    """moves = exit_px - entry_px per real trade. Returns {name: totals over draws} where each mask
    selects the trades kept (True = kept)."""
    rng = np.random.default_rng(seed)
    out = {k: np.empty(n_draws) for k in masks}
    done = 0
    while done < n_draws:
        b = min(CHUNK, n_draws - done)
        s = _draw_sides(rng, q, (b, len(moves)))
        pnl = s * moves * MULT - COST_RT
        for k, mk in masks.items():
            out[k][done:done + b] = pnl[:, mk].sum(axis=1)
        done += b
    return out


def null_b(rows: np.ndarray, durations: np.ndarray, q: float, fwd_px: np.ndarray, fwd_idx: np.ndarray,
           masks: dict, n_draws: int = N_DRAWS, seed: int = SEED, entry_bars: np.ndarray = ENTRY_BARS) -> dict:
    """One simulated trade per real trade, on the same day (per-day counts kept): entry bar uniform
    over the rule's execution bars, side ~ Bernoulli(q), duration drawn from the real durations,
    exit at the open of min(entry + duration, 389)."""
    rng = np.random.default_rng(seed)
    n = len(rows)
    out = {k: np.empty(n_draws) for k in masks}
    done = 0
    while done < n_draws:
        b = min(CHUNK, n_draws - done)
        eb = entry_bars[rng.integers(0, len(entry_bars), size=(b, n))]
        s = _draw_sides(rng, q, (b, n))
        dur = durations[rng.integers(0, len(durations), size=(b, n))]
        r = np.broadcast_to(rows, (b, n))
        ej = fwd_idx[r, eb]
        epx = fwd_px[r, eb]
        xb = np.minimum(ej + dur, EXIT_IDX)
        xpx = fwd_px[r, xb]
        pnl = s * (xpx - epx) * MULT - COST_RT
        for k, mk in masks.items():
            out[k][done:done + b] = pnl[:, mk].sum(axis=1)
        done += b
    return out


def p_value(sims: np.ndarray, real: float) -> float:
    return float((1 + np.sum(sims >= real - 1e-9)) / (1 + len(sims)))


def summarize(sims: np.ndarray, real: float) -> dict:
    return {"real_net_usd": float(real), "p": p_value(sims, real), "n_draws": int(len(sims)),
            "null_mean": float(sims.mean()), "null_std": float(sims.std(ddof=1)),
            "quantiles": {f"q{int(round(100 * a))}": float(np.quantile(sims, a)) for a in QUANTILES},
            "n_ge_real": int(np.sum(sims >= real - 1e-9))}


def exclusion_masks(t: pd.DataFrame, net: np.ndarray) -> tuple[dict, dict]:
    daily = pd.Series(net).groupby(t["date"].to_numpy()).sum().sort_values(ascending=False)
    best1 = list(daily.index[:1])
    best5 = list(daily.index[:5])
    d = t["date"].to_numpy()
    masks = {"all": np.ones(len(t), bool),
             "without_best_day": ~np.isin(d, best1),
             "without_5_best_days": ~np.isin(d, best5)}
    info = {"best_day": [str(x) for x in best1], "best_day_net_usd": float(daily.iloc[0]) if len(daily) else None,
            "best_5_days": [str(x) for x in best5],
            "best_5_days_net_usd": [float(daily[x]) for x in best5],
            "prereg_best_day_2025_04_09_is_best": bool(best1 and best1[0] == PREREG_BEST_DAY)}
    return masks, info


def run_window(t: pd.DataFrame, open_grid: np.ndarray, dates_grid: list, fwd_px, fwd_idx,
               n_draws: int = N_DRAWS, seed: int = SEED) -> dict:
    net = recompute_net(t)
    rows = day_rows(dates_grid, list(t["date"]))
    if not np.isfinite(fwd_px[np.unique(rows)][:, ENTRY_BARS.min():]).all():
        raise ValueError("missing executable price on a trade day (null B would be NaN)")
    q =float((t["side"] == 1).mean())
    durations = (t["exit_bar"] - t["entry_bar"]).to_numpy()
    masks, exinfo = exclusion_masks(t, net)
    moves = (t["exit_px"] - t["entry_px"]).to_numpy()
    sa = null_a(moves, q, masks, n_draws, seed)
    sb = null_b(rows, durations, q, fwd_px, fwd_idx, masks, n_draws, seed)
    res = {"first_day": str(t["date"].min()), "last_day": str(t["date"].max()),
           "n_trades": int(len(t)), "n_days_traded": int(t["date"].nunique()), "q_long": q,
           "duration_bars": {"min": int(durations.min()), "median": float(np.median(durations)),
                             "max": int(durations.max())},
           "real_net_recomputed_usd": float(net.sum()), "real_net_csv_usd": float(t["net_usd"].sum()),
           "reprice_check": reprice_check(t, open_grid, rows), "excluded_days": exinfo,
           "null_A": {}, "null_B": {}}
    for k, mk in masks.items():
        real = float(net[mk].sum())
        res["null_A"][k] = summarize(sa[k], real)
        res["null_B"][k] = summarize(sb[k], real)
    return res


def verdict73(p_a_h: float, p_b_h: float, p_a_hpost: float) -> dict:
    rule = ("SIGNAL: p_A <= 0.05 and p_B <= 0.05 on H, and p_A <= 0.10 on H-post; "
            "HASARD: p_A > 0.20 on H; else INCERTAIN")
    if p_a_h <= 0.05 and p_b_h <= 0.05 and p_a_hpost <= 0.10:
        v = "SIGNAL"
    elif p_a_h > 0.20:
        v = "HASARD"
    else:
        v = "INCERTAIN"
    return {"rule": rule, "p_A_H": p_a_h, "p_B_H": p_b_h, "p_A_Hpost": p_a_hpost, "verdict": v}


# --------------------------------------------------------------------------- driver
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", required=True, help="NASDAQ100_1m.csv (read only)")
    ap.add_argument("--holdout-decision", required=True,
                    help="written decision already unlocking the index HOLDOUT (Exp 65)")
    ap.add_argument("--trades65", required=True)
    ap.add_argument("--trades64", default=None)
    ap.add_argument("--out", required=True, help="criteria JSON path")
    ap.add_argument("--n-draws", type=int, default=N_DRAWS)
    a = ap.parse_args(argv)

    df = e64.load_pre_holdout(a.bars, a.holdout_decision)
    last_bar = str(df.index.max())
    grid = e64.build_grid(df)
    del df
    o = grid["open"]
    fwd_px, fwd_idx = exec_tables(o)
    dates = grid["dates"]

    windows = {"H": load_trades(a.trades65, H_START), "H_post": load_trades(a.trades65, H_POST_START)}
    if a.trades64 and Path(a.trades64).is_file():
        windows["P1"] = load_trades(a.trades64, None, P1_END)
    crit = {"prereg": "docs/agents/hypotheses/Exp-73.md", "script": "scripts/agents/exp73_mnq_random_null.py",
            "seed": SEED, "n_draws": a.n_draws, "mult": MULT, "cost_rt_usd": COST_RT,
            "fill": "open of the bar after the HH:00/HH:30 decision (exp64._exec_price), exit at bar open",
            "entry_bars_null_B": ENTRY_BARS.tolist(), "bars_file": a.bars, "last_bar_loaded_et": last_bar,
            "holdout_decision": a.holdout_decision, "windows": {}}
    for name, t in windows.items():
        res = run_window(t, o, dates, fwd_px, fwd_idx, a.n_draws, SEED)
        crit["windows"][name] = res
        print(name, json.dumps({k: res[k] for k in ("n_trades", "q_long", "real_net_recomputed_usd",
                                                    "real_net_csv_usd", "reprice_check")}),
              "pA", res["null_A"]["all"]["p"], "pB", res["null_B"]["all"]["p"], flush=True)
    w = crit["windows"]
    crit["verdict"] = verdict73(w["H"]["null_A"]["all"]["p"], w["H"]["null_B"]["all"]["p"],
                                w["H_post"]["null_A"]["all"]["p"])
    crit["variants_counted"] = 1
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(crit, f, indent=2, default=str, ensure_ascii=False)
    print(json.dumps(crit["verdict"], ensure_ascii=False))
    return crit


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
