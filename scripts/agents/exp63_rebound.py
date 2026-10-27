"""Exp 63 (C-REBOUND-CONFIRM-001) -- strategy C "wait for the rebound to start", to the letter of
docs/agents/hypotheses/Exp-63.md (frozen in commit 49a37ba).

Signal: REF of Exp 53 (label 10 min, p >= 0.70, same filters, same folds) = the Exp 53 fold checkpoints'
REF signal times for SOL/BTC/ETH (outputs/exp53 of worktree agent-a17639c9ee2636b1f, read only). The
models reproducing them are checked by scripts/agents/exp63_verify_models.py (model_check.json).

Rule C (decisional K = 15):
  * signal bar s (bar labelled by its open time, signal known at its close), H = high[s];
  * confirmation = first bar cb = s + k, k in [1, K], with close[cb] > H; none -> no trade;
  * entry at the open of cb + 1, time exit at the close of the 50th bar (cb + 50), no stop:
    harness v1.2+ run_trades(signal_time = time of bar cb, entry_mode="next_open", ExitRule(max_bars=50));
  * one position per symbol; a signal arriving while a position or a confirmation wait is in progress
    on the same symbol is ignored.
REF: entry at the open of s + 1, same exit, sequenced as Exp 53 (scripts/agents/exp53_label50.sequence).

Points fixed HERE, before any harness computation (not fixed by the preregistration):
  * bars are positional (as the harness): "k bars after" = k rows later in the bar cache;
  * the wait ends at the close of bar s + K: a new signal AT bar s + K is accepted (same convention as
    REF, where a signal at the exit bar s + 50 is accepted: state is resolved before new signals);
    after a confirmed trade the next accepted signal is >= cb + 50 (exit bar);
  * if the data end before a confirmation, there is no trade (counted as unconfirmed);
  * period P1/P2 of a C trade = period of its RF signal time (s), as REF;
  * net/trade = mean net_ret_at_size at 116.08 USD notional (33 % of 500 CAD), as Exp 53;
  * account: 500 CAD, 33 % of realized equity per position, one position per symbol, at most 3
    positions (sizer refusal), gross exposure <= 100 %, one account per period (trades whose RF signal
    time is in the period), CAGR over the period (as Exp 53);
  * "rebond manque" = entry price C / open[s + 1] - 1 (the REF entry price of the same signal), in %;
  * gaps (non-contiguous minutes) inside the confirmation window are counted and reported, not excluded.
Costs: jupiter_build (principal), jupiter_order (reported, no effect).

  python scripts/agents/exp63_rebound.py --date 2026-10-08
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.execution_harness import (VERSION, USD_PER_CAD, ExitRule, apply_costs, load_bars,  # noqa: E402
                                         profit_factor, run_trades, simulate_account)
from scripts.agents.exp53_label50 import ALL_SYMS, HOLD_BARS, P2_START, sequence  # noqa: E402
from scripts.agents.exp61_harness import max_positions_sizer  # noqa: E402
from scripts.agents.exp61_signals import EXP53  # noqa: E402

K_MAIN = 15
VARIANTS = {"REF": None, "C15": 15, "C5": 5, "C30": 30}   # C15 decisional; C5/C30 reported only
COSTS = {"principal_build": "jupiter_build", "stress_order": "jupiter_order"}
INITIAL_CAD, FRACTION = 500.0, 0.33
CACHE = Path("C:/AAProjet/quant_bot_v1/docs/_full_data_cache")
OUT = ROOT / "docs" / "agents" / "results"


# ----------------------------------------------------------------------------- building blocks (tested)
def confirm_bar(h: np.ndarray, c: np.ndarray, s: int, k_max: int) -> int | None:
    """Index of the first bar s+k, 1 <= k <= k_max, whose close is > high[s]; None if none / data end."""
    hi = h[s]
    end = min(s + k_max, len(c) - 1)
    for j in range(s + 1, end + 1):
        if c[j] > hi:
            return j
    return None


def sequence_confirm(sig_idx, h: np.ndarray, c: np.ndarray, k_max: int, hold: int = HOLD_BARS) -> list[tuple]:
    """One position per symbol with a confirmation wait. Returns [(s, cb or None)] for every ACCEPTED
    signal (signals during a wait or a position are dropped). Wait = bars s+1..s+k_max; a signal at s+k_max
    is accepted if unconfirmed; after a confirmed trade (entry cb+1, exit close cb+hold) the next accepted
    signal is >= cb+hold."""
    out, nxt = [], -1
    for s in np.unique(np.asarray(sig_idx, dtype=np.int64)):
        if s < nxt:
            continue
        cb = confirm_bar(h, c, int(s), k_max)
        out.append((int(s), cb))
        nxt = s + k_max if cb is None else cb + hold
    return out


def mechanical(crit: dict) -> str:
    """crit = {period: {"C_net": %, "REF_net": %, "C_cagr": %, "REF_cagr": %, "C_maxdd": %}} for P1, P2."""
    def ok(p):
        return (p["C_net"] > 0 and p["C_net"] - p["REF_net"] >= 0.03 and p["C_cagr"] >= p["REF_cagr"]
                and p["C_maxdd"] >= -35.0)
    if all(ok(p) for p in crit.values()):
        return "PASS"
    if any(p["C_net"] <= 0 for p in crit.values()) or all(p["C_cagr"] < p["REF_cagr"] for p in crit.values()):
        return "REJET"
    return "INCERTAIN"


def build_candidates(sig_times: dict, bars: dict, k_max: int | None) -> pd.DataFrame:
    """sig_times = {sym: int64 ns signal bar open times}; bars = {sym: OHLC DataFrame (UTC index)}.
    Returns one row per ACCEPTED signal: symbol, rf_signal_time, confirmed, delay, signal_time (bar
    handed to the harness: s for REF, cb for C), ref_entry_price (open[s+1]), confirm_gap."""
    rows = []
    for sym, st in sig_times.items():
        b = bars[sym]
        idx = b.index.get_indexer(pd.DatetimeIndex(np.asarray(st, dtype="datetime64[ns]")).tz_localize("UTC"))
        if (idx < 0).any():
            raise ValueError(f"{sym}: {int((idx < 0).sum())} signal times not in the bar cache")
        o, h, c = (b[k].to_numpy(dtype=float) for k in ("open", "high", "close"))
        ts = b.index
        if k_max is None:
            acc = [(int(s), int(s)) for s in sequence(idx, HOLD_BARS)]
        else:
            acc = sequence_confirm(idx, h, c, k_max, HOLD_BARS)
        for s, cb in acc:
            rows.append({"symbol": sym, "rf_signal_time": ts[s], "confirmed": cb is not None,
                         "delay": (cb - s) if (cb is not None and k_max is not None) else (0 if cb is not None else np.nan),
                         "signal_time": ts[cb] if cb is not None else pd.NaT,
                         "ref_entry_price": o[s + 1] if s + 1 < len(o) else np.nan,
                         "confirm_gap": bool(cb is not None and (ts[cb] - ts[s]) != pd.Timedelta(minutes=cb - s))})
    df = pd.DataFrame(rows)
    df["period"] = np.where(df.rf_signal_time < P2_START, "P1", "P2")
    df["side"] = 1
    return df


def simulate_variant(cand: pd.DataFrame, loader, notional: float) -> pd.DataFrame:
    """run_trades on the confirmed candidates (entry next open after the handed bar), metadata merged back."""
    conf = cand[cand.confirmed].reset_index(drop=True)
    sim = run_trades(conf[["symbol", "signal_time", "side"]], ExitRule(max_bars=HOLD_BARS), "jupiter_build",
                     loader, entry_mode="next_open", notional_usd=notional)
    meta = conf[["rf_signal_time", "delay", "ref_entry_price", "period", "confirm_gap"]]
    sim = sim.join(meta, on="cand_id")
    sim["missed_rebound"] = sim.entry_price / sim.ref_entry_price - 1
    return sim


# ----------------------------------------------------------------------------- run
def load_signals() -> dict:
    folds = json.loads((EXP53 / "folds.json").read_text())
    sig = {s: [] for s in ALL_SYMS}
    for k in range(1, len(folds) + 1):
        with open(EXP53 / f"fold_{k:02d}.pkl", "rb") as fh:
            r = pickle.load(fh)
        for s in ALL_SYMS:
            sig[s].append(np.asarray(r["signals"]["REF"][s]))
    return {s: np.unique(np.concatenate(v)) for s, v in sig.items()}, folds


def stats_rows(var, pop, cost, t, cand, p0, p1) -> list[dict]:
    out = []
    ok = t[(t.status == "ok") & (t.period == pop)]
    cp = cand[cand.period == pop]
    for sym in list(ALL_SYMS) + ["POOLED"]:
        x = ok if sym == "POOLED" else ok[ok.symbol == sym]
        cc = cp if sym == "POOLED" else cp[cp.symbol == sym]
        r = x.net_ret_at_size
        conf = cc[cc.confirmed]
        out.append({"variant": var, "period": pop, "cost": cost, "symbol": sym, "n": len(x),
                    "mean_gross_pct": 100 * x.gross_ret.mean(), "mean_net_pct_at_size": 100 * r.mean(),
                    "pf_at_size": profit_factor(r), "win_rate": float((r > 0).mean()) if len(x) else np.nan,
                    "t_stat": float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if len(r) > 1 else np.nan,
                    "trades_per_day": len(x) / ((p1 - p0).total_seconds() / 86400),
                    "accepted_signals": len(cc), "confirmed": len(conf),
                    "confirm_rate": len(conf) / len(cc) if len(cc) else np.nan,
                    "median_delay_bars": float(conf.delay.median()) if len(conf) else np.nan,
                    "mean_delay_bars": float(conf.delay.mean()) if len(conf) else np.nan,
                    "missed_rebound_mean_pct": 100 * x.missed_rebound.mean(),
                    "missed_rebound_median_pct": 100 * x.missed_rebound.median(),
                    "confirm_gap_windows": int(conf.confirm_gap.sum()),
                    "n_not_ok": int(((t.period == pop) & (t.status != "ok") &
                                     ((t.symbol == sym) if sym != "POOLED" else True)).sum())})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-10-08")
    ap.add_argument("--out-dir", default=str(OUT))
    a = ap.parse_args(argv)
    out_dir = Path(a.out_dir)
    sig, folds = load_signals()
    bars = {s: load_bars(s, CACHE) for s in ALL_SYMS}
    loader = bars.__getitem__
    notional = INITIAL_CAD * USD_PER_CAD.value * FRACTION
    test_start, end = pd.Timestamp(folds[0][1]), pd.Timestamp(folds[-1][2])
    periods = {"P1": (test_start, P2_START), "P2": (P2_START, end)}
    pt, accts, status = [], [], []
    for var, k in VARIANTS.items():
        cand = build_candidates(sig, bars, k)
        sim = simulate_variant(cand, loader, notional)
        status.append(sim.groupby(["period", "symbol", "status"]).size().rename("n").reset_index().assign(variant=var))
        print(f"{var}: accepted {len(cand)}, confirmed {int(cand.confirmed.sum())}, simulated {len(sim)}", flush=True)
        for cost, plat in COSTS.items():
            t = apply_costs(sim, plat, notional_usd=notional)
            for pop, (p0, p1) in periods.items():
                pt += stats_rows(var, pop, cost, t, cand, p0, p1)
                tt = t.copy()
                tt.loc[(tt.period != pop) & (tt.status == "ok"), "status"] = "other_period"
                acc = simulate_account(tt, plat, INITIAL_CAD, USD_PER_CAD.value, position_fraction=FRACTION,
                                       max_gross_exposure=1.0, one_position_per_symbol=True, period=(p0, p1),
                                       sizer=max_positions_sizer(3))
                accts.append({"variant": var, "period": pop, "cost": cost, "platform": plat,
                              "period_start": str(p0), "period_end": str(p1),
                              **{kk: v for kk, v in acc.items() if kk not in ("ledger", "equity_minute", "skips")},
                              **{f"skip_{kk}": v for kk, v in acc.get("skips", {}).items()}})
    pt, ac, st = pd.DataFrame(pt), pd.DataFrame(accts), pd.concat(status)
    out_dir.mkdir(parents=True, exist_ok=True)
    pt.to_csv(out_dir / f"Exp-63_{a.date}_per_trade.csv", index=False)
    ac.to_csv(out_dir / f"Exp-63_{a.date}_accounts.csv", index=False)
    st.to_csv(out_dir / f"Exp-63_{a.date}_status.csv", index=False)

    def pick(df, var, pop, col, cost="principal_build", sym=None):
        q = (df.variant == var) & (df.period == pop) & (df.cost == cost)
        if sym is not None:
            q &= df.symbol == sym
        return float(df.loc[q, col].iloc[0])

    crit, reported = {}, {}
    for pop in periods:
        crit[pop] = {"C_net": pick(pt, "C15", pop, "mean_net_pct_at_size", sym="POOLED"),
                     "REF_net": pick(pt, "REF", pop, "mean_net_pct_at_size", sym="POOLED"),
                     "C_cagr": pick(ac, "C15", pop, "cagr_cad_pct"), "REF_cagr": pick(ac, "REF", pop, "cagr_cad_pct"),
                     "C_maxdd": pick(ac, "C15", pop, "max_dd_pct"), "REF_maxdd": pick(ac, "REF", pop, "max_dd_pct")}
        c = crit[pop]
        c.update({"delta_net_pct_points": c["C_net"] - c["REF_net"],
                  "a_C_net_gt_0": c["C_net"] > 0, "b_delta_ge_0p03": c["C_net"] - c["REF_net"] >= 0.03,
                  "c_C_cagr_ge_REF": c["C_cagr"] >= c["REF_cagr"], "d_C_maxdd_ge_m35": c["C_maxdd"] >= -35.0,
                  "C_n": int(pick(pt, "C15", pop, "n", sym="POOLED")), "REF_n": int(pick(pt, "REF", pop, "n", sym="POOLED"))})
    mech = mechanical({p: {k: crit[p][k] for k in ("C_net", "REF_net", "C_cagr", "REF_cagr", "C_maxdd")} for p in crit})
    out = {"harness_version": VERSION, "notional_usd_at_33pct": notional, "usd_per_cad": USD_PER_CAD.value,
           "periods": {k: [str(x), str(y)] for k, (x, y) in periods.items()}, "decisional_variant": "C15",
           "criteria": crit, "mechanical_reading": mech}
    (out_dir / f"Exp-63_{a.date}_criteria.json").write_text(json.dumps(out, indent=2, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(pt.round(4).to_string())
    print(ac[["variant", "period", "cost", "n_trades", "total_return_cad_pct", "cagr_cad_pct", "max_dd_pct",
              "worst_day_pct", "worst_day_date", "pf_usd", "skip_symbol_busy", "skip_exposure_cap"]].round(3).to_string())
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
