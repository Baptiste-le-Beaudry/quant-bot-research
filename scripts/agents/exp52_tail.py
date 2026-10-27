"""Exp 52 (A-JUP-TAIL-001) -- executed to the letter of docs/agents/hypotheses/Exp-52.md (commit eacf9f8).

UNCAPPED = deployed rule, identical to Exp 57 (SOL+BTC+ETH, time exit 50 bars without stop, next-open
entry, 33 % of realized equity per position, one position per symbol, exposure <= 100 %, cost
jupiter_build, 500 CAD).
CAPPED   = same entries/fills/costs, sized INSIDE the account replay (realized equity at entry):
  * notional_i = min(33 % * E, B / q_i) with B = 2 % * E, i.e. E * min(0.33, 0.02 / q_i)
    q_i = Q995_TRAIN(adverse move over 50 bars) * rv30(signal) / median_TRAIN(rv30)
    TRAIN: P1 -> bars before 2021-11-01 ; P2 -> all of P1 (2021-11-01 -> 2025-03-28, earliest HOLDOUT start)
  * burst: an open position of ANOTHER symbol entered <= 60 min before this entry -> size 0
  * floor: no position < 20 USD
SOL-only instance: size rule + floor only (reported, no effect on the verdict).

Definitions fixed here (prereg leaves them implicit; reported in the result file):
  adverse move over 50 bars for a signal on bar k = max(0, 1 - min(low[k+1..k+50]) / open[k+1])
  (the same 50 evaluated bars as the harness, entry at the next open), every minute of TRAIN with a
  contiguous window is a sample; rv30 = std of 1-min close pct_change over 30 bars ending at the
  signal bar (quant_bot/features/basics.realized_vol).
Harness v1.2.0 (sizer hook). Bars read-only from --cache-dir. Outputs under docs/agents/results/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.execution_harness import (VERSION, USD_PER_CAD, ExitRule, load_bars,  # noqa: E402
                                         run_trades, simulate_account)

SYMS = ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
POPS = {"P1": ROOT / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv",
        "P2": ROOT / "docs" / "experiment50_trades.csv"}
TRAIN = {"P1": (None, "2021-11-01"), "P2": ("2021-11-01", "2025-03-28")}
RULE = ExitRule(max_bars=50)
INITIAL_CAD, FRACTION, PLATFORM = 500.0, 0.33, "jupiter_build"
B_FRAC, QUANTILE, HOLD, BURST_MIN, FLOOR_USD = 0.02, 0.995, 50, 60, 20.0
OUT = ROOT / "docs" / "agents" / "results"


# ---------------------------------------------------------------- tail estimate
def adverse_move(bars: pd.DataFrame, hold: int = HOLD) -> pd.Series:
    """Adverse move of a long entered at open[k+1] over bars k+1..k+hold, indexed by signal bar k.
    NaN when the window is not `hold` contiguous minutes or runs past the data."""
    o = bars["open"].to_numpy(float)
    low = pd.Series(bars["low"].to_numpy(float))
    win_min = low.rolling(hold, min_periods=hold).min().shift(-hold).to_numpy()  # min low[k+1..k+hold]
    entry = np.r_[o[1:], np.nan]
    mae = np.maximum(0.0, 1.0 - win_min / entry)
    ts = np.round((bars.index - bars.index[0]) / pd.Timedelta(minutes=1)).astype(np.int64)  # minutes
    n = len(ts)
    contiguous = np.zeros(n, bool)
    if n > hold:
        contiguous[: n - hold] = (ts[hold:] - ts[: n - hold]) == hold  # k .. k+hold contiguous
    mae[~contiguous] = np.nan
    return pd.Series(mae, index=bars.index)


def rv30(bars: pd.DataFrame) -> pd.Series:
    return bars["close"].pct_change().rolling(30).std()


def _utc(x) -> pd.Timestamp:
    x = pd.Timestamp(x)
    return x.tz_localize("UTC") if x.tz is None else x.tz_convert("UTC")


def fit_tail(mae: pd.Series, vol: pd.Series, start, end, hold: int = HOLD) -> dict:
    """Q99.5 of the adverse move and median rv30 on [start, end); a sample is used only if its whole
    window (signal bar .. signal + hold) ends before `end`."""
    idx = mae.index
    m = np.ones(len(idx), bool)
    if start is not None:
        m &= idx >= _utc(start)
    if end is not None:
        m &= idx + pd.Timedelta(minutes=hold) < _utc(end)
    x, v = mae[m].dropna(), vol[m].dropna()
    return {"q995": float(np.quantile(x.to_numpy(), QUANTILE)), "rv30_median": float(v.median()),
            "n_mae": int(len(x)), "n_rv": int(len(v)),
            "first": str(x.index.min()) if len(x) else None, "last": str(x.index.max()) if len(x) else None}


def tail_q(fit: dict, rv_signal: float) -> float:
    return fit["q995"] * rv_signal / fit["rv30_median"]


# ---------------------------------------------------------------- sizing rule
def make_capped_sizer(fits: dict, rv_at_signal: dict, b_frac=B_FRAC, cap_frac=FRACTION,
                      burst_minutes=BURST_MIN, floor_usd=FLOOR_USD, burst=True, record=None):
    """sizer for simulate_account (harness v1.2). fits[symbol] -> fit_tail dict;
    rv_at_signal[(symbol, signal_time)] -> rv30 at the signal bar."""
    win = pd.Timedelta(minutes=burst_minutes)

    def sizer(t, equity, open_pos, base_notional):
        if burst:
            for p in open_pos:
                if p["symbol"] != t.symbol and pd.Timedelta(0) <= t.entry_time - p["entry_time"] <= win:
                    return 0.0, "burst"
        rv = rv_at_signal.get((t.symbol, pd.Timestamp(t.signal_time)), np.nan)
        if not np.isfinite(rv) or rv <= 0:
            return 0.0, "rv_missing"
        q = tail_q(fits[t.symbol], rv)
        frac = min(cap_frac, b_frac / q)
        notional = frac * equity
        if record is not None:
            record.append({"symbol": t.symbol, "signal_time": t.signal_time, "rv30": rv, "q": q,
                           "frac": frac, "equity": equity})
        if notional < floor_usd:
            return 0.0, "floor"
        return notional, ("tail_cap" if frac < cap_frac else "full")

    return sizer


# ---------------------------------------------------------------- metrics
def summarize_account(a: dict, n_candidates_ok: int) -> dict:
    led = a["ledger"]
    tags = led.size_tag.value_counts().to_dict() if len(led) else {}
    return {"n_trades": a["n_trades"], "n_candidates_ok": n_candidates_ok,
            "cagr_cad_pct": a["cagr_cad_pct"], "total_return_cad_pct": a["total_return_cad_pct"],
            "max_dd_pct": a["max_dd_pct"], "ret_over_maxdd": a["cagr_cad_pct"] / abs(a["max_dd_pct"]),
            "worst_day_pct": a["worst_day_pct"], "worst_day_date": a["worst_day_date"],
            "worst_intraday_pct": a["worst_intraday_pct"], "worst_week_pct": a["worst_week_pct"],
            "worst_week_end": a["worst_week_end"],
            "mean_net_per_kept_trade_pct": 100 * float(led.ret_on_notional.mean()),
            "mean_pnl_usd": float(led.pnl_usd.mean()), "median_notional_usd": float(led.notional_usd.median()),
            "years": a["years"], **{f"skip_{k}": v for k, v in a["skips"].items()},
            **{f"taken_{k}": v for k, v in tags.items()}}


def criteria(unc: dict, cap: dict) -> dict:
    return {"worst_day_capped_pct": cap["worst_day_pct"],
            "c1_worst_day_ge_-10": cap["worst_day_pct"] >= -10.0,
            "net_kept_capped_pct": cap["mean_net_per_kept_trade_pct"],
            "net_kept_uncapped_pct": unc["mean_net_per_kept_trade_pct"],
            "c2_net_kept_ge_80pct": cap["mean_net_per_kept_trade_pct"] >= 0.8 * unc["mean_net_per_kept_trade_pct"],
            "cagr_capped_pct": cap["cagr_cad_pct"], "cagr_uncapped_pct": unc["cagr_cad_pct"],
            "c3_cagr_ge_50pct": cap["cagr_cad_pct"] >= 0.5 * unc["cagr_cad_pct"],
            "ratio_capped": cap["ret_over_maxdd"], "ratio_uncapped": unc["ret_over_maxdd"],
            "c4_ratio_improves": cap["ret_over_maxdd"] > unc["ret_over_maxdd"],
            "reject_worst_day_lt_-15": cap["worst_day_pct"] < -15.0}


def mechanical_verdict(crit: dict) -> dict:
    keys = ("c1_worst_day_ge_-10", "c2_net_kept_ge_80pct", "c3_cagr_ge_50pct", "c4_ratio_improves")
    all_pass = all(all(bool(c[k]) for k in keys) for c in crit.values())
    rej_day = any(bool(c["reject_worst_day_lt_-15"]) for c in crit.values())
    # "ne s'ameliore pas dans les deux periodes": strict reading = not improved in at least one period;
    # lenient reading = improved in neither. Both reported.
    rej_ratio_strict = not all(bool(c["c4_ratio_improves"]) for c in crit.values())
    rej_ratio_lenient = not any(bool(c["c4_ratio_improves"]) for c in crit.values())
    def verdict(rej_ratio):
        return "PASS" if all_pass else ("REJET" if (rej_day or rej_ratio) else "INCERTAIN")
    return {"verdict_strict_reading": verdict(rej_ratio_strict),
            "verdict_lenient_reading": verdict(rej_ratio_lenient),
            "reject_by_worst_day": rej_day, "reject_by_ratio_strict": rej_ratio_strict,
            "reject_by_ratio_lenient": rej_ratio_lenient}


def candidates(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["entry_time"])
    d = d[d.symbol.isin(SYMS)]
    return pd.DataFrame({"symbol": d.symbol.values, "signal_time": d.entry_time.values, "side": 1})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--date", default="2026-10-07")
    args = ap.parse_args(argv)
    loader = lambda s: load_bars(s, args.cache_dir)  # noqa: E731
    cands = {pop: candidates(p) for pop, p in POPS.items()}
    for c in cands.values():
        c["signal_time"] = pd.to_datetime(c.signal_time, utc=True)

    # 1) tail fits + rv30 at every signal, one symbol at a time (memory)
    fits = {pop: {} for pop in POPS}
    rv_sig, fit_rows, q_rows = {}, [], []
    for sym in SYMS:
        bars = loader(sym)
        mae, vol = adverse_move(bars), rv30(bars)
        for pop, (s, e) in TRAIN.items():
            f = fit_tail(mae, vol, s, e)
            fits[pop][sym] = f
            fit_rows.append({"population": pop, "symbol": sym, "train_start": s, "train_end": e, **f})
        for pop, c in cands.items():
            st = c.loc[c.symbol == sym, "signal_time"]
            v = vol.reindex(st)
            for t0, val in zip(st, v.to_numpy()):
                rv_sig[(sym, pd.Timestamp(t0))] = float(val)
                q_rows.append({"population": pop, "symbol": sym, "signal_time": t0, "rv30": float(val),
                               "q": tail_q(fits[pop][sym], float(val)),
                               "frac_capped": min(FRACTION, B_FRAC / tail_q(fits[pop][sym], float(val)))})
        del bars, mae, vol
        print(sym, "fitted", flush=True)

    rows, crit, ledgers = [], {}, []
    for pop in POPS:
        sim = run_trades(cands[pop], RULE, PLATFORM, loader, entry_mode="next_open")
        ok_all = sim[sim.status == "ok"]
        period = (ok_all.signal_time.min(), ok_all.exit_time.max())
        res = {}
        for acct, syms in (("SOL_BTC_ETH", SYMS), ("SOL_only", ["SOLUSDT"])):
            tt = sim.copy()
            tt.loc[~tt.symbol.isin(syms) & (tt.status == "ok"), "status"] = "excluded_universe"
            n_ok = int((tt.status == "ok").sum())
            for variant in ("UNCAPPED", "CAPPED"):
                sizer = None
                if variant == "CAPPED":
                    sizer = make_capped_sizer(fits[pop], rv_sig, burst=(acct == "SOL_BTC_ETH"))
                a = simulate_account(tt, PLATFORM, INITIAL_CAD, USD_PER_CAD.value, position_fraction=FRACTION,
                                     max_gross_exposure=1.0, one_position_per_symbol=True, period=period,
                                     sizer=sizer)
                s = summarize_account(a, n_ok)
                res[(acct, variant)] = s
                rows.append({"population": pop, "account": acct, "variant": variant,
                             "period_start": str(period[0]), "period_end": str(period[1]), **s})
                ledgers.append(a["ledger"].assign(population=pop, account=acct, variant=variant))
        crit[pop] = {k: (bool(v) if isinstance(v, (bool, np.bool_)) else v)
                     for k, v in criteria(res[("SOL_BTC_ETH", "UNCAPPED")], res[("SOL_BTC_ETH", "CAPPED")]).items()}
        crit[pop + "_SOL_only_no_effect"] = {
            k: (bool(v) if isinstance(v, (bool, np.bool_)) else v)
            for k, v in criteria(res[("SOL_only", "UNCAPPED")], res[("SOL_only", "CAPPED")]).items()}
        print(pop, "done", flush=True)

    ac = pd.DataFrame(rows)
    # reproduction check of UNCAPPED against Exp 57 (principal cost)
    e57 = pd.read_csv(OUT / "Exp-57_2026-10-07_accounts.csv")
    e57 = e57[e57.cost == "principal_build"].set_index(["population", "account"])
    repro = {}
    for _, r in ac[ac.variant == "UNCAPPED"].iterrows():
        ref = e57.loc[(r.population, r.account)]
        repro[f"{r.population}_{r.account}"] = {
            "n_trades": [int(r.n_trades), int(ref.n_trades)],
            "cagr": [float(r.cagr_cad_pct), float(ref.cagr_cad_pct)],
            "maxdd": [float(r.max_dd_pct), float(ref.max_dd_pct)],
            "worst_day": [float(r.worst_day_pct), float(ref.worst_day_pct)],
            "identical": bool(int(r.n_trades) == int(ref.n_trades)
                              and abs(r.cagr_cad_pct - ref.cagr_cad_pct) < 1e-9
                              and abs(r.max_dd_pct - ref.max_dd_pct) < 1e-9)}
    main_crit = {p: crit[p] for p in POPS}
    out = {"harness_version": VERSION, "platform": PLATFORM, "usd_per_cad": USD_PER_CAD.value,
           "params": {"B": B_FRAC, "quantile": QUANTILE, "hold_bars": HOLD, "burst_minutes": BURST_MIN,
                      "floor_usd": FLOOR_USD, "cap_fraction": FRACTION, "train": TRAIN},
           "fits": fit_rows, "criteria": crit, "mechanical": mechanical_verdict(main_crit),
           "uncapped_reproduces_exp57": repro}
    OUT.mkdir(parents=True, exist_ok=True)
    ac.to_csv(OUT / f"Exp-52_{args.date}_accounts.csv", index=False)
    pd.DataFrame(q_rows).to_csv(OUT / f"Exp-52_{args.date}_signal_sizes.csv", index=False)
    pd.concat(ledgers).to_csv(OUT / f"Exp-52_{args.date}_ledgers.csv", index=False)
    (OUT / f"Exp-52_{args.date}_criteria.json").write_text(json.dumps(out, indent=2, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)
    print(pd.DataFrame(fit_rows).to_string())
    print(ac.round(4).T.to_string())
    print(json.dumps({"criteria": crit, "mechanical": out["mechanical"], "repro": repro}, indent=2, default=str))


if __name__ == "__main__":
    main()
