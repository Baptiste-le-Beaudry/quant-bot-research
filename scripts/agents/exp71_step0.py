"""Exp 71 step 0 (blocking) -- data checks only, no PnL computed.

Same checks as Exp 64 section 2: time zone, bar labelling, RTH completeness, CFD volume, plus the
eligibility rule of Exp 64 section 3.6 (engine functions, unchanged) and the technical-reject
thresholds of the preregistration (>= 1000 eligible days for MYM, >= 800 for M2K).

Usage:
    python scripts/agents/exp71_step0.py --data-dir C:/AAProjet/quant_bot_v1/data/indices \
        --out docs/agents/results/Exp-71_step0.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1].parent
_spec = importlib.util.spec_from_file_location("exp64", ROOT / "scripts" / "agents" / "exp64_noise_momentum.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

PREREG = ROOT / "docs" / "agents" / "hypotheses" / "Exp-71.md"
NAMES = ("DOW30", "RUSSELL2000")
MIN_ELIGIBLE = {"DOW30": 1000, "RUSSELL2000": 800}


def load_full(path) -> pd.DataFrame:
    """Whole series (single test, no HOLDOUT split per the preregistration): the engine loader is
    reused unchanged, the preregistration being the written decision that the full file is read."""
    return E.load_pre_holdout(path, str(PREREG))


def minute_profile(df: pd.DataFrame, minutes: list) -> dict:
    """Mean |close/open - 1| (in %) and median volume per ET minute-of-day label."""
    hm = df.index.hour * 60 + df.index.minute
    r = (df["close"] / df["open"] - 1.0).abs() * 100.0
    out = {}
    for m in minutes:
        sel = hm == m
        out[f"{m // 60:02d}:{m % 60:02d}"] = {"mean_abs_ret_pct": float(r[sel].mean()) if sel.any() else None,
                                              "median_volume": float(df["volume"][sel].median()) if sel.any() else None,
                                              "n": int(sel.sum())}
    return out


def completeness_by_year(grid: dict, elig: pd.DataFrame) -> dict:
    present = ~np.isnan(grid["close"])
    v = grid["volume"]
    years = np.array([d.year for d in grid["dates"]])
    out = {}
    for y in sorted(set(years)):
        s = years == y
        pv = present[s]
        vols = v[s][pv]
        out[int(y)] = {
            "sessions": int(s.sum()),
            "frac_with_0930_bar": float(pv[:, 0].mean()),
            "frac_with_1559_bar": float(pv[:, E.EXIT_IDX].mean()),
            "median_rth_bars_present": float(np.median(pv.sum(axis=1))),
            "median_max_gap_min": float(elig.loc[s, "max_gap"].median()),
            "rth_zero_volume_frac": float((vols == 0).mean()) if len(vols) else None,
            "rth_volume_multiple_of_1e6_frac": float((np.mod(vols, 1e6) == 0).mean()) if len(vols) else None,
            "eligible": int(elig.loc[s, "eligible"].sum()),
        }
    return out


def step0_index(name: str, data_dir) -> dict:
    spec = E.INSTRUMENTS[name]
    df = load_full(Path(data_dir) / spec["file"])
    info = {"file": spec["file"], "future": spec["future"], "mult_usd_per_pt": spec["mult"],
            "tick_usd": spec["tick_usd"], "cost_rt_usd": 2 * (E.COMM_PER_SIDE + spec["tick_usd"]),
            "n_bars": int(len(df)), "first_bar_et": str(df.index.min()), "last_bar_et": str(df.index.max()),
            "duplicated_timestamps": int(df.index.duplicated().sum()),
            "tz_label_profile_open": minute_profile(df, [9 * 60 + 27, 9 * 60 + 28, 9 * 60 + 29, 9 * 60 + 30,
                                                         9 * 60 + 31, 9 * 60 + 32]),
            "tz_label_profile_close": minute_profile(df, [15 * 60 + 58, 15 * 60 + 59, 16 * 60, 16 * 60 + 1])}
    grid = E.build_grid(df)
    del df
    elig = E.eligibility(grid)
    lv = E.compute_levels(grid, elig)
    n_elig = int(elig["eligible"].sum())
    info.update({
        "sessions_in_grid": len(grid["dates"]), "eligible_sessions": n_elig,
        "tradable_sessions_after_14d_history": int(lv["tradable"].sum()),
        "excluded_half_days": int(elig["half_day"].sum()),
        "exclusion_reasons": {
            "half_day": int(elig["half_day"].sum()),
            "no_0930_bar": int((~elig["has_open"]).sum()),
            "no_1559_bar": int((~elig["has_exit"]).sum()),
            "max_gap_gt_5": int((elig["max_gap"] > E.MAX_GAP_MIN).sum()),
            "zero_vol_frac_gt_5pct": int((elig["zero_vol_frac"] > E.MAX_ZERO_VOL_FRAC).sum()),
            "no_prev_close": int(elig["prev_close"].isna().sum())},
        "by_year": completeness_by_year(grid, elig),
        "min_eligible_required": MIN_ELIGIBLE[name],
        "technical_reject": bool(n_elig < MIN_ELIGIBLE[name]),
    })
    return info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    res = {n: step0_index(n, a.data_dir) for n in NAMES}
    res["technical_reject_any"] = any(res[n]["technical_reject"] for n in NAMES)
    Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    for n in NAMES:
        print(n, res[n]["n_bars"], res[n]["first_bar_et"], res[n]["last_bar_et"],
              "eligible", res[n]["eligible_sessions"], "tech_reject", res[n]["technical_reject"], flush=True)
    return res


if __name__ == "__main__":
    main()
    sys.exit(0)
