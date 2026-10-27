"""Exp 62 -- forward Equity trades since the 2026-10-01 refit, DESCRIPTIVE ONLY (no verdict).

Input: a read-only CSV dump of the remote ``equity_forward_state.sqlite3`` (made over SSH with
``file:...?mode=ro``; see the report for the exact command), the trade-level output of
``exp62_equity_audit.py`` (historical distribution, in-sample) and the refit bundle parts
(selection cuts; optional in-sample probability distribution of the refit models).

Split: signal time before / after D-04 (2026-10-07 02:46:25 UTC). Before D-04 the bot entered at
the signal close and exited at the stop level on close breaches (research convention); after D-04
it enters at the next available open and exits on intrabar stops. Every forward signal is ALSO
replayed with harness v1.3 on the bot's own bars (D-STOP next_open), so both periods are compared
on the same convention.
"""
from __future__ import annotations

import argparse
import io
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quant_bot.execution_harness import ExitRule, apply_costs, get_platform, profit_factor, simulate_trade  # noqa: E402

D04 = pd.Timestamp("2026-10-07 02:46:25", tz="UTC")
RULE_STOP = ExitRule(max_bars=50, use_candidate_stop=True, trail_activation=0.0063, trail_distance=0.008)
FEATS = ["realized_vol_30", "atr_norm", "range_pos_60"]
NOTIONAL = 160.0


def read_dump(path: Path) -> dict:
    secs, name, buf = {}, None, []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith("#####SECTION "):
            if name:
                secs[name] = pd.read_csv(io.StringIO("".join(buf)))
            name, buf = line.split()[1], []
        else:
            buf.append(line)
    if name:
        secs[name] = pd.read_csv(io.StringIO("".join(buf)))
    return secs


def q(x, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    x = pd.Series(x).dropna()
    return {f"q{int(100 * k)}": float(x.quantile(k)) for k in qs} | {"mean": float(x.mean()), "n": int(len(x))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--hist-trades", required=True, help="exp62_equity_audit.py --trades-out file")
    ap.add_argument("--bundle-parts", required=True, help="docs/forward_paper/equity_strategy_a_refit_20261001_parts")
    ap.add_argument("--bar-dir", required=True, help="docs/_full_data_cache_a_equity (in-sample proba distribution)")
    ap.add_argument("--date", default="2026-10-07")
    args = ap.parse_args(argv)
    pre = ROOT / "docs" / "agents" / "results" / f"Exp-62_{args.date}_forward"
    d = read_dump(Path(args.dump))
    trades, sig, bars = d["trades"], d["signals_sel"], d["bars"]
    for c in ("entry_time", "exit_time"):
        trades[c] = pd.to_datetime(trades[c], utc=True, format="ISO8601")
    sig["timestamp"] = pd.to_datetime(sig.timestamp, utc=True, format="ISO8601")
    bars["timestamp"] = pd.to_datetime(bars.timestamp, utc=True, format="ISO8601")

    # one row per signal (the 3 risk profiles of a model share the signal, entry and exit)
    trades["model"] = np.where(trades.profile.str.contains("_RF_"), "rf", "logistic")
    t = (trades.sort_values("profile").drop_duplicates("signal_id")
         .merge(sig[["signal_id", "timestamp", "probability", "features_json"]], on="signal_id", how="left"))
    feats = pd.DataFrame([json.loads(s) for s in t.features_json])
    t = pd.concat([t.drop(columns="features_json"), feats[FEATS]], axis=1)
    t["period"] = np.where(t.timestamp < D04, "avant_D04", "apres_D04")
    t["bot_raw_ret"] = t.exit_price / t.entry_price - 1
    t["bot_entry_lag_min"] = (t.entry_time - t.timestamp).dt.total_seconds() / 60

    cuts, stops = {}, {}
    for f in Path(args.bundle_parts).glob("*.pkl"):
        sym, model = f.stem.rsplit("_", 1)
        with open(f, "rb") as fh:
            b = pickle.load(fh)
        cuts[(sym, model)] = (b["selection_cut"], b["range_cut"], b["vol_cut"])
        stops[(sym, model)] = b["protective_stop_distance"]
    t["selection_cut"] = [cuts[(s, m)][0] for s, m in zip(t.symbol, t.model)]
    t["proba_minus_cut"] = t.probability - t.selection_cut
    t["stop_distance"] = [stops[(s, m)] for s, m in zip(t.symbol, t.model)]

    # harness replay on the bot's own Dukascopy bars
    rep = []
    for r in t.itertuples(index=False):
        b = bars[bars.symbol == r.symbol].sort_values("timestamp").set_index("timestamp")
        s = b.index.get_indexer([r.timestamp])[0]
        if s < 0:
            rep.append({"rep_status": "signal_bar_missing"})
            continue
        o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        ts = b.index.tz_localize(None).to_numpy()
        res = simulate_trade(o, h, l, c, int(s), RULE_STOP, stop_distance=r.stop_distance, ts=ts)
        if res is None:
            rep.append({"rep_status": "no_entry_bar"})
            continue
        e, x = res["entry_idx"], res["exit_idx"]
        rep.append({"rep_status": "ok" if res["exit_reason"] != "end_of_data" else "end_of_data",
                    "rep_gross": res["gross_ret"], "rep_reason": res["exit_reason"], "rep_mae": res["mae_ret"],
                    "rep_mfe": float(h[e:x + 1].max() / res["entry_price"] - 1), "rep_bars": res["bars_held"],
                    "rep_entry_slip": float(o[s + 1] / c[s] - 1), "signal_close": float(c[s]),
                    "bot_entry_vs_signal_close": float(r.entry_price / c[s] - 1)})
    t = pd.concat([t.reset_index(drop=True), pd.DataFrame(rep)], axis=1)
    t["status"] = t.rep_status
    t["gross_ret"] = t.rep_gross
    ok = t[t.status == "ok"]
    v1 = apply_costs(ok.assign(symbol=ok.symbol), get_platform("ibkr_ca_tiered"), notional_usd=NOTIONAL)
    t.loc[ok.index, "rep_net_v1_tiered"] = v1.net_ret_at_size.values
    t["rep_net_research"] = t.rep_gross - 0.0002
    t["bot_net_research"] = t.bot_raw_ret - 0.0002
    t.to_csv(f"{pre}_trades.csv", index=False)

    # historical (in-sample) distribution: D-STOP harness trades on the 15 deployed symbols
    hist = pd.read_csv(args.hist_trades, compression="gzip")
    hist = hist[(hist.rule == "D-STOP") & hist.symbol.isin(t.symbol.unique())]
    out = {"category": "FORWARD descriptif (aucun verdict) ; historique = EN ECHANTILLON",
           "d04_boundary_utc": str(D04), "n_forward_signals_traded": int(len(t)),
           "forward_span": [str(t.timestamp.min()), str(t.exit_time.max())], "groups": {}}
    hist_block = {"n": int(len(hist)), "gross_pct": q(100 * hist.gross_ret), "mae_pct": q(100 * hist.mae_ret),
                  "mfe_pct": q(100 * hist.mfe_ret), "entry_slip_pct": q(100 * hist.entry_slip_vs_signal_close),
                  **{f: q(hist[f]) for f in FEATS},
                  "mean_net_research_pct": 100 * float((hist.gross_ret - 0.0002).mean()),
                  "sd_gross_pct": 100 * float(hist.gross_ret.std())}
    out["historical_dstop_deployed"] = hist_block
    sd = float(hist.gross_ret.std())
    for (period, model), g in list(t.groupby(["period", "model"])) + [(("tous", "tous"), t)]:
        gok = g[g.status == "ok"]
        out["groups"][f"{period}|{model}"] = {
            "n": int(len(g)), "n_replay_ok": int(len(gok)), "symbols": g.symbol.value_counts().to_dict(),
            "probability": q(g.probability), "proba_minus_cut": q(g.proba_minus_cut),
            **{f: q(g[f]) for f in FEATS},
            "bot_recorded_net_research_pct": q(100 * g.bot_net_research),
            "bot_recorded_pf": profit_factor(g.bot_net_research),
            "bot_exit_reasons": g.exit_reason.value_counts().to_dict(),
            "bot_entry_lag_min": q(g.bot_entry_lag_min),
            "bot_entry_vs_signal_close_pct": q(100 * g.bot_entry_vs_signal_close),
            "replay_gross_pct": q(100 * gok.rep_gross), "replay_net_research_pct": q(100 * gok.rep_net_research),
            "replay_pf_research": profit_factor(gok.rep_net_research),
            "replay_net_v1_tiered_pct": q(100 * gok.rep_net_v1_tiered),
            "replay_mae_pct": q(100 * gok.rep_mae), "replay_mfe_pct": q(100 * gok.rep_mfe),
            "replay_reasons": gok.rep_reason.value_counts().to_dict(),
            "replay_entry_slip_pct": q(100 * gok.rep_entry_slip),
            "z_mean_gross_vs_hist": (float((gok.rep_gross.mean() - hist.gross_ret.mean()) / (sd / np.sqrt(len(gok))))
                                     if len(gok) else None)}

    # in-sample probability distribution of the refit models on their last 6 TRAIN months (selected bars)
    try:
        from quant_bot.features.build import build_feature_matrix
        rows = []
        for (sym, model), (cut, rcut, vcut) in sorted(cuts.items()):
            if sym not in set(t.symbol):
                continue
            with open(Path(args.bundle_parts) / f"{sym}_{model}.pkl", "rb") as fh:
                b = pickle.load(fh)
            bars_h = pd.read_pickle(Path(args.bar_dir) / f"{sym}_full.pkl").sort_index()
            bars_h = bars_h[bars_h.index >= bars_h.index.max() - pd.Timedelta(days=190)]
            X = build_feature_matrix(bars_h)
            X = X[X.index >= bars_h.index.max() - pd.Timedelta(days=182)]
            p = b["model"].predict_proba(X)
            sel = (p > cut) & (X.range_pos_60 < rcut) & (X.realized_vol_30 > vcut)
            rows.append(pd.DataFrame({"symbol": sym, "model": model, "proba": p[sel].values,
                                      "proba_minus_cut": (p[sel] - cut).values}))
        ins = pd.concat(rows)
        out["in_sample_refit_selected_last6m"] = {
            m: {"n": int(len(g)), "probability": q(g.proba), "proba_minus_cut": q(g.proba_minus_cut)}
            for m, g in ins.groupby("model")}
    except Exception as exc:  # descriptive extra, must not block the report
        out["in_sample_refit_selected_last6m"] = {"error": repr(exc)}
    Path(f"{pre}.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str)[:12000])


if __name__ == "__main__":
    main()
