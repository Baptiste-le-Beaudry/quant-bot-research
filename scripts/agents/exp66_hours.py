"""Exp 66 (T-HOUR-001 / T-048) -- hour-of-day effects on SOL/BTC/ETH, discovery P1 -> confirmation P2.

Preregistration (frozen, applied literally): docs/agents/hypotheses/Exp-66.md.

Data: Binance 1m bars SOLUSDT/BTCUSDT/ETHUSDT from docs/_full_data_cache/<SYM>_full.pkl (read only,
via quant_bot.execution_harness.data.load_bars). Hour return = open of the HH:00 bar -> open of the
HH+1:00 bar (UTC). An hour is kept only if BOTH bars exist with a finite open (missing bars are
counted, never filled).

Per-trade cost (preregistration): 0.02 % round trip (Jupiter /build) + 0.01 USD per swap on a
116 USD position -> cost_rt = 0.0002 + 2 * 0.01 / 116.

Interpretation choices (spec ambiguities, the most conservative option is taken and reported):
  * "t regroupe" -- the 3 symbols trade the same hour and are strongly correlated, so a t computed
    on the pooled symbol-hours treats correlated observations as independent. Decisional t =
    min(t_pooled, t_daily) where t_daily is the t of the equal-weight (available symbols) daily
    portfolio return of that hour (n = days). Both are reported.
  * Selection: the 2 hours with the highest pooled mean net return are taken first; each is retained
    only if its t >= 2.5 (no reaching further down the ranking). 0 retained -> REJET without P2.
  * P2 end "2026-08-17" is inclusive: hour starts < 2026-08-18 00:00 UTC (BTC/ETH data end
    2026-08-17 00:00, so their last hour is 2026-08-16 23:00).
  * Account (500 CAD): common harness v1.3, platform jupiter_build (0.01 %/side + 0.01 USD/swap,
    funding ramp 0.5 %/direction + 10 CAD), position_fraction 0.33, entry at the open of HH:00
    (signal bar = HH-1:59, next_open), time exit at the close of the HH:59 bar (harness convention,
    = the next open up to the inter-bar gap), no stop. Decisional CAGR = CAD CAGR after the ramp
    over the full P2 calendar (2025-01-01 -> 2026-08-18).

  python scripts/agents/exp66_hours.py --stage extract   # hourly returns -> outputs/exp66/hourly.parquet
  python scripts/agents/exp66_hours.py --stage p1        # P1 table + selection (commit before p2)
  python scripts/agents/exp66_hours.py --stage p2        # P2 tables, account, criteria
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SYMBOLS = ("SOLUSDT", "BTCUSDT", "ETHUSDT")
DATA_DIR = Path("C:/AAProjet/quant_bot_v1/docs/_full_data_cache")
OUT = ROOT / "outputs" / "exp66"
RES = ROOT / "docs" / "agents" / "results"
TAG = "Exp-66_2026-10-08"

P1 = (pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC"))
P2 = (pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2026-08-18", tz="UTC"))

POSITION_USD = 116.0
BUILD_RT = 0.0002
SWAP_USD = 0.01
COST_RT = BUILD_RT + 2 * SWAP_USD / POSITION_USD
# /order (reported without effect): SOL 0.041 % RT measured quote incl. fee; cbBTC/WETH 10 bps fee per swap
ORDER_RT = {"SOLUSDT": 0.00041, "BTCUSDT": 0.0020, "ETHUSDT": 0.0020}

T_SELECT = 2.5
N_SELECT = 2
FUNDING_HOURS = (0, 8, 16)


# ----------------------------------------------------------------------------- data
def hourly_returns(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Open(HH:00) -> open(HH+1:00) gross returns. Both bars must exist with a finite, > 0 open."""
    o = bars["open"].astype(float)
    if o.index.tz is None:
        o.index = o.index.tz_localize("UTC")
    o = o[~o.index.duplicated(keep="first")].sort_index()
    starts = o[(o.index.minute == 0) & (o.index.second == 0)]
    nxt = o.reindex(starts.index + pd.Timedelta(hours=1))
    a, b = starts.to_numpy(), nxt.to_numpy()
    ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
    out = pd.DataFrame({"hour_start": starts.index[ok], "gross_ret": b[ok] / a[ok] - 1.0})
    stats = {"hour_bars": int(len(starts)), "kept": int(ok.sum()), "dropped_missing_next_or_nan": int((~ok).sum())}
    return out, stats


def add_fields(h: pd.DataFrame) -> pd.DataFrame:
    h = h.copy()
    h["hour_start"] = pd.to_datetime(h["hour_start"], utc=True)
    h["hour"] = h["hour_start"].dt.hour
    h["date"] = h["hour_start"].dt.floor("D")
    h["year"] = h["hour_start"].dt.year
    h["weekend"] = h["hour_start"].dt.dayofweek >= 5
    h["net_ret"] = h["gross_ret"] - COST_RT
    h["net_ret_order"] = h["gross_ret"] - h["symbol"].map(ORDER_RT) - 2 * SWAP_USD / POSITION_USD
    return h


def in_period(h: pd.DataFrame, period) -> pd.DataFrame:
    return h[(h["hour_start"] >= period[0]) & (h["hour_start"] < period[1])]


# ----------------------------------------------------------------------------- stats
def tstat(x) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return float("nan")
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / math.sqrt(len(x)))) if sd > 0 else float("nan")


def group_stats(g: pd.DataFrame, col: str = "net_ret") -> dict:
    """Pooled stats + daily equal-weight portfolio t over the given rows (one hour or a hour set)."""
    daily = g.groupby(["date", "hour"])[col].mean()  # equal weight over the symbols available that hour
    t_pool, t_day = tstat(g[col]), tstat(daily)
    return {"n_obs": int(len(g)), "n_portfolio_hours": int(len(daily)),
            "mean_gross_pct": 100 * float(g["gross_ret"].mean()) if len(g) else float("nan"),
            "mean_net_pct": 100 * float(g[col].mean()) if len(g) else float("nan"),
            "t_pooled": t_pool, "t_daily": t_day,
            "t_decisional": float(np.nanmin([t_pool, t_day])) if np.isfinite([t_pool, t_day]).any() else float("nan"),
            "win_rate": float((g[col] > 0).mean()) if len(g) else float("nan")}


def hour_table(h: pd.DataFrame, col: str = "net_ret") -> pd.DataFrame:
    rows = []
    for hr in range(24):
        g = h[h["hour"] == hr]
        r = {"hour_utc": hr, **group_stats(g, col)}
        for s in SYMBOLS:
            gs = g[g["symbol"] == s]
            r[f"mean_net_pct_{s}"] = 100 * float(gs[col].mean()) if len(gs) else float("nan")
            r[f"t_{s}"] = tstat(gs[col])
            r[f"n_{s}"] = int(len(gs))
        r["funding_hour"] = hr in FUNDING_HOURS
        rows.append(r)
    t = pd.DataFrame(rows)
    t["rank_mean_net"] = t["mean_net_pct"].rank(ascending=False, method="first").astype(int)
    return t


def select_hours(table: pd.DataFrame, k: int = N_SELECT, t_min: float = T_SELECT) -> dict:
    top = table.sort_values("mean_net_pct", ascending=False).head(k)
    cands = [{"hour_utc": int(r.hour_utc), "mean_net_pct": float(r.mean_net_pct), "t_pooled": float(r.t_pooled),
              "t_daily": float(r.t_daily), "t_decisional": float(r.t_decisional),
              "passes_t": bool(r.t_decisional >= t_min)} for r in top.itertuples()]
    retained = [c["hour_utc"] for c in cands if c["passes_t"]]
    return {"top_k_by_mean": cands, "retained_hours": retained, "t_min": t_min, "k": k,
            "decision": "CONTINUE_TO_P2" if retained else "REJET (no hour with t >= 2.5 among the top 2; P2 not computed)"}


def verdict66(p2: pd.DataFrame, retained: list[int], account: dict) -> dict:
    """Frozen P2 criteria of Exp-66.md, read mechanically."""
    sel = p2[p2["hour"].isin(retained)]
    pooled = group_stats(sel)
    per_hour = {int(hr): 100 * float(sel.loc[sel["hour"] == hr, "net_ret"].mean()) for hr in retained}
    per_sym = {s: 100 * float(sel.loc[sel["symbol"] == s, "net_ret"].mean()) for s in SYMBOLS}
    c = {
        "each_hour_mean_net_gt0": all(v > 0 for v in per_hour.values()),
        "pooled_t_ge_2": bool(pooled["t_decisional"] >= 2.0),
        "mean_net_gt0_on_2of3_symbols": sum(v > 0 for v in per_sym.values()) >= 2,
        "cagr_cad_ge_10pct": bool(account.get("cagr_cad_pct", float("-inf")) >= 10.0),
        "maxdd_ge_minus25pct": bool(account.get("max_dd_pct", float("-inf")) >= -25.0),
    }
    if pooled["mean_net_pct"] <= 0:
        v = "REJET"
    elif all(c.values()):
        v = "PASS"
    else:
        v = "INCERTAIN"
    return {"verdict": v, "criteria": c, "pooled": pooled, "per_hour_mean_net_pct": per_hour,
            "per_symbol_mean_net_pct": per_sym}


# ----------------------------------------------------------------------------- stages
def stage_extract(data_dir: Path = DATA_DIR, out: Path = OUT) -> None:
    from quant_bot.execution_harness.data import load_bars
    out.mkdir(parents=True, exist_ok=True)
    frames, stats = [], {}
    for s in SYMBOLS:
        bars = load_bars(s, data_dir)
        h, st = hourly_returns(bars)
        st.update({"first_bar": str(bars.index[0]), "last_bar": str(bars.index[-1])})
        h["symbol"] = s
        frames.append(h)
        stats[s] = st
        del bars
    pd.concat(frames, ignore_index=True).to_parquet(out / "hourly.parquet")
    (out / "extract_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


def load_hourly(out: Path = OUT) -> pd.DataFrame:
    return add_fields(pd.read_parquet(out / "hourly.parquet"))


def by_year_table(h: pd.DataFrame, hours) -> pd.DataFrame:
    rows = []
    for (hr, yr), g in h[h["hour"].isin(hours)].groupby(["hour", "year"]):
        rows.append({"hour_utc": int(hr), "year": int(yr), **group_stats(g)})
    for yr, g in h[h["hour"].isin(hours)].groupby("year"):
        rows.append({"hour_utc": "selected", "year": int(yr), **group_stats(g)})
    return pd.DataFrame(rows)


def stage_p1(out: Path = OUT, res: Path = RES) -> dict:
    h = in_period(load_hourly(out), P1)
    tab = hour_table(h)
    tab.to_csv(res / f"{TAG}_hours_P1.csv", index=False, float_format="%.6g")
    sel = select_hours(tab)
    sel.update({"period": [str(P1[0]), str(P1[1])], "cost_rt": COST_RT, "n_variants_examined": 24,
                "t_definition": "t_decisional = min(t_pooled over symbol-hours, t of the equal-weight daily "
                                "portfolio return of the hour)",
                "n_obs_P1": int(len(h))})
    (res / f"{TAG}_selection_P1.json").write_text(json.dumps(sel, indent=2))
    print(tab[["hour_utc", "n_obs", "mean_net_pct", "t_pooled", "t_daily", "rank_mean_net"]].to_string())
    print(json.dumps(sel, indent=2))
    return sel


def account_p2(retained: list[int], platform: str) -> dict:
    from quant_bot.execution_harness import ExitRule, run_trades, simulate_account
    from quant_bot.execution_harness.data import load_bars
    days = pd.date_range(P2[0], P2[1] - pd.Timedelta(days=1), freq="D")
    cand = pd.DataFrame([{"symbol": s, "signal_time": d + pd.Timedelta(hours=hr) - pd.Timedelta(minutes=1)}
                         for d in days for hr in retained for s in SYMBOLS])
    tr = run_trades(cand, ExitRule(max_bars=60), platform, bars_loader=lambda s: load_bars(s, DATA_DIR))
    acc = simulate_account(tr, platform, initial_cad=500.0, position_fraction=0.33, period=P2)
    acc.pop("equity_minute", None)
    led = acc.pop("ledger", None)
    acc["status_counts"] = tr["status"].value_counts().to_dict()
    acc["n_candidates"] = int(len(tr))
    return acc, led


def stage_p2(out: Path = OUT, res: Path = RES) -> dict:
    sel = json.loads((res / f"{TAG}_selection_P1.json").read_text())
    retained = sel["retained_hours"]
    if not retained:
        raise SystemExit("P1 selection is REJET: P2 must not be computed")
    hall = load_hourly(out)
    h2 = in_period(hall, P2)
    tab2 = hour_table(h2)
    tab2.to_csv(res / f"{TAG}_hours_P2.csv", index=False, float_format="%.6g")
    acc_build, led = account_p2(retained, "jupiter_build")
    led.to_csv(res / f"{TAG}_ledger_P2_build.csv", index=False, float_format="%.6g")
    acc_order, _ = account_p2(retained, "jupiter_order")
    v = verdict66(h2, retained, acc_build)
    sel_rows = h2[h2["hour"].isin(retained)]
    h1 = in_period(hall, P1)
    reported = {
        "by_year": pd.concat([by_year_table(h1, retained).assign(period="P1"),
                              by_year_table(h2, retained).assign(period="P2")]).to_dict("records"),
        "weekday_vs_weekend_P2": {("weekend" if w else "weekday"): group_stats(g)
                                  for w, g in sel_rows.groupby("weekend")},
        "weekday_vs_weekend_P1": {("weekend" if w else "weekday"): group_stats(g)
                                  for w, g in h1[h1["hour"].isin(retained)].groupby("weekend")},
        "funding_hours": {p: {int(hr): group_stats(hh[hh["hour"] == hr]) for hr in FUNDING_HOURS}
                          for p, hh in (("P1", h1), ("P2", h2))},
        "order_cost_P2_selected": group_stats(sel_rows, "net_ret_order"),
        "account_jupiter_order": acc_order,
    }
    crit = {"prereg": "docs/agents/hypotheses/Exp-66.md", "engine": "scripts/agents/exp66_hours.py",
            "selection_file": f"docs/agents/results/{TAG}_selection_P1.json", "retained_hours": retained,
            "period_P2": [str(P2[0]), str(P2[1])], "cost_rt_per_trade": COST_RT,
            "fill": "hour open -> next hour open (per trade); harness next_open entry, time exit at close of "
                    "HH:59 (account)", **v, "account_jupiter_build": acc_build, "reported_without_effect": reported}
    (res / f"{TAG}_criteria.json").write_text(json.dumps(crit, indent=2, default=str))
    print(json.dumps({k: crit[k] for k in ("retained_hours", "verdict", "criteria", "pooled",
                                           "per_hour_mean_net_pct", "per_symbol_mean_net_pct")}, indent=2, default=str))
    print({k: acc_build[k] for k in ("n_trades", "cagr_cad_pct", "cagr_trading_pct", "max_dd_pct",
                                      "total_return_cad_pct", "skips")})
    return crit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("extract", "p1", "p2"), required=True)
    a = ap.parse_args()
    {"extract": stage_extract, "p1": stage_p1, "p2": stage_p2}[a.stage]()


if __name__ == "__main__":
    main()
