"""Exp 62 (A-EQ-AUDIT-001) -- executed to the letter of docs/agents/hypotheses/Exp-62.md (commit adefcba).

Same entries as the frozen config D walk-forward ledgers (15 primary assets + 16 Task E assets,
RF and logistic, pre-HOLDOUT TEST trades). Two exit rules, harness v1.3.0 fills:

* D-STOP   : config D exit = per-trade protective stop (ledger ``stop_distance``) + trailing
             0.63 % / 0.80 % + time exit after 50 bars, positional bars like the research and the
             forward bot (a position may be held overnight; the next-day open gap is filled at
             min(stop, open) by the harness).
* D-TIME50 : time exit at the close of the 50th bar, NO stop, never past the session: forced exit at
             the close of the last bar of the entry session (15:59 ET, 12:59 on early closes).

Entry: open of the bar after the signal bar (harness ``next_open``), only if that bar is in the
same US session (otherwise ``no_same_session_entry``: the bot cancels such entries).
Costs at 160 USD per position (preregistered): V1 IBKR Canada (tiered = decisional, fixed reported),
V2 zero-commission Canadian broker (no retail order API found -> unusable), V3 stock CFD
(Darwinex conditions, unverified, Quebec access unverified). All figures are IN-SAMPLE (the
ledgers are pre-HOLDOUT TEST folds of a strategy whose HOLDOUT is consumed): they can only reject.

Bars and ledgers are read-only. Single process. Outputs: docs/agents/results/Exp-62_<date>_*.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.execution_harness import (VERSION, USD_PER_CAD, ExitRule, apply_costs, get_platform,  # noqa: E402
                                         profit_factor, simulate_account, simulate_trade, with_per_share_fee)
from quant_bot.execution_harness.costs import DARWINEX_SWAP_ANNUAL, DARWINEX_USD_PER_SHARE  # noqa: E402
from quant_bot.features.basics import atr, realized_vol  # noqa: E402

PRIMARY = ["AMD", "PLTR", "UBER", "INTC", "BAC", "FB", "NFLX", "GOOGL", "PYPL", "DIS", "JNJ", "PG", "KO",
           "XOM", "WMT"]
TASK_E = ["AMZN", "BA", "BABA", "MU", "C", "CRM", "ADBE", "QCOM", "TXN", "AVGO", "CSCO", "V", "MA", "PEP",
          "MCD", "COST"]
DEPLOYED = sorted(set(TASK_E) - {"C"})
MODELS = ["rf", "logistic"]
NOTIONAL_USD = 160.0
INITIAL_CAD, FRACTION = 500.0, 0.33
ACTIVATE_AT, TRAIL_DIST, EXIT_WINDOW = 0.0063, 0.0080, 50
RULE_STOP = ExitRule(max_bars=EXIT_WINDOW, use_candidate_stop=True, trail_activation=ACTIVATE_AT,
                     trail_distance=TRAIL_DIST)
RESEARCH_COST = 0.0002
VENUES = {  # name -> (harness platform, usable by a bot from Quebec at this budget, decisional)
    "V1_ibkr_tiered": ("ibkr_ca_tiered", True, True),
    "V1_ibkr_fixed": ("ibkr_ca_fixed", True, False),
    "V2_zero_commission": ("zero_commission_ca", False, True),
    "V3_cfd_darwinex": ("cfd_darwinex_assumed", False, True),
}
NY = "America/New_York"
RECON: list[dict] = []  # every matched ledger trade of the 15 deployed symbols, entry at signal close


def load_bars(bar_dir: Path, sym: str) -> pd.DataFrame:
    b = pd.read_pickle(bar_dir / f"{sym}_full.pkl").sort_index()
    if b.index.tz is None:
        b.index = b.index.tz_localize("UTC")
    return b[["open", "high", "low", "close"]].astype(float)


def simulate_symbol(sym: str, group: str, bars: pd.DataFrame, ledgers: dict) -> list[dict]:
    o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    ts = bars.index.tz_convert("UTC").tz_localize(None).to_numpy()
    day = bars.index.tz_convert(NY).tz_localize(None).normalize().to_numpy()
    n = len(c)
    # last positional index of each session
    new_day = np.r_[day[1:] != day[:-1], True]
    last_of_day = np.flatnonzero(new_day)
    sess_last = last_of_day[np.searchsorted(last_of_day, np.arange(n))]
    a = atr(bars, 14)
    feats = pd.DataFrame({"atr_norm": a / bars.close, "realized_vol_30": realized_vol(bars.close, 30),
                          "range_pos_60": (bars.close - bars.low.rolling(60).min())
                          / (bars.high.rolling(60).max() - bars.low.rolling(60).min()).replace(0, np.nan)})
    fa = {k: feats[k].to_numpy() for k in feats}
    rows = []
    for model, led in ledgers.items():
        idx = bars.index.get_indexer(pd.to_datetime(led.entry_time, utc=True))
        for r, s in zip(led.itertuples(index=False), idx):
            base = {"symbol": sym, "group": group, "model": model, "fold": int(r.fold),
                    "signal_time": pd.Timestamp(r.entry_time), "ledger_raw": float(r.raw_return),
                    "stop_distance": float(r.stop_distance)}
            if s < 0:
                rows.append({**base, "status": "signal_bar_missing"})
                continue
            rec = None
            if sym in DEPLOYED:  # reconciliation with docs/exit_realism_check_equity.csv (intrabar), ALL trades
                rec = simulate_trade(o, h, l, c, int(s), RULE_STOP, stop_distance=float(r.stop_distance),
                                     entry_mode="signal_close")
                RECON.append({"symbol": sym, "model": model, "ledger_raw": float(r.raw_return),
                              "signal_close_gross": rec["gross_ret"]})
            j = s + 1
            if j >= n or day[j] != day[s]:
                rows.append({**base, "status": "no_same_session_entry"})
                continue
            base.update({k: float(fa[k][s]) for k in fa})
            stop = simulate_trade(o, h, l, c, int(s), RULE_STOP, stop_distance=float(r.stop_distance), ts=ts)
            mb = int(min(EXIT_WINDOW, sess_last[j] - j + 1))
            t50 = simulate_trade(o, h, l, c, int(s), ExitRule(max_bars=mb), ts=ts)
            # descriptive latency sensitivity: fill one bar later (the live bot fills at t+2 or t+3)
            lat1 = {"D-STOP": None, "D-TIME50": None}
            if j + 1 < n and day[j + 1] == day[s]:
                r1 = simulate_trade(o, h, l, c, int(s), RULE_STOP, stop_distance=float(r.stop_distance),
                                    latency_bars=1, ts=ts)
                t1 = simulate_trade(o, h, l, c, int(s), ExitRule(max_bars=int(min(EXIT_WINDOW, sess_last[j] - j))),
                                    latency_bars=1, ts=ts) if sess_last[j] - j >= 1 else None
                lat1 = {"D-STOP": r1["gross_ret"] if r1 else None, "D-TIME50": t1["gross_ret"] if t1 else None}
            for rule, res in (("D-STOP", stop), ("D-TIME50", t50)):
                if res is None:
                    rows.append({**base, "rule": rule, "status": "no_entry_bar"})
                    continue
                e, x = res["entry_idx"], res["exit_idx"]
                if res["exit_reason"] == "end_of_data":
                    status = "end_of_data"
                else:
                    status = "ok"
                span_min = (ts[x] - ts[e]) / np.timedelta64(1, "m")
                nights = int((day[x] - day[e]) / np.timedelta64(1, "D"))
                mfe = float(h[e:x + 1].max() / res["entry_price"] - 1.0)
                lows = l[e:x + 1].astype(float).copy()
                if res["exit_reason"] in ("stop", "trail"):
                    lows[-1] = res["exit_price"]
                rows.append({**base, "rule": rule, "status": status,
                             "entry_time": pd.Timestamp(ts[e]).tz_localize("UTC"),
                             "exit_time": pd.Timestamp(ts[x]).tz_localize("UTC"),
                             "entry_price": res["entry_price"], "exit_price": res["exit_price"],
                             "exit_reason": res["exit_reason"], "gross_ret": res["gross_ret"],
                             "mae_ret": res["mae_ret"], "mfe_ret": mfe, "bars_held": res["bars_held"],
                             "nights": nights, "missing_minutes": bool(nights == 0 and span_min != x - e),
                             "entry_slip_vs_signal_close": float(o[j] / c[s] - 1.0),
                             "recon_signal_close_gross": (rec["gross_ret"] if (rec is not None and rule == "D-STOP")
                                                          else np.nan),
                             "gross_ret_lat1": lat1[rule] if lat1[rule] is not None else np.nan,
                             "side": 1, "mark_times": ts[e:x + 1], "mark_prices": lows})
    return rows


def stats(x: pd.Series) -> dict:
    x = x.dropna()
    return {"n": int(len(x)), "mean_pct": 100 * float(x.mean()) if len(x) else np.nan,
            "pf": profit_factor(x) if len(x) else np.nan, "win": float((x > 0).mean()) if len(x) else np.nan,
            "se_pct": 100 * float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger-dir", required=True, help="outputs/strategy_a_equity of the main checkout (read-only)")
    ap.add_argument("--bar-dir", required=True, help="docs/_full_data_cache_a_equity (read-only)")
    ap.add_argument("--realism-csv", default=str(ROOT / "docs" / "exit_realism_check_equity.csv"))
    ap.add_argument("--trades-out", required=True, help="trade-level output (large, not committed)")
    ap.add_argument("--date", default="2026-10-07")
    ap.add_argument("--only", nargs="*", default=None, help="smoke test on a subset (writes with a _smoke suffix)")
    args = ap.parse_args(argv)
    ledger_dir, bar_dir = Path(args.ledger_dir), Path(args.bar_dir)
    out = ROOT / "docs" / "agents" / "results"
    pre = out / f"Exp-62_{args.date}{'_smoke' if args.only else ''}"

    rows = []
    for group, syms in (("primary", PRIMARY), ("taskE", TASK_E)):
        for sym in syms:
            if args.only and sym not in args.only:
                continue
            ledgers = {m: pd.read_csv(ledger_dir / f"own_asset_{sym}_{m}_trades.csv") for m in MODELS}
            bars = load_bars(bar_dir, sym)
            rows += simulate_symbol(sym, group, bars, ledgers)
            del bars
            print(sym, len(rows), flush=True)
    sim = pd.DataFrame(rows)
    sim["signal_time"] = pd.to_datetime(sim.signal_time, utc=True)
    # chronological halves: median signal time of all ledger entries (both models), fixed before results
    split = sim.drop_duplicates(["symbol", "model", "signal_time"]).signal_time.median()
    sim["half"] = np.where(sim.signal_time < split, "H1", "H2")
    status = sim.groupby(["rule", "model", "status"], dropna=False).size().rename("n").reset_index()
    status.to_csv(f"{pre}_status.csv", index=False)

    ok = sim[sim.status == "ok"].copy()
    med_price = ok.groupby("symbol").entry_price.median().to_dict()
    plats = {}
    for v, (pname, _, _) in VENUES.items():
        p = get_platform(pname)
        if v == "V3_cfd_darwinex":
            p = with_per_share_fee(p, DARWINEX_USD_PER_SHARE.value, med_price, DARWINEX_USD_PER_SHARE.source)
        plats[v] = p

    net = {}
    for v, p in plats.items():
        t = apply_costs(ok.drop(columns=["mark_times", "mark_prices"]), p, notional_usd=NOTIONAL_USD)
        x = t.net_ret_at_size
        if v == "V3_cfd_darwinex":  # long-CFD financing per night held (D-STOP overnight trades)
            x = x - t.nights * DARWINEX_SWAP_ANNUAL.value / 360.0
        net[v] = x
        ok[f"net_{v}"] = x.values
    ok["net_research_ref"] = ok.ledger_raw - RESEARCH_COST  # walk-forward convention, same entries

    summ, per_asset = [], []
    cols = {"gross": "gross_ret", "gross_latency1": "gross_ret_lat1", "research_ref_0.02": "net_research_ref", **{v: f"net_{v}" for v in VENUES}}
    for (rule, model), g in ok.groupby(["rule", "model"]):
        for label, col in cols.items():
            for scope, gg in (("all", g), ("H1", g[g.half == "H1"]), ("H2", g[g.half == "H2"]),
                              ("primary", g[g.group == "primary"]), ("taskE", g[g.group == "taskE"]),
                              ("deployed15", g[g.symbol.isin(DEPLOYED)])):
                summ.append({"rule": rule, "model": model, "measure": label, "scope": scope, **stats(gg[col])})
            pa = g.groupby("symbol")[col].mean()
            per_asset.append({"rule": rule, "model": model, "measure": label, "n_assets": int(len(pa)),
                              "n_assets_pos": int((pa > 0).sum()), "share_pos": float((pa > 0).mean())})
    summ = pd.DataFrame(summ)
    per_asset = pd.DataFrame(per_asset)
    summ.to_csv(f"{pre}_summary.csv", index=False)
    per_asset.to_csv(f"{pre}_per_asset_share.csv", index=False)
    asset_tab = ok.groupby(["rule", "model", "symbol", "group"]).agg(
        n=("gross_ret", "size"), gross_pct=("gross_ret", lambda s: 100 * s.mean()),
        v1_tiered_pct=("net_V1_ibkr_tiered", lambda s: 100 * s.mean()),
        v2_pct=("net_V2_zero_commission", lambda s: 100 * s.mean()),
        v3_pct=("net_V3_cfd_darwinex", lambda s: 100 * s.mean()),
        research_ref_pct=("net_research_ref", lambda s: 100 * s.mean())).reset_index()
    asset_tab.to_csv(f"{pre}_per_asset.csv", index=False)

    # mechanical criteria
    crit = []
    for (rule, model), _ in ok.groupby(["rule", "model"]):
        for v, (pname, usable, decisional) in VENUES.items():
            s = summ[(summ.rule == rule) & (summ.model == model) & (summ.measure == v)].set_index("scope")
            pa = per_asset[(per_asset.rule == rule) & (per_asset.model == model) & (per_asset.measure == v)].iloc[0]
            c = {"rule": rule, "model": model, "venue": v, "platform": pname, "decisional": decisional,
                 "mean_all_pct": s.loc["all", "mean_pct"], "mean_H1_pct": s.loc["H1", "mean_pct"],
                 "mean_H2_pct": s.loc["H2", "mean_pct"], "share_assets_pos": float(pa.share_pos),
                 "n_assets_pos": int(pa.n_assets_pos), "n_assets": int(pa.n_assets), "venue_usable": usable}
            c["edge_realistic"] = bool(c["mean_H1_pct"] > 0 and c["mean_H2_pct"] > 0
                                       and c["share_assets_pos"] >= 0.5 and usable)
            crit.append(c)
    crit = pd.DataFrame(crit)
    combos = crit[crit.decisional].groupby(["rule", "venue"]).edge_realistic.agg(["all", "any"]).reset_index()
    verdict = "PASS" if combos["all"].any() else "REJECT"

    # minimal budget for V1 (analytic): mean gross - proportional costs > 2 * per-order minimum / notional
    budgets = []
    for (rule, model), g in ok.groupby(["rule", "model"]):
        for v in ("V1_ibkr_tiered", "V1_ibkr_fixed"):
            p = plats[v]
            prop = float(np.mean([p.round_trip_pct(s) for s in g.symbol]))
            edge = float(g.gross_ret.mean()) - prop
            n_star = 2 * p.fixed_fee_usd_per_order.value / edge if edge > 0 else np.nan
            budgets.append({"rule": rule, "model": model, "venue": v, "mean_gross_pct": 100 * g.gross_ret.mean(),
                            "proportional_rt_pct": 100 * prop, "edge_before_min_pct": 100 * edge,
                            "min_notional_usd": n_star,
                            "min_account_cad_at_33pct": (n_star / FRACTION / USD_PER_CAD.value
                                                         if edge > 0 else np.nan)})
    budgets = pd.DataFrame(budgets)
    budgets.to_csv(f"{pre}_budget.csv", index=False)

    # accounts (reported without effect): 500 CAD, 33 %/position, 1 position/symbol, gross <= 100 %
    accts = []
    for (rule, model), g in ok.groupby(["rule", "model"]):
        g = g.reset_index(drop=True).copy()
        g["cand_id"] = np.arange(len(g))
        for v, p in plats.items():
            a = simulate_account(g, p, initial_cad=INITIAL_CAD, position_fraction=FRACTION)
            accts.append({"rule": rule, "model": model, "venue": v, "n_trades": a["n_trades"],
                          "skips": json.dumps(a["skips"]), "years": a.get("years"),
                          "cagr_cad_pct": a.get("cagr_cad_pct"), "total_return_cad_pct": a.get("total_return_cad_pct"),
                          "max_dd_pct": a.get("max_dd_pct"), "worst_day_pct": a.get("worst_day_pct"),
                          "worst_day_date": a.get("worst_day_date"), "pf_usd": a.get("pf_usd"),
                          "mean_ret_on_notional_pct": a.get("mean_ret_on_notional_pct"),
                          "total_cost_usd": a.get("total_cost_usd")})
            print("account", rule, model, v, round(a.get("cagr_cad_pct", np.nan), 2), flush=True)
    accts = pd.DataFrame(accts)
    accts.to_csv(f"{pre}_accounts.csv", index=False)

    # reconciliation with the existing exit-realism check (15 deployed, intrabar, entry at signal close)
    rec = {}
    try:
        ref = pd.read_csv(args.realism_csv)
        mine = ok[(ok.rule == "D-STOP") & ok.symbol.isin(DEPLOYED)]
        rec = {"ref_n": int(len(ref)), "ref_intrabar_mean_pct": 100 * float(ref.intrabar.mean()),
               "ref_intrabar_net002_pf": profit_factor(ref.intrabar - RESEARCH_COST),
               "harness_signal_close_n": int(mine.recon_signal_close_gross.notna().sum()),
               "harness_signal_close_mean_pct": 100 * float(mine.recon_signal_close_gross.mean()),
               "harness_signal_close_net002_pf": profit_factor(mine.recon_signal_close_gross - RESEARCH_COST),
               "harness_next_open_mean_pct": 100 * float(mine.gross_ret.mean()),
               "harness_next_open_net002_pf": profit_factor(mine.gross_ret - RESEARCH_COST)}
        rc = pd.DataFrame(RECON)
        per = []
        for (sy, m), rr in ref.groupby(["symbol", "model"]):
            mm = rc[(rc.symbol == sy) & (rc.model == m)]
            row = {"symbol": sy, "model": m, "ref_n": len(rr), "harness_n": len(mm)}
            if len(rr) == len(mm):  # same order: both follow the ledger rows
                row.update({"max_abs_diff_ledger": float(np.abs(rr.ledger.to_numpy() - mm.ledger_raw.to_numpy()).max()),
                            "max_abs_diff_intrabar_vs_signal_close": float(
                                np.abs(rr.intrabar.to_numpy() - mm.signal_close_gross.to_numpy()).max())})
            per.append(row)
        per = pd.DataFrame(per)
        per.to_csv(f"{pre}_reconciliation.csv", index=False)
        rec.update({"recon_n": int(len(rc)), "recon_signal_close_mean_pct": 100 * float(rc.signal_close_gross.mean()),
                    "recon_signal_close_net002_pf": profit_factor(rc.signal_close_gross - RESEARCH_COST),
                    "n_groups_count_mismatch": int((per.ref_n != per.harness_n).sum()),
                    "max_abs_diff_ledger_per_trade": float(per.max_abs_diff_ledger.max()),
                    "max_abs_diff_intrabar_vs_signal_close_per_trade": float(
                        per.max_abs_diff_intrabar_vs_signal_close.max())})
    except FileNotFoundError:
        rec = {"error": "realism csv not found"}

    desc = {
        "exit_reasons": ok.groupby(["rule", "model"]).exit_reason.value_counts().unstack(fill_value=0)
        .reset_index().to_dict(orient="records"),
        "overnight_share_dstop": float((ok[ok.rule == "D-STOP"].nights > 0).mean()),
        "missing_minutes_share": float(ok.missing_minutes.mean()),
        "time50_truncated_by_session_share": float((ok[ok.rule == "D-TIME50"].bars_held < EXIT_WINDOW).mean()),
        "entry_slip_vs_signal_close_mean_pct": 100 * float(ok[ok.rule == "D-STOP"].entry_slip_vs_signal_close.mean()),
        "worst_trade_pct": ok.groupby("rule").gross_ret.min().mul(100).to_dict(),
    }
    res = {"experiment": "Exp 62", "id": "A-EQ-AUDIT-001", "harness_version": VERSION,
           "preregistration": "docs/agents/hypotheses/Exp-62.md (commit adefcba)",
           "category": "EN ECHANTILLON (pre-HOLDOUT walk-forward TEST ledgers; HOLDOUT consumed by Exp 47)",
           "fill_convention": "entry next open (same session only); D-STOP stop/trailing intrabar gap-aware; "
                              "D-TIME50 close of bar 50 or of the session's last bar",
           "notional_usd_per_trade": NOTIONAL_USD, "split_time_H1_H2": str(split),
           "period": [str(ok.entry_time.min()), str(ok.exit_time.max())],
           "n_candidates": int(sim.drop_duplicates(["symbol", "model", "signal_time"]).shape[0]),
           "multiple_testing": "2 rules x 3 venues = 6 decisional combinations (x 2 model classes reported)",
           "model_rule": "a (rule, venue) combination is an edge only if the criterion holds for BOTH model "
                         "classes (rf and logistic), the deployed bot running both",
           "criteria": crit.to_dict(orient="records"), "combos": combos.to_dict(orient="records"),
           "verdict_proposed": verdict, "reconciliation": rec, "descriptive": desc,
           "costs": {v: p.describe() for v, p in plats.items() if v != "V3_cfd_darwinex"},
           "v3_swap_annual": DARWINEX_SWAP_ANNUAL.value}
    Path(f"{pre}_criteria.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    keep = [c for c in ok.columns if c not in ("mark_times", "mark_prices")]
    ok[keep].to_csv(args.trades_out, index=False, compression="gzip")
    print(json.dumps({"verdict": verdict, "split": str(split), "reconciliation": rec}, indent=1, default=str))
    print(crit.to_string())


if __name__ == "__main__":
    main()
