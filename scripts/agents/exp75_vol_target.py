"""Exp 75 (preregistered, docs/agents/hypotheses/Exp-75.md, commit ba53a83): S&P 500 volatility targeting,
leverage capped at x3, versus a constant-leverage reference with EQUAL realised volatility.

Rule (fixed, no tuning):
  * sigma_t = std(ddof=1) of the 21 daily TR returns ending at t (t included) * sqrt(252);
  * target_t = min(3, V / sigma_t), V = 25 % (decisional), 20 % / 30 % robustness;
  * target_t is executed at close t+1 (so it earns the return of day t+2), and only if
    |target_t - w_current| >= 0.25 (band). Before sigma exists the position is 0 (cash);
  * daily return: w * r_TR + (1 - w) * rf - FEE * max(w - 1, 0) / 252, rf = ^IRX / 100 / 252 (ffill);
  * cost: 0.10 % * |delta w| of capital, charged on the first day the new weight earns returns.

Reference: constant weight L, same return formula, free daily rebalancing, L solved (brentq) so that the
reference's realised daily volatility (std ddof=1 of daily returns) equals the rule's on the SAME evaluated
period. L is re-solved for every evaluated period/window.

Usage:  py -3 scripts/agents/exp75_vol_target.py run

Conservative / interpretive choices (spec silent or ambiguous), flagged in the deliverable:
  * criterion 1 "et il est > 0 en Pre comme en Post": read BOTH as rule Sharpe > 0 AND Sharpe gap > 0 in
    Pre and Post (the stricter reading); both components are reported separately;
  * no ETF-proxy extra drag in the decisional figures (spec fixes the formula); a sensitivity with the Exp 74
    UPRO gap (1.356 %/yr for 2 units of excess leverage -> +0.678 %/yr per unit) is reported only;
  * NDX / RUT: price-only on both sides (no full-period TR); DAX is a performance (TR) index in EUR, US rf used.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "agents"))
import exp74_leveraged_trend as e74  # noqa: E402  (loaders + metrics reused)

OUT_DIR = REPO / "docs" / "agents" / "results"
TD = 252
V_DEC = 0.25
V_ROB = (0.20, 0.30)
WINDOW = 21
CAP = 3.0
BAND = 0.25
FEE = 0.0095
COST = 0.0010
N_TRIALS = 75
START = "1990-01-01"
PRE = ("1990-01-01", "2016-02-29")
POST_START = "2016-03-01"
EXTRA_DRAG_PER_UNIT = 0.013562986538093423 / 2.0  # Exp 74 UPRO gap, sensitivity only
PERIODS = {"full": (START, None), "pre": PRE, "post": (POST_START, None)}


# ---------------------------------------------------------------- core (pure)
def realised_vol(r: pd.Series, window: int = WINDOW) -> pd.Series:
    """sigma_t: annualised std of the `window` returns ending at t (t included). NaN until `window` returns exist."""
    return r.rolling(window, min_periods=window).std(ddof=1) * math.sqrt(TD)


def target_weights(r: pd.Series, V: float, window: int = WINDOW, cap: float = CAP) -> pd.Series:
    """target_t = min(cap, V / sigma_t); 0 where sigma_t is not yet defined (or zero)."""
    sig = realised_vol(r, window)
    w = (V / sig).clip(upper=cap)
    w[~np.isfinite(w)] = 0.0
    return w.fillna(0.0)


def held_weights(target: pd.Series, band: float = BAND) -> tuple[pd.Series, pd.Series]:
    """Execute target_t at close t+1 if |target_t - current| >= band.
    Returns (held, traded): held[d] = weight earning the return of day d (= position after close d-1);
    traded[e] = True if a trade happened at close e."""
    tv = target.shift(1).fillna(0.0).values  # target available for execution at close e is target_{e-1}
    n = len(tv)
    after = np.zeros(n)
    traded = np.zeros(n, dtype=bool)
    cur = 0.0
    for e in range(n):
        if abs(tv[e] - cur) >= band - 1e-12:
            if tv[e] != cur:
                traded[e] = True
            cur = tv[e]
        after[e] = cur
    held = pd.Series(after, index=target.index).shift(1).fillna(0.0)
    return held, pd.Series(traded, index=target.index)


def weighted_returns(w, r_tr: pd.Series, rf: pd.Series, fee: float = FEE, extra_per_unit: float = 0.0) -> pd.Series:
    """w * r_TR + (1 - w) * rf - (fee + extra_per_unit) * max(w - 1, 0) / TD. w scalar or Series."""
    if np.isscalar(w):
        w = pd.Series(float(w), index=r_tr.index)
    ex = np.maximum(w - 1.0, 0.0)
    return w * r_tr + (1.0 - w) * rf - (fee + extra_per_unit) * ex / TD


def rule_returns(held: pd.Series, r_tr: pd.Series, rf: pd.Series, cost: float = COST, fee: float = FEE,
                 extra_per_unit: float = 0.0) -> pd.Series:
    gross = weighted_returns(held, r_tr, rf, fee, extra_per_unit)
    dw = held.diff().abs().fillna(held.abs())
    return (1 + gross) * (1 - cost * dw) - 1


def ann_vol(r: pd.Series) -> float:
    return float(r.dropna().std(ddof=1) * math.sqrt(TD))


def solve_L(r_tr: pd.Series, rf: pd.Series, target_vol: float, fee: float = FEE, extra_per_unit: float = 0.0,
            hi: float = 20.0) -> float:
    """Constant weight L >= 0 whose daily-return realised vol equals target_vol (annualised) on r_tr's index."""
    def f(L):
        return ann_vol(weighted_returns(L, r_tr, rf, fee, extra_per_unit)) - target_vol
    lo = 0.0
    if f(lo) >= 0:
        return 0.0
    return float(brentq(f, lo, hi, xtol=1e-10))


def sub(r, a, b=None):
    return e74.sub(r, a, b)


def sharpe(r, rf):
    return e74.sharpe(r, rf)


def period_block(r_rule: pd.Series, held: pd.Series, traded: pd.Series, r_tr: pd.Series, rf: pd.Series,
                 a: str, b: str | None, fee: float = FEE, extra_per_unit: float = 0.0) -> dict:
    rr = sub(r_rule, a, b)
    rt = sub(r_tr, a, b)
    rfp = sub(rf, a, b)
    hv = sub(held, a, b)
    vol = ann_vol(rr)
    L = solve_L(rt, rfp, vol, fee, extra_per_unit)
    ref = weighted_returns(L, rt, rfp, fee, extra_per_unit)
    s_rule = e74.stats(rr, rf)
    s_ref = e74.stats(ref, rf)
    s_rule["vol"], s_ref["vol"] = vol, ann_vol(ref)
    yrs = len(rr) / TD
    s_rule["rebalances"] = int(sub(traded, a, b).sum())
    s_rule["rebalances_per_year"] = s_rule["rebalances"] / yrs
    s_rule["mean_leverage"] = float(hv.mean())
    s_rule["share_time_w_gt_2"] = float((hv > 2.0).mean())
    s_rule["share_time_w_lt_1"] = float((hv < 1.0).mean())
    s_rule["share_time_at_cap"] = float((hv >= CAP - 1e-9).mean())
    s_rule["dsr_n75"] = e74.deflated_sharpe(rr, rf, N_TRIALS)
    return {"rule": s_rule, "ref": s_ref, "L": L, "sharpe_gap": s_rule["sharpe"] - s_ref["sharpe"],
            "cagr_gap": s_rule["cagr"] - s_ref["cagr"], "_ref_series": ref}


def top3_share(r_rule: pd.Series, r_ref: pd.Series) -> dict:
    """Yearly log-return surplus of rule over reference; share of the total surplus from the 3 best years."""
    yr = np.log1p(e74.period_returns(r_rule, "Y")) - np.log1p(e74.period_returns(r_ref, "Y"))
    tot = float(yr.sum())
    best = yr.sort_values(ascending=False).head(3)
    share = float(best.sum() / tot) if tot > 0 else float("nan")
    return {"total_log_surplus": tot, "top3_years": {str(k): float(v) for k, v in best.items()},
            "top3_share": share, "n_years": int(len(yr)), "n_years_positive": int((yr > 0).sum()),
            "yearly_log_surplus": {str(k): float(v) for k, v in yr.items()}}


def rolling_windows(r_rule, r_tr, rf, years: int = 10, fee: float = FEE) -> dict:
    starts = pd.date_range(START, r_rule.index[-1] - pd.DateOffset(years=years), freq="MS")
    gaps = []
    for s in starts:
        e = s + pd.DateOffset(years=years) - pd.Timedelta(days=1)
        rr, rt, rfp = r_rule[s:e], r_tr[s:e], rf[s:e]
        L = solve_L(rt, rfp, ann_vol(rr), fee)
        ref = weighted_returns(L, rt, rfp, fee)
        gaps.append({"start": str(s.date()), "gap": sharpe(rr, rf) - sharpe(ref, rf),
                     "cagr_gap": e74.cagr(rr) - e74.cagr(ref)})
    g = np.array([x["gap"] for x in gaps])
    return {"n_windows": len(g), "share_gap_pos": float((g > 0).mean()), "min_gap": float(g.min()),
            "median_gap": float(np.median(g)), "max_gap": float(g.max()),
            "worst_start": gaps[int(g.argmin())]["start"], "best_start": gaps[int(g.argmax())]["start"],
            "share_cagr_gap_pos": float(np.mean([x["cagr_gap"] > 0 for x in gaps])),
            "yearly_starts": [x for x in gaps if x["start"].endswith("-01-01")]}


def verdict(gap_full_25: float, sh_rule_pre: float, sh_rule_post: float, gap_pre: float, gap_post: float,
            gap_full_20: float, gap_full_30: float, idx_gaps: dict, post_cagr: float, full_maxdd: float) -> dict:
    c1 = gap_full_25 >= 0.10 and sh_rule_pre > 0 and sh_rule_post > 0 and gap_pre > 0 and gap_post > 0
    c1_lenient = gap_full_25 >= 0.10 and sh_rule_pre > 0 and sh_rule_post > 0
    c2 = gap_full_20 > 0 and gap_full_30 > 0
    n_pos = sum(int(g > 0) for g in idx_gaps.values())
    n_nonpos = sum(int(g <= 0) for g in idx_gaps.values())
    c3 = n_pos >= 2
    c4 = post_cagr >= 0.15 and full_maxdd >= -0.50
    rej = gap_full_25 <= 0 or n_nonpos >= 2
    v = "PASS" if (c1 and c2 and c3 and c4) else ("REJET" if rej else "INCERTAIN")
    return {"verdict": v, "c1_strict": c1, "c1_lenient_rule_sharpe_only": c1_lenient, "c2_robust_V20_V30": c2,
            "c3_same_sign_2of3": c3, "c4_post_cagr_ge15_full_maxdd_ge_m50": c4,
            "reject_gap_full_le_0": gap_full_25 <= 0, "reject_2of3_indices_le_0": n_nonpos >= 2,
            "n_indices_gap_pos": n_pos}


# ---------------------------------------------------------------- run
def build(px_tr: pd.Series, irx: pd.Series, V: float, window: int = WINDOW, sma_close: pd.Series | None = None,
          extra_per_unit: float = 0.0):
    idx = px_tr.index
    if sma_close is not None:
        idx = idx.intersection(sma_close.index)
    lvl = px_tr.loc[idx]
    r_tr = lvl.pct_change()
    rf = (irx.reindex(idx.union(irx.index)).ffill().reindex(idx)) / 100.0 / TD
    tgt = target_weights(r_tr, V, window)
    if sma_close is not None:
        sig = e74.sma_signal(sma_close.loc[idx])
        tgt = tgt.where(sig == 1, 0.0)
    held, traded = held_weights(tgt)
    r = rule_returns(held, r_tr.fillna(0.0), rf, extra_per_unit=extra_per_unit)
    r_tr_c = r_tr.fillna(0.0)
    m = idx >= pd.Timestamp(START)
    return {"r": r[m], "held": held[m], "traded": traded[m], "r_tr": r_tr_c[m], "rf": rf[m],
            "sigma": realised_vol(r_tr, window)[m], "target": tgt[m]}


def evaluate(b: dict, extra_per_unit: float = 0.0) -> dict:
    out = {}
    for pn, (a, z) in PERIODS.items():
        blk = period_block(b["r"], b["held"], b["traded"], b["r_tr"], b["rf"], a, z, FEE, extra_per_unit)
        out[pn] = blk
    return out


def strip(d):
    if isinstance(d, dict):
        return {k: strip(v) for k, v in d.items() if not k.startswith("_")}
    return d


def run():
    meta = json.loads((e74.DATA_DIR / "meta.json").read_text())
    tr, irx, gspc = e74.load("^SP500TR"), e74.load("^IRX"), e74.load("^GSPC")
    res = {"meta": meta, "params": {"V_dec": V_DEC, "V_rob": V_ROB, "window": WINDOW, "cap": CAP, "band": BAND,
                                    "fee": FEE, "cost": COST, "td": TD, "n_trials": N_TRIALS, "pre": PRE,
                                    "post_start": POST_START, "exec": "target_t executed at close t+1"}}
    sp = {}
    builds = {}
    for V in (0.20, 0.25, 0.30):
        b = build(tr, irx, V)
        builds[V] = b
        sp[f"V{int(V*100)}"] = evaluate(b)
    bh = builds[0.25]["r_tr"]
    sp["sp500tr_x1"] = {pn: e74.stats(sub(bh, a, z), builds[0.25]["rf"]) | {"vol": ann_vol(sub(bh, a, z))}
                        for pn, (a, z) in PERIODS.items()}
    # reported only: window 63, MM200 combination, extra drag sensitivity
    b63 = build(tr, irx, V_DEC, window=63)
    sp["V25_window63"] = evaluate(b63)
    bmm = build(tr, irx, V_DEC, sma_close=gspc)
    sp["V25_MM200"] = evaluate(bmm)
    bdr = build(tr, irx, V_DEC, extra_per_unit=EXTRA_DRAG_PER_UNIT)
    sp["V25_extra_drag_sens"] = evaluate(bdr, EXTRA_DRAG_PER_UNIT)
    res["sp500"] = strip(sp)

    b25 = builds[0.25]
    full25 = sp["V25"]["full"]
    res["top3_share_full"] = top3_share(b25["r"], full25["_ref_series"])
    res["rolling_10y"] = rolling_windows(b25["r"], b25["r_tr"], b25["rf"])
    res["yearly"] = {str(k): {"rule_V25": float(v), "ref_V25_fullL": float(w), "sp500tr": float(x)}
                     for (k, v), w, x in zip(e74.period_returns(b25["r"], "Y").items(),
                                             e74.period_returns(full25["_ref_series"], "Y").values,
                                             e74.period_returns(b25["r_tr"], "Y").values)}

    # CAD (rule and full-period reference)
    fx = e74.load_cadusd()
    fxa = fx.reindex(b25["r"].index.union(fx.index)).ffill().reindex(b25["r"].index)
    fxr = fxa.pct_change().fillna(0)
    cad = {}
    for pn, (a, z) in PERIODS.items():
        rr = sub(b25["r"], a, z)
        ref = sp["V25"][pn]["_ref_series"]
        f = sub(fxr, a, z)
        rc, fc = (1 + rr) * (1 + f) - 1, (1 + ref) * (1 + f) - 1
        cad[pn] = {"rule": {"cagr": e74.cagr(rc), "maxdd": e74.max_dd(rc), "vol": ann_vol(rc)},
                   "ref": {"cagr": e74.cagr(fc), "maxdd": e74.max_dd(fc), "vol": ann_vol(fc)}}
    res["cad"] = cad

    # other indices
    others = {}
    notes = {"^NDX": "price-only both sides (no TR on Yahoo)", "^RUT": "price-only both sides over full period",
             "^GDAXI": "DAX performance (TR) index in EUR; US T-bill rf used (flag)"}
    idx_gaps = {}
    for sym in ("^NDX", "^RUT", "^GDAXI"):
        px = e74.load(sym)
        o = {"note": notes[sym]}
        for V in (0.20, 0.25, 0.30):
            o[f"V{int(V*100)}"] = strip(evaluate(build(px, irx, V)))
        bhx = build(px, irx, V_DEC)["r_tr"]
        o["hold_x1_full"] = e74.stats(bhx, build(px, irx, V_DEC)["rf"]) | {"vol": ann_vol(bhx)}
        others[sym] = o
        idx_gaps[sym] = o["V25"]["full"]["sharpe_gap"]
    ruttr = e74.load("^RUTTR")
    bru = build(ruttr, irx, V_DEC)
    others["^RUTTR_sensitivity"] = {"note": "^RUTTR from 1995-06, evaluated from 1995-08-01 (after warm-up), reported only",
                                    "V25_full": strip(period_block(bru["r"], bru["held"], bru["traded"], bru["r_tr"],
                                                                   bru["rf"], "1995-08-01", None))}
    res["others"] = others

    s = res["sp500"]
    crit = verdict(s["V25"]["full"]["sharpe_gap"], s["V25"]["pre"]["rule"]["sharpe"], s["V25"]["post"]["rule"]["sharpe"],
                   s["V25"]["pre"]["sharpe_gap"], s["V25"]["post"]["sharpe_gap"], s["V20"]["full"]["sharpe_gap"],
                   s["V30"]["full"]["sharpe_gap"], idx_gaps, s["V25"]["post"]["rule"]["cagr"],
                   s["V25"]["full"]["rule"]["maxdd"])
    crit.update({"gap_full_V25": s["V25"]["full"]["sharpe_gap"], "gap_pre_V25": s["V25"]["pre"]["sharpe_gap"],
                 "gap_post_V25": s["V25"]["post"]["sharpe_gap"], "gap_full_V20": s["V20"]["full"]["sharpe_gap"],
                 "gap_full_V30": s["V30"]["full"]["sharpe_gap"], "index_gaps_V25_full": idx_gaps,
                 "post_cagr_V25": s["V25"]["post"]["rule"]["cagr"], "full_maxdd_V25": s["V25"]["full"]["rule"]["maxdd"]})
    res["criteria"] = crit

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "Exp-75_2026-10-11_criteria.json").write_text(json.dumps(res, indent=2, default=str))
    daily = pd.DataFrame({"r_sp500tr": b25["r_tr"], "rf_daily": b25["rf"], "sigma21": b25["sigma"],
                          "target_V25": b25["target"], "held_V25": b25["held"], "traded_V25": b25["traded"].astype(int),
                          "rule_V25": b25["r"], "ref_V25_fullL": full25["_ref_series"],
                          "rule_V20": builds[0.20]["r"], "rule_V30": builds[0.30]["r"],
                          "rule_V25_MM200": bmm["r"], "rule_V25_w63": b63["r"], "cad_per_usd": fxa})
    daily.index.name = "date"
    daily.to_csv(OUT_DIR / "Exp-75_2026-10-11_daily.csv", float_format="%.8g")
    print(json.dumps(crit, indent=2))


if __name__ == "__main__":
    run()
