"""Exp 61 (A-JUP-SOLTOKENS-001) -- step-0 freeze, execution and account, to the letter of
docs/agents/hypotheses/Exp-61.md (commit 5dc8b95).

Stages
  step0   : reads the /build quote database (scripts/agents/exp61_quote_collector.py), checks the
            >= 20 quotes over >= 24 h rule per token, applies the exclusion (median round trip > 0.10 %)
            and FREEZES it in docs/agents/results/Exp-61_<date>_step0.json. Must run before ``harness``.
  harness : harness v1.2 (quant_bot/execution_harness), entry next open, time exit 50 bars without
            stop, one position per symbol (sequenced as Exp 53), cost = measured median round trip
            (per side = median / 2) + 0.01 USD per swap (jupiter_build fixed fee), notional 116.08 USD
            (33 % of 500 CAD). SOL/BTC/ETH: Exp 53 REF signals, jupiter_build costs (0.02 % RT + 0.01 USD).

Points fixed HERE, before any harness computation (not fixed by the preregistration):
  * net/trade = mean net_ret_at_size (116.08 USD notional, fixed fees included), as Exp 53/57.
  * token period = [TEST start of its first eligible fold, 2026-08-17 00:01 UTC) (Exp 53 last fold end);
    the two chronological halves split that period at its time midpoint (by signal time).
  * ">= 100 trades" counts the token's sequenced trades with harness status ok over the whole period.
  * A measured median below 0 is floored at 0 (never a negative cost).
  * Account: 500 CAD, 33 % of realized equity per position, one position per symbol, at most 3
    simultaneous positions (sizer refusal) and gross exposure <= 100 %; common period = from the
    latest first-eligible TEST start among the retained tokens to 2026-08-17 00:01; both accounts
    (SOL+BTC+ETH and SOL+BTC+ETH+retained) on that period, trades with signal time inside it.
  * If no token is retained the verdict is REJET; the account "SOL+BTC+ETH+all non-excluded tokens" is
    still reported (no effect), on its own common period.
  * Stress x3 (reported): token AND SOL/BTC/ETH proportional costs x3 and fixed fee x3.
  * No-cap account (reported): no position-count cap, exposure cap 1e9.
  * RAYUSDT_2021 (delisted RAY perpetual, 2021-2022): reported only, RAY's measured cost.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.execution_harness import (VERSION, USD_PER_CAD, ExitRule, Sourced, apply_costs,  # noqa: E402
                                         get_platform, load_bars, profit_factor, run_trades, simulate_account)
from scripts.agents.exp53_label50 import HOLD_BARS, sequence  # noqa: E402
from scripts.agents import exp61_quote_collector as qc  # noqa: E402
from scripts.agents.exp61_signals import DATA, DIAG, EXP53, TOKENS, token_bars  # noqa: E402

BASE_SYMS = ("SOLUSDT", "BTCUSDT", "ETHUSDT")
QUOTE_SYM = {"JUPUSDT": "JUPUSDT", "JTOUSDT": "JTOUSDT", "PYTHUSDT": "PYTHUSDT", "RAYSOLUSDT": "RAYUSDT",
             "WIFUSDT": "WIFUSDT", "1000BONKUSDT": "1000BONKUSDT", "RAYUSDT_2021": "RAYUSDT"}
INITIAL_CAD, FRACTION, MAX_POS = 500.0, 0.33, 3
END = pd.Timestamp("2026-08-17 00:01", tz="UTC")
MIN_QUOTES, MIN_SPAN_H = 20, 24.0
OUT = ROOT / "docs" / "agents" / "results"
CACHE = Path("C:/AAProjet/quant_bot_v1/docs/_full_data_cache")


# ----------------------------------------------------------------------------- step 0
def stage_step0(db_path: Path, out: Path) -> dict:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    s = qc.summarize(db)
    cycles = db.execute("SELECT MIN(cycle_ts), MAX(cycle_ts), COUNT(DISTINCT cycle_ts) FROM quotes").fetchone()
    errors = db.execute("SELECT symbol, error, COUNT(*) FROM quotes WHERE error IS NOT NULL "
                        "GROUP BY symbol, error").fetchall()
    rows = db.execute("SELECT * FROM quotes").fetchall()
    db.close()
    complete = all(v["n_ok"] >= MIN_QUOTES and v["span_hours"] >= MIN_SPAN_H for v in s.values())
    res = {"endpoint": "/swap/v2/build (keyless api.jup.ag, placeholder taker, nothing signed)",
           "size_usd": qc.SIZE_USD, "exclusion_threshold_rt": qc.EXCLUSION_THRESHOLD,
           "first_cycle_utc": str(pd.Timestamp(cycles[0], unit="ms", tz="UTC")),
           "last_cycle_utc": str(pd.Timestamp(cycles[1], unit="ms", tz="UTC")), "n_cycles": cycles[2],
           "rule_met_ge20_quotes_ge24h": complete, "n_quote_rows": len(rows),
           "errors": [list(e) for e in errors], "tokens": s,
           "excluded": [k for k, v in s.items() if v["excluded"]],
           "retained_for_backtest": [k for k, v in s.items() if not v["excluded"]]}
    out.write_text(json.dumps(res, indent=2, default=str))
    return res


# ----------------------------------------------------------------------------- building blocks (tested)
def make_platform(costs_rt: dict, mult: float = 1.0, name: str = "exp61_jupiter_build"):
    """jupiter_build (SOL/BTC/ETH 0.01 %/side + 0.01 USD) extended with measured per-token round trips
    (half per side, floored at 0); ``mult`` scales every proportional cost and the fixed fee."""
    base = get_platform("jupiter_build")
    hs = {s: Sourced(base.half_spread_pct.value * mult, base.half_spread_pct.source + f" x{mult}", False)
          for s in BASE_SYMS}
    for sym, rt in costs_rt.items():
        hs[sym] = Sourced(max(rt, 0.0) / 2 * mult, f"Exp 61 step 0 median /build round trip {rt:.6f} / 2"
                          f" x{mult}", True)
    return dataclasses.replace(
        base, name=name, symbols=frozenset(hs), per_symbol_half_spread_pct=hs,
        fixed_fee_usd_per_order=Sourced(base.fixed_fee_usd_per_order.value * mult,
                                        base.fixed_fee_usd_per_order.source + f" x{mult}", False))


def halves(period_start: pd.Timestamp, period_end: pd.Timestamp) -> pd.Timestamp:
    return period_start + (period_end - period_start) / 2


def max_positions_sizer(max_pos: int = MAX_POS):
    def sizer(trade, equity, open_positions, base_notional):
        if len(open_positions) >= max_pos:
            return 0.0, "max_positions"
        return base_notional, "fraction"
    return sizer


def token_verdict(per_token: dict, retained_step0: list, min_trades: int = 100) -> dict:
    """per_token = {key: {"n": int, "net_h1": float, "net_h2": float}} (principal cost, fractions)."""
    out = {}
    for k, v in per_token.items():
        ok = (k in retained_step0 and v["n"] >= min_trades and v["net_h1"] > 0 and v["net_h2"] > 0)
        out[k] = bool(ok)
    return out


def mechanical(retained: list, cagr_with: float | None, cagr_base: float | None, dd_with: float | None) -> str:
    if len(retained) == 0:
        return "REJET"
    if len(retained) >= 2 and cagr_with > cagr_base and dd_with >= -35.0:
        return "PASS"
    return "INCERTAIN"


# ----------------------------------------------------------------------------- harness
def loader_factory():
    cache = {}

    def load(sym):
        if sym not in cache:
            if sym in BASE_SYMS:
                cache[sym] = load_bars(sym, CACHE)
            else:
                df = token_bars(sym, DATA)
                cache[sym] = df[["open", "high", "low", "close"]]
        return cache[sym]
    return load


def candidates(work: Path) -> tuple[pd.DataFrame, dict]:
    elig = json.loads((work / "eligibility.json").read_text())
    folds = json.loads((EXP53 / "folds.json").read_text())
    rows, meta = [], {}
    # base symbols: Exp 53 REF signals, all folds
    for s in BASE_SYMS:
        sig = []
        for k in range(1, len(folds) + 1):
            with open(EXP53 / f"fold_{k:02d}.pkl", "rb") as fh:
                sig.append(np.asarray(pickle.load(fh)["signals"]["REF"][s]))
        times = np.load(EXP53 / f"times_{s}.npy")
        sig = np.unique(np.concatenate(sig))
        idx = np.searchsorted(times, sig)
        assert (times[idx] == sig).all()
        seq = sequence(idx, HOLD_BARS)
        rows.append(pd.DataFrame({"symbol": s, "signal_time": pd.DatetimeIndex(times[seq]).tz_localize("UTC")}))
        meta[s] = {"raw_signal_bars": int(len(sig)), "sequenced": int(len(seq))}
    for key in list(TOKENS) + list(DIAG):
        e = elig[key]
        if not e["first_fold"]:
            meta[key] = {"eligible": False}
            continue
        sig, per_fold = [], {}
        for k in range(e["first_fold"], e["last_fold"] + 1):
            with open(work / f"fold_{k:02d}.pkl", "rb") as fh:
                r = pickle.load(fh)
            sig.append(np.asarray(r["signals"][key]))
            per_fold[k] = int(len(r["signals"][key]))
        times = np.load(work / f"times_{key}.npy")
        sig = np.unique(np.concatenate(sig))
        idx = np.searchsorted(times, sig)
        assert (times[idx] == sig).all()
        seq = sequence(idx, HOLD_BARS)
        rows.append(pd.DataFrame({"symbol": key, "signal_time": pd.DatetimeIndex(times[seq]).tz_localize("UTC")}))
        p0 = pd.Timestamp(e["first_test_start"])
        p1 = END if key != "RAYUSDT_2021" else pd.Timestamp(e["last_bar"])
        meta[key] = {"eligible": True, "first_fold": e["first_fold"], "period_start": str(p0),
                     "period_end": str(p1), "midpoint": str(halves(p0, p1)), "raw_signal_bars": int(len(sig)),
                     "sequenced": int(len(seq)), "signal_bars_per_fold": per_fold}
    cand = pd.concat(rows, ignore_index=True)
    cand["side"] = 1
    return cand, meta


def per_trade_table(t: pd.DataFrame, meta: dict, cost_label: str) -> list[dict]:
    out = []
    for key in list(BASE_SYMS) + list(TOKENS) + list(DIAG):
        x = t[(t.symbol == key) & (t.status == "ok")]
        m = meta.get(key, {})
        if key in BASE_SYMS:
            p0 = pd.Timestamp(meta["_common_start"]) if "_common_start" in meta else x.signal_time.min()
            x = x[(x.signal_time >= p0) & (x.signal_time < END)]
            mid = halves(p0, END)
        elif not m.get("eligible"):
            continue
        else:
            mid = pd.Timestamp(m["midpoint"])
        r = x.net_ret_at_size
        h1, h2 = x[x.signal_time < mid], x[x.signal_time >= mid]
        half_n = len(x) // 2
        xs = x.sort_values("signal_time")
        out.append({"cost": cost_label, "symbol": key, "n": len(x), "n_h1": len(h1), "n_h2": len(h2),
                    "cost_rt_pct": 100 * float(x.cost_rt.iloc[0]) if len(x) else np.nan,
                    "mean_gross_pct": 100 * x.gross_ret.mean(), "mean_net_pct": 100 * r.mean(),
                    "net_h1_pct": 100 * h1.net_ret_at_size.mean(), "net_h2_pct": 100 * h2.net_ret_at_size.mean(),
                    "net_h1_by_count_pct": 100 * xs.net_ret_at_size.iloc[:half_n].mean(),
                    "net_h2_by_count_pct": 100 * xs.net_ret_at_size.iloc[half_n:].mean(),
                    "pf": profit_factor(r), "pf_h1": profit_factor(h1.net_ret_at_size),
                    "pf_h2": profit_factor(h2.net_ret_at_size),
                    "win_rate": float((r > 0).mean()) if len(x) else np.nan,
                    "t_stat": float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if len(r) > 1 else np.nan,
                    "first_signal": str(x.signal_time.min()), "last_signal": str(x.signal_time.max()),
                    "midpoint": str(mid)})
    return out


def account(t: pd.DataFrame, plat, syms: list, p0, p1, capped: bool) -> dict:
    tt = t.copy()
    keep = tt.symbol.isin(syms) & (tt.signal_time >= p0) & (tt.signal_time < p1)
    tt.loc[~keep & (tt.status == "ok"), "status"] = "outside_account"
    a = simulate_account(tt, plat, INITIAL_CAD, USD_PER_CAD.value, position_fraction=FRACTION,
                         max_gross_exposure=1.0 if capped else 1e9, one_position_per_symbol=True,
                         period=(p0, p1), sizer=max_positions_sizer() if capped else None)
    led = a.get("ledger", pd.DataFrame(columns=["symbol"]))
    return {**{k: v for k, v in a.items() if k not in ("ledger", "equity_minute", "skips")},
            **{f"skip_{k}": v for k, v in a.get("skips", {}).items()},
            **{f"n_taken_{s}": int((led.symbol == s).sum()) for s in syms}}


def stage_harness(work: Path, step0_path: Path, date: str) -> dict:
    step0 = json.loads(step0_path.read_text())
    if not step0["rule_met_ge20_quotes_ge24h"]:
        raise SystemExit("STOP: step 0 incomplete (< 20 quotes or < 24 h for a token)")
    costs = {k: step0["tokens"][QUOTE_SYM[k]]["median_cost"] for k in list(TOKENS) + list(DIAG)}
    kept0 = [k for k in TOKENS if QUOTE_SYM[k] in step0["retained_for_backtest"]]
    notional = INITIAL_CAD * USD_PER_CAD.value * FRACTION
    cand, meta = candidates(work)
    plats = {"principal": make_platform(costs), "stress_x3": make_platform(costs, 3.0, "exp61_build_x3")}
    sim = run_trades(cand, ExitRule(max_bars=HOLD_BARS), plats["principal"], loader_factory(),
                     entry_mode="next_open", notional_usd=notional)
    status = sim.groupby(["symbol", "status"]).size().rename("n").reset_index()
    priced = {c: (sim if c == "principal" else apply_costs(sim, p, notional_usd=notional))
              for c, p in plats.items()}
    nonexcl = [k for k in kept0 if meta[k].get("eligible")]
    if nonexcl:  # base-symbol rows of the per-trade table: period of the all-non-excluded account
        meta["_common_start"] = str(max(pd.Timestamp(meta[k]["period_start"]) for k in nonexcl))
    pt = []
    for c, t in priced.items():
        pt += per_trade_table(t, meta, c)
    pt = pd.DataFrame(pt)
    pp = pt[pt.cost == "principal"].set_index("symbol")
    per_tok = {k: {"n": int(pp.loc[k, "n"]), "net_h1": float(pp.loc[k, "net_h1_pct"]),
                   "net_h2": float(pp.loc[k, "net_h2_pct"])} for k in TOKENS if k in pp.index}
    ver = token_verdict(per_tok, kept0)
    retained = [k for k, v in ver.items() if v]

    accts = []

    def run_pair(tokens: list, label: str):
        if not tokens:
            return None
        p0 = max(pd.Timestamp(meta[k]["period_start"]) for k in tokens)
        res = {}
        for c, t in priced.items():
            for capped in (True, False):
                for acct, syms in (("SOL_BTC_ETH", list(BASE_SYMS)), (f"SOL_BTC_ETH+{label}", list(BASE_SYMS) + tokens)):
                    a = account(t, plats[c], syms, p0, END, capped)
                    row = {"set": label, "cost": c, "cap3": capped, "account": acct, "period_start": str(p0),
                           "period_end": str(END), **a}
                    accts.append(row)
                    res[(c, capped, acct)] = row
        return res

    pair = run_pair(retained, "retained")
    run_pair(nonexcl, "all_non_excluded")
    if pair:
        w = pair[("principal", True, "SOL_BTC_ETH+retained")]
        b = pair[("principal", True, "SOL_BTC_ETH")]
        mech = mechanical(retained, w["cagr_cad_pct"], b["cagr_cad_pct"], w["max_dd_pct"])
        crit_acct = {"cagr_with_pct": w["cagr_cad_pct"], "cagr_base_pct": b["cagr_cad_pct"],
                     "maxdd_with_pct": w["max_dd_pct"], "maxdd_base_pct": b["max_dd_pct"],
                     "period": [w["period_start"], w["period_end"]]}
    else:
        mech, crit_acct = mechanical(retained, None, None, None), None
    ac = pd.DataFrame(accts)
    OUT.mkdir(parents=True, exist_ok=True)
    pt.to_csv(OUT / f"Exp-61_{date}_per_trade.csv", index=False)
    ac.to_csv(OUT / f"Exp-61_{date}_accounts.csv", index=False)
    status.to_csv(OUT / f"Exp-61_{date}_status.csv", index=False)
    out = {"harness_version": VERSION, "notional_usd_at_33pct": notional, "usd_per_cad": USD_PER_CAD.value,
           "costs_rt_measured": costs, "excluded_step0": [k for k in TOKENS if k not in kept0],
           "token_retained": ver, "retained": retained, "account_criterion": crit_acct,
           "mechanical_reading": mech, "meta": meta}
    (OUT / f"Exp-61_{date}_criteria.json").write_text(json.dumps(out, indent=2, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(pt.round(4).to_string())
    if len(ac):
        print(ac[["set", "cost", "cap3", "account", "n_trades", "total_return_cad_pct", "cagr_cad_pct",
                  "max_dd_pct", "worst_day_pct", "worst_day_date", "pf_usd", "years"]].round(3).to_string())
    print(status.to_string())
    print(json.dumps({k: v for k, v in out.items() if k != "meta"}, indent=2, default=str))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["step0", "harness"], required=True)
    ap.add_argument("--quotes", default=str(DATA / "exp61_quotes.sqlite3"))
    ap.add_argument("--work-dir", default=str(ROOT / "outputs" / "exp61"))
    ap.add_argument("--date", default="2026-10-08")
    a = ap.parse_args(argv)
    step0 = OUT / f"Exp-61_{a.date}_step0.json"
    if a.stage == "step0":
        print(json.dumps(stage_step0(Path(a.quotes), step0), indent=2, default=str))
    else:
        stage_harness(Path(a.work_dir), step0, a.date)


if __name__ == "__main__":
    main()
