"""Exp 64 -- intraday "noise area" momentum (Zarattini-Aziz-Barbon 2024) on MES/MNQ.

Frozen reading: docs/agents/results/Exp-64_2026-10-08.md section 3 (committed before any computation).
Preregistration: docs/agents/hypotheses/Exp-64.md.

The common execution harness (quant_bot/execution_harness) is NOT used: it only models
fixed/trailing stops in return space filled intrabar at the stop level, while this rule needs
band/VWAP stops evaluated only at HH:00/HH:30 and filled at the next bar open, with per-contract
USD fees. The fill convention here follows the preregistration (next-bar open, never at the stop).

HOLDOUT: SP500_1m.csv / NASDAQ100_1m.csv carry the positional 60/20/20 HOLDOUT (last 20 % of rows)
registered by Exp 32 / STRATEGY_B_INDEX_SPEC. The loader reads only the first int(0.8*n) rows
unless an explicit written decision file is supplied.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.easter import easter

ET = "America/New_York"
N_MIN = 390                      # 09:30 .. 15:59 bars (start-labelled)
HALF_N_MIN = 210                 # 09:30 .. 12:59
DECISION_IDX = [29 + 30 * k for k in range(12)]   # bar ending at 10:00, 10:30, ..., 15:30
DECISION_LABELS = [f"{10 + (30 * k) // 60:02d}:{(30 * k) % 60:02d}" for k in range(12)]
EXIT_IDX = 389                   # open of the 15:59 bar
LOOKBACK = 14
MAX_GAP_MIN = 5
MAX_ZERO_VOL_FRAC = 0.05
COMM_PER_SIDE = 0.61             # 1.22 USD round trip (Topstep)
HOLDOUT_FRACTION = 0.8           # positional convention of scripts/nasdaq_baseline_test.py

INSTRUMENTS = {
    "SP500": {"file": "SP500_1m.csv", "future": "MES", "mult": 5.0, "tick_usd": 1.25},
    "NASDAQ100": {"file": "NASDAQ100_1m.csv", "future": "MNQ", "mult": 2.0, "tick_usd": 0.50},
    # Exp 71 (docs/agents/hypotheses/Exp-71.md): only permitted change to this engine.
    "DOW30": {"file": "DOW30_1m.csv", "future": "MYM", "mult": 0.5, "tick_usd": 0.50},
    "RUSSELL2000": {"file": "RUSSELL2000_1m.csv", "future": "M2K", "mult": 5.0, "tick_usd": 0.50},
}
EXP64_INSTRUMENTS = ("SP500", "NASDAQ100")  # main() of Exp 64 stays on its preregistered pair
PERIODS = {"P1": (dt.date(2012, 1, 1), dt.date(2024, 10, 31)),
           "P2": (dt.date(2024, 11, 27), dt.date(2100, 1, 1))}
EXTRA_CLOSURES = {dt.date(2012, 10, 29), dt.date(2012, 10, 30), dt.date(2018, 12, 5), dt.date(2025, 1, 9)}


class HoldoutLockedError(RuntimeError):
    pass


# --------------------------------------------------------------------------- calendar
def _nth_weekday(year, month, weekday, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year, month, weekday):
    d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d):
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


def nyse_holidays(year: int) -> set:
    h = set()
    ny = dt.date(year, 1, 1)
    if ny.weekday() == 6:
        h.add(dt.date(year, 1, 2))
    elif ny.weekday() != 5:          # NYSE does not observe Jan 1 falling on Saturday
        h.add(ny)
    h.add(_nth_weekday(year, 1, 0, 3))            # MLK
    h.add(_nth_weekday(year, 2, 0, 3))            # Presidents
    h.add(easter(year) - dt.timedelta(days=2))    # Good Friday
    h.add(_last_weekday(year, 5, 0))              # Memorial
    if year >= 2022:
        h.add(_observed(dt.date(year, 6, 19)))    # Juneteenth
    h.add(_observed(dt.date(year, 7, 4)))
    h.add(_nth_weekday(year, 9, 0, 1))            # Labor
    h.add(_nth_weekday(year, 11, 3, 4))           # Thanksgiving
    h.add(_observed(dt.date(year, 12, 25)))
    h |= {d for d in EXTRA_CLOSURES if d.year == year}
    return h


def nyse_half_days(year: int) -> set:
    s = {_nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1)}
    for d in (dt.date(year, 12, 24), dt.date(year, 7, 3)):
        if d.weekday() <= 3:
            s.add(d)
    return s - nyse_holidays(year)


def is_session(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in nyse_holidays(d.year)


def previous_session(d: dt.date) -> dt.date:
    p = d - dt.timedelta(days=1)
    while not is_session(p):
        p -= dt.timedelta(days=1)
    return p


# --------------------------------------------------------------------------- data
def count_rows(path: Path) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f) - 1


def load_pre_holdout(path, holdout_decision: str | None = None) -> pd.DataFrame:
    """Read the CSV; only the first int(0.8*n) rows unless a written decision file exists."""
    path = Path(path)
    if holdout_decision is not None:
        if not Path(holdout_decision).is_file():
            raise HoldoutLockedError(f"HOLDOUT decision file not found: {holdout_decision}")
        nrows = None
    else:
        nrows = int(count_rows(path) * HOLDOUT_FRACTION)
    df = pd.read_csv(path, nrows=nrows)
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(ET)
    df = df.drop(columns=["timestamp"])
    df.index = pd.DatetimeIndex(ts, name="et")
    return df


def build_grid(df: pd.DataFrame) -> dict:
    """Per NYSE session, 390-minute RTH grid (NaN where the bar is missing)."""
    idx = df.index
    minute = (idx.hour * 60 + idx.minute).to_numpy() - 570
    in_rth = (minute >= 0) & (minute < N_MIN)
    dates = np.array(idx.date)[in_rth]
    minute = minute[in_rth]
    sub = df.loc[in_rth]
    days = sorted({d for d in set(dates) if is_session(d)})
    pos = {d: i for i, d in enumerate(days)}
    keep = np.array([d in pos for d in dates], dtype=bool)
    row = np.array([pos[d] for d in dates[keep]], dtype=int)
    col = minute[keep]
    out = {"dates": days}
    for k in ("open", "high", "low", "close", "volume"):
        a = np.full((len(days), N_MIN), np.nan)
        a[row, col] = sub[k].to_numpy(dtype=float)[keep]
        out[k] = a
    return out


def _ffill_rows(a: np.ndarray) -> np.ndarray:
    mask = np.isnan(a)
    idx = np.where(~mask, np.arange(a.shape[1]), 0)
    np.maximum.accumulate(idx, axis=1, out=idx)
    return a[np.arange(a.shape[0])[:, None], idx]   # leading NaNs stay NaN (idx 0 is NaN)


def eligibility(grid: dict) -> pd.DataFrame:
    dates = grid["dates"]
    o, c, v = grid["open"], grid["close"], grid["volume"]
    present = ~np.isnan(c)
    pos_of = {d: i for i, d in enumerate(dates)}
    rows = []
    for i, d in enumerate(dates):
        half = d in nyse_half_days(d.year)
        cols = np.flatnonzero(present[i])
        if len(cols):
            full = np.concatenate([[-1], cols, [N_MIN]])
            maxgap = int((np.diff(full) - 1).max())
        else:
            maxgap = N_MIN
        has_open = bool(present[i, 0]) and not np.isnan(o[i, 0])
        has_exit = bool(present[i, EXIT_IDX]) and not np.isnan(o[i, EXIT_IDX])
        vv = v[i, cols] if len(cols) else np.array([])
        zero_frac = float((vv == 0).mean()) if len(vv) else 1.0
        # previous session close
        p = previous_session(d)
        prev_close = np.nan
        if p in pos_of:
            j = pos_of[p]
            end = HALF_N_MIN if p in nyse_half_days(p.year) else N_MIN
            seg = c[j, end - MAX_GAP_MIN:end]
            ok = np.flatnonzero(~np.isnan(seg))
            if len(ok):
                prev_close = float(seg[ok[-1]])
        elig = (not half) and has_open and has_exit and maxgap <= MAX_GAP_MIN \
            and zero_frac <= MAX_ZERO_VOL_FRAC and not np.isnan(prev_close)
        rows.append({"date": d, "half_day": half, "has_open": has_open, "has_exit": has_exit,
                     "max_gap": maxgap, "zero_vol_frac": zero_frac, "prev_close": prev_close,
                     "eligible": bool(elig)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- signals
def compute_levels(grid: dict, elig: pd.DataFrame) -> dict:
    """Decision prices, sigma (14 previous eligible days), bounds and VWAP at each decision time."""
    o, h, l, c, v = (grid[k] for k in ("open", "high", "low", "close", "volume"))
    cf = _ffill_rows(c)
    o930 = o[:, 0]
    P = cf[:, DECISION_IDX]                                   # price at HH:MM (as-of)
    move = np.abs(P / o930[:, None] - 1.0)
    e = elig["eligible"].to_numpy()
    n = len(o930)
    sigma = np.full((n, len(DECISION_IDX)), np.nan)
    hist = []
    for i in range(n):
        if len(hist) >= LOOKBACK:
            sigma[i] = move[hist[-LOOKBACK:]].mean(axis=0)
        if e[i]:
            hist.append(i)
    prev_close = elig["prev_close"].to_numpy()
    ub = np.maximum(o930, prev_close)[:, None] * (1.0 + sigma)
    lb = np.minimum(o930, prev_close)[:, None] * (1.0 - sigma)
    tp = (h + l + c) / 3.0
    vol = np.nan_to_num(v)
    pv = np.nancumsum(np.where(np.isnan(tp), 0.0, tp * vol), axis=1)
    cv = np.cumsum(vol, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        vwap_all = np.where(cv > 0, pv / cv, np.nan)
    vwap = vwap_all[:, DECISION_IDX]
    tradable = e & np.isfinite(sigma).all(axis=1) & np.isfinite(vwap).all(axis=1) & np.isfinite(P).all(axis=1)
    return {"P": P, "sigma": sigma, "ub": ub, "lb": lb, "vwap": vwap, "o930": o930, "tradable": tradable}


def _exec_price(orow: np.ndarray, idx: int):
    """Open of bar idx, else first available bar after it (strictly before the 15:59 exit bar)."""
    for j in range(idx, EXIT_IDX):
        if not np.isnan(orow[j]):
            return j, float(orow[j])
    return EXIT_IDX, float(orow[EXIT_IDX])


def next_state(pos: int, p: float, ub: float, lb: float, vwap: float) -> int:
    if pos == 0:
        return 1 if p > ub else (-1 if p < lb else 0)
    if pos == 1:
        if p < lb:
            return -1
        return 0 if p < max(ub, vwap) else 1
    if p > ub:
        return 1
    return 0 if p > min(lb, vwap) else -1


def simulate_noise(grid: dict, elig: pd.DataFrame, lv: dict) -> list:
    o = grid["open"]
    trades = []
    for i, d in enumerate(grid["dates"]):
        if not lv["tradable"][i]:
            continue
        pos, entry = 0, None
        for k, di in enumerate(DECISION_IDX):
            new = next_state(pos, lv["P"][i, k], lv["ub"][i, k], lv["lb"][i, k], lv["vwap"][i, k])
            if new == pos:
                continue
            j, px = _exec_price(o[i], di + 1)
            if pos != 0:
                trades.append(_close(d, entry, j, px, "reverse" if new != 0 else "stop"))
            pos = new
            entry = (new, j, px, DECISION_LABELS[k]) if new != 0 else None
        if pos != 0:
            trades.append(_close(d, entry, EXIT_IDX, float(o[i, EXIT_IDX]), "eod"))
    return trades


def _close(d, entry, j, px, reason):
    side, ej, epx, lab = entry
    return {"date": d, "side": side, "decision": lab, "entry_bar": ej, "entry_px": epx,
            "exit_bar": j, "exit_px": px, "exit_reason": reason}


def simulate_gao(grid: dict, elig: pd.DataFrame, lv: dict) -> list:
    o = grid["open"]
    trades = []
    k1530 = DECISION_LABELS.index("15:30")
    for i, d in enumerate(grid["dates"]):
        if not lv["tradable"][i]:
            continue
        r = lv["P"][i, k1530] / lv["o930"][i] - 1.0
        if not np.isfinite(r) or r == 0:
            continue
        side = 1 if r > 0 else -1
        j, px = _exec_price(o[i], DECISION_IDX[k1530] + 1)
        trades.append(_close(d, (side, j, px, "15:30"), EXIT_IDX, float(o[i, EXIT_IDX]), "eod"))
    return trades


# --------------------------------------------------------------------------- accounting
def price_trades(trades: list, spec: dict) -> pd.DataFrame:
    t = pd.DataFrame(trades, columns=["date", "side", "decision", "entry_bar", "entry_px",
                                      "exit_bar", "exit_px", "exit_reason"])
    t["gross_usd"] = t["side"] * (t["exit_px"] - t["entry_px"]) * spec["mult"]
    t["cost_usd"] = 2.0 * (COMM_PER_SIDE + spec["tick_usd"])
    t["net_usd"] = t["gross_usd"] - t["cost_usd"]
    return t


def daily_series(trades: pd.DataFrame, elig: pd.DataFrame, lv: dict, grid: dict, spec: dict) -> pd.DataFrame:
    # only days where the rule could be evaluated (eligible + 14-day history + VWAP defined) count
    ok = lv["tradable"]
    days = pd.DataFrame({"date": np.array(grid["dates"], dtype=object)[ok], "o930": lv["o930"][ok]})
    agg = trades.groupby("date").agg(n_trades=("net_usd", "size"), gross_usd=("gross_usd", "sum"),
                                     cost_usd=("cost_usd", "sum"), net_usd=("net_usd", "sum")) \
        if len(trades) else pd.DataFrame(columns=["n_trades", "gross_usd", "cost_usd", "net_usd"])
    days = days.merge(agg, left_on="date", right_index=True, how="left").fillna(
        {"n_trades": 0, "gross_usd": 0.0, "cost_usd": 0.0, "net_usd": 0.0})
    days["n_trades"] = days["n_trades"].astype(int)
    days["notional_usd"] = days["o930"] * spec["mult"]
    days["net_pct"] = 100.0 * days["net_usd"] / days["notional_usd"]
    days["gross_pct"] = 100.0 * days["gross_usd"] / days["notional_usd"]
    days["period"] = [period_of(d) for d in days["date"]]
    return days


def period_of(d) -> str:
    for p, (a, b) in PERIODS.items():
        if a <= d <= b:
            return p
    return "out"


def sharpe(x) -> float:
    x = np.asarray(x, dtype=float)
    if len(x) < 2 or np.std(x, ddof=1) == 0:
        return float("nan")
    return float(np.mean(x) / np.std(x, ddof=1) * math.sqrt(252))


def max_drawdown(x) -> float:
    eq = np.cumsum(np.asarray(x, dtype=float))
    if not len(eq):
        return float("nan")
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    return float((eq - peak).min())


def period_stats(days: pd.DataFrame) -> dict:
    if days.empty:
        return {"n_days": 0}
    g, cst, n = days["gross_usd"].sum(), days["cost_usd"].sum(), days["net_usd"]
    worst = days.loc[n.idxmin()]
    return {
        "first_day": str(days["date"].min()), "last_day": str(days["date"].max()),
        "n_days": int(len(days)), "days_traded": int((days["n_trades"] > 0).sum()),
        "n_trades": int(days["n_trades"].sum()),
        "sharpe_gross": sharpe(days["gross_usd"]), "sharpe_net": sharpe(n),
        "sharpe_net_pct_notional": sharpe(days["net_pct"]),
        "mean_net_usd_per_day": float(n.mean()), "mean_net_pct_per_day": float(days["net_pct"].mean()),
        "total_gross_usd": float(g), "total_cost_usd": float(cst), "total_net_usd": float(n.sum()),
        "cost_share_of_gross": float(cst / g) if g > 0 else None,
        "gross_nonpositive": bool(g <= 0),
        "maxdd_usd": max_drawdown(n), "worst_day_usd": float(worst["net_usd"]),
        "worst_day_date": str(worst["date"]), "best_day_usd": float(n.max()),
        "days_below_minus_1000_topstep_legacy_dll": int((n < -1000).sum()),
        "days_below_minus_1200_lucid_dll": int((n < -1200).sum()),
        "days_below_minus_2000_mll": int((n < -2000).sum()),
    }


def verdict(stats: dict) -> dict:
    """Mechanical reading of the preregistered criteria. stats[index][period] for the decision rule."""
    out = {"rule": "PASS: net Sharpe >= 0.5 in P1 and P2 on both, >200 traded days in P2; "
                   "REJET: net Sharpe <= 0 in P2 on at least one, or < 0.5 in P2 on both; else INCERTAIN"}
    p2 = {k: stats[k].get("P2", {}) for k in stats}
    p2_missing = any(v.get("n_days", 0) == 0 for v in p2.values())
    p1_pass = all(stats[k]["P1"].get("sharpe_net", -np.inf) >= 0.5 for k in stats)
    out["p1_both_net_sharpe_ge_0p5"] = bool(p1_pass)
    if p2_missing:
        out["verdict"] = "NON DETERMINABLE (P2 dans le HOLDOUT verrouille, non calcule)"
        out["pass_still_possible"] = bool(p1_pass)
        out["note"] = ("Sans P2, seuls PASS/INCERTAIN/REJET conditionnels : si P1 < 0,5 sur un indice, "
                       "PASS est exclu et le verdict sera REJET ou INCERTAIN selon P2.")
        return out
    s2 = {k: v["sharpe_net"] for k, v in p2.items()}
    if any(x <= 0 for x in s2.values()) or all(x < 0.5 for x in s2.values()):
        out["verdict"] = "REJET"
    elif p1_pass and all(x >= 0.5 for x in s2.values()) and all(v["days_traded"] > 200 for v in p2.values()):
        out["verdict"] = "PASS"
    else:
        out["verdict"] = "INCERTAIN"
    return out


# --------------------------------------------------------------------------- driver
def run_index(name: str, data_dir, holdout_decision=None):
    spec = INSTRUMENTS[name]
    df = load_pre_holdout(Path(data_dir) / spec["file"], holdout_decision)
    last_bar = str(df.index.max())
    grid = build_grid(df)
    del df
    elig = eligibility(grid)
    lv = compute_levels(grid, elig)
    res = {}
    for variant, fn in (("noise_area", simulate_noise), ("gao_last_half_hour", simulate_gao)):
        tr = price_trades(fn(grid, elig, lv), spec)
        days = daily_series(tr, elig, lv, grid, spec)
        res[variant] = (tr, days)
    info = {"last_bar_loaded_et": last_bar, "sessions_in_grid": len(grid["dates"]),
            "eligible_sessions": int(elig["eligible"].sum()),
            "excluded_half_days": int(elig["half_day"].sum()),
            "eligible_by_year": elig.assign(y=[d.year for d in elig["date"]]).groupby("y")["eligible"].sum().to_dict()}
    return res, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out-prefix", required=True, help="e.g. docs/agents/results/Exp-64_2026-10-08")
    ap.add_argument("--holdout-decision", default=None,
                    help="path to a written decision unlocking the HOLDOUT (absent = locked)")
    a = ap.parse_args(argv)
    all_days, all_trades, crit = [], [], {"holdout_locked": a.holdout_decision is None, "indices": {}}
    stats_rule = {}
    for name, spec in ((n, INSTRUMENTS[n]) for n in EXP64_INSTRUMENTS):
        res, info = run_index(name, a.data_dir, a.holdout_decision)
        crit["indices"][name] = {"future": spec["future"], "mult_usd_per_pt": spec["mult"],
                                 "cost_rt_usd": 2 * (COMM_PER_SIDE + spec["tick_usd"]), "data": info}
        for variant, (tr, days) in res.items():
            st = {p: period_stats(days[days["period"] == p]) for p in ("P1", "P2")}
            crit["indices"][name][variant] = st
            if variant == "noise_area":
                stats_rule[name] = st
            all_days.append(days.assign(index=name, future=spec["future"], variant=variant))
            all_trades.append(tr.assign(index=name, future=spec["future"], variant=variant))
        print(name, json.dumps(crit["indices"][name]["noise_area"], default=str), flush=True)
    crit["verdict_noise_area"] = verdict(stats_rule)
    crit["variants_counted"] = 2
    d = pd.concat(all_days, ignore_index=True)
    cols = ["date", "index", "future", "variant", "period", "n_trades", "gross_usd", "cost_usd", "net_usd",
            "notional_usd", "gross_pct", "net_pct"]
    d[cols].to_csv(a.out_prefix + "_daily.csv", index=False, float_format="%.6f")
    pd.concat(all_trades, ignore_index=True).to_csv(a.out_prefix + "_trades.csv", index=False, float_format="%.6f")
    with open(a.out_prefix + "_criteria.json", "w", encoding="utf-8") as f:
        json.dump(crit, f, indent=2, default=str, ensure_ascii=False)
    print(json.dumps(crit["verdict_noise_area"], ensure_ascii=False))
    return crit


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
