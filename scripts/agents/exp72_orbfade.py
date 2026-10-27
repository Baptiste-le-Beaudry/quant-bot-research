"""Exp 72 -- Fade de l'echec d'ORB 30 min sur MNQ (R1, H-R19). Test DECISIONNEL (preenregistre).

Preenregistrement fige : docs/agents/hypotheses/Exp-72.md.

Regle, statistiques et simulateur IMPORTES SANS MODIFICATION :
  - docs/agents/research/H-R19_scripts/families.py      (load, f2_orb_fade, stats)
  - docs/agents/research/H-R19_scripts/funded_orbfade.py (library)
  - docs/agents/research/H-R17_scripts/funded_sim.py     (run)
  - scripts/agents/exp64_noise_momentum.py               (build_grid, eligibility)
Seul ajout : le chargeur de la fenetre de decision (ce fichier).

Fenetre de decision : D1 = 2020-01-02 -> 2021-09-22, D2 = 2024-03-05 -> 2026-08-18.
BI3 = 2021-09-23 -> 2024-03-04 : calcule et rapporte SANS EFFET.
Historique de sigma : 14 jours eligibles pris en decembre 2019 (lecture a partir du 2019-12-01 ET).

Grille de decision (pour funded_orbfade.library, qui charge un fichier de grille) : les 14 derniers
jours eligibles avant D1 (historique de sigma, jamais `ok` : < 14 jours d'historique chacun),
puis D1 et D2 ; BI3 retire. La regle F2 est independante d'un jour a l'autre et sigma n'entre
que via sa finitude (masque `ok`) : le script VERIFIE que les trades obtenus sur cette grille sont
identiques a ceux de la grille complete restreinte a D1 u D2.

Usage : py -3.13 -I scripts/agents/exp72_orbfade.py --data-dir <data/indices> --work-dir <dir>
        --out-prefix <docs/agents/results/Exp-72_YYYY-MM-DD> [--skip-variants]
"""
import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "scripts" / "agents", ROOT / "docs" / "agents" / "research" / "H-R19_scripts",
          ROOT / "docs" / "agents" / "research" / "H-R17_scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import exp64_noise_momentum as e64  # noqa: E402
import families as F  # noqa: E402
import funded_orbfade as FO  # noqa: E402
import funded_sim as FS  # noqa: E402

D1 = (dt.date(2020, 1, 2), dt.date(2021, 9, 22))
BI3 = (dt.date(2021, 9, 23), dt.date(2024, 3, 4))
D2 = (dt.date(2024, 3, 5), dt.date(2026, 8, 18))
HIST_START = dt.date(2019, 12, 1)
SIGMA_HIST = 14
OR_LEN = 30
LABEL = "F2 ORB-fade OR30"
NAME = "NASDAQ100"
FILES = {"NASDAQ100": "NASDAQ100_1m.csv", "SP500": "SP500_1m.csv", "DOW30": "DOW30_1m.csv",
         "RUSSELL2000": "RUSSELL2000_1m.csv"}
# Prereg : 2,22 USD AR au notionnel 60 000 (0,0037 %) ; stress +1 tick/cote (3,22 USD).
COST_USD_PREREG = 2.22
STRESS_USD_PREREG = 3.22
N_PATHS, SEED, ATTEMPTS, ACCT = 3000, 11, 5, 50
CASES = {"principale": ("lucid", ("fixed", 3)), "secondaire": ("topstep", ("fixed", 5))}
# M2K (variante sans effet, fuite c) : absent des constantes de families.py. Valeurs de H-R19 §1.1
# (notionnel 14 975 USD, AR 2,22 USD = 0,0148 %, tick 0,1 pt sur un indice ~ 2 995).
M2K_CONST = {"cost": 0.0148e-2, "tick": 0.1 / 2995.0, "notional": 15000.0}


# --------------------------------------------------------------------------- periodes
def period_of(d):
    if d < D1[0]:
        return "pre"
    if d <= D1[1]:
        return "D1"
    if d <= BI3[1]:
        return "BI3"
    if d <= D2[1]:
        return "D2"
    return "post"


# --------------------------------------------------------------------------- chargeur
def load_window(path, start, end=None, chunksize=500_000):
    """Lit le CSV Dukascopy par blocs ; garde les barres dont la date ET est dans [start, end].
    S'arrete au premier bloc entierement apres `end`."""
    parts = []
    for ch in pd.read_csv(path, chunksize=chunksize):
        ts = pd.to_datetime(ch["timestamp"], utc=True).dt.tz_convert(e64.ET)
        d = ts.dt.date
        keep = (d >= start) if end is None else ((d >= start) & (d <= end))
        if keep.any():
            sub = ch.loc[keep].drop(columns=["timestamp"])
            sub.index = pd.DatetimeIndex(ts[keep], name="et")
            parts.append(sub)
        if end is not None and d.iloc[0] > end:
            break
    if not parts:
        raise ValueError(f"aucune barre dans [{start}, {end}] : {path}")
    return pd.concat(parts)


def grid_from_df(df):
    g = e64.build_grid(df)
    el = e64.eligibility(g)
    return g, el


def save_npz(path, g, el, rows=None):
    rows = np.arange(len(g["dates"])) if rows is None else np.asarray(rows, dtype=int)
    dates = np.array([str(g["dates"][i]) for i in rows])
    np.savez_compressed(path, dates=dates, **{k: g[k][rows] for k in ("open", "high", "low", "close", "volume")},
                        eligible=el["eligible"].to_numpy()[rows], prev_close=el["prev_close"].to_numpy()[rows])


def decision_rows(dates, eligible):
    """Indices des seances de la grille de decision : 14 derniers jours eligibles avant D1
    (historique de sigma) et toutes les seances qui suivent avant D1, puis D1 et D2."""
    per = [period_of(d) for d in dates]
    pre_el = [i for i, (p, e) in enumerate(zip(per, eligible)) if p == "pre" and e]
    start = pre_el[-SIGMA_HIST] if len(pre_el) >= SIGMA_HIST else 0
    return [i for i, p in enumerate(per) if (p == "pre" and i >= start) or p in ("D1", "D2")]


def prepare(data_dir, work_dir, name=NAME, start=HIST_START, end=D2[1], chunksize=500_000):
    """Construit grille complete et grille de decision ; retourne leurs repertoires."""
    work = Path(work_dir)
    full_dir, dec_dir = work / "full", work / "decision"
    full_dir.mkdir(parents=True, exist_ok=True)
    dec_dir.mkdir(parents=True, exist_ok=True)
    df = load_window(Path(data_dir) / FILES[name], start, end, chunksize)
    g, el = grid_from_df(df)
    save_npz(full_dir / f"{name}_grid.npz", g, el)
    if name == NAME:
        rows = decision_rows(g["dates"], el["eligible"].to_numpy())
        save_npz(dec_dir / f"{name}_grid.npz", g, el, rows)
    info = {"name": name, "first_session": str(g["dates"][0]), "last_session": str(g["dates"][-1]),
            "sessions": len(g["dates"]), "eligible": int(el["eligible"].sum())}
    return full_dir, dec_dir, info


# --------------------------------------------------------------------------- mesures
def masked(g, periods):
    g2 = dict(g)
    per = np.array([period_of(d) for d in g["dates"]])
    g2["ok"] = g["ok"] & np.isin(per, list(periods))
    return g2


def trade_key(g, tr):
    return [(str(g["dates"][int(t[0])]),) + tuple(float(x) for x in t[1:]) for t in tr]


def sharpe(x):
    x = np.asarray(x, dtype=float)
    sd = x.std(ddof=1) if len(x) > 1 else 0.0
    return float(x.mean() / sd * math.sqrt(252)) if sd > 0 else float("nan")


def daily_usd(g, tr, cost_usd, notional):
    """PnL quotidien (USD, 1 contrat) sur les jours `ok` de g, cout fixe en USD par AR."""
    days = np.flatnonzero(g["ok"])
    s = pd.Series(0.0, index=days)
    for t in tr:
        i, ep, xp, side = int(t[0]), t[2], t[4], t[5]
        s[i] += side * (xp / ep - 1) * notional - cost_usd
    return s


def period_block(g, name, periods, label=LABEL):
    gm = masked(g, periods)
    tr = F.f2_orb_fade(gm, OR_LEN)
    res = F.stats(gm, name, tr, label)
    if not isinstance(res, tuple):
        return {"periods": list(periods), **res}, None, tr
    st, full = res
    st = {"periods": list(periods), **st}
    st["sharpe_net_exact"] = sharpe(full["net"])
    st["sharpe_stress_exact"] = sharpe(full["net_st"])
    st["net_total_usd"] = round(float(full["net"].sum()), 1)
    s = full["net"]
    st["top5_share_exact"] = float(s.sort_values().iloc[-5:].sum() / s.sum()) if s.sum() > 0 else None
    full = full.assign(date=[g["dates"][k] for k in full.index])
    return st, full, tr


def funded(dec_dir):
    out = {}
    for edge in ("mes", "half"):
        lib = FO.library(str(dec_dir), edge)
        for case, (firm, pol) in CASES.items():
            r = FS.run(lib, firm, ACCT, pol, ATTEMPTS, n_paths=N_PATHS, seed=SEED)
            out[f"{case}_{edge}"] = {"firm": firm, "acct": ACCT, "policy": f"{pol[0]}:{pol[1]}",
                                     "attempts": ATTEMPTS, "edge": edge, "lib_days": int(len(lib[0])),
                                     "lib_mean_usd": lib[3], "lib_sd_usd": lib[2],
                                     **{k: float(v) for k, v in r.items()}}
    return out


def evaluate(m):
    """m : sharpe_all, sharpe_d1, sharpe_d2, sharpe_stress, top5_share, n_trades,
    main_mes_ev, main_mes_ev_se, main_mes_ev_per100, main_half_ev. Retourne criteres + verdict."""
    c = {
        "sharpe_all_ge_0.6": m["sharpe_all"] >= 0.6,
        "sharpe_d1_gt_0": m["sharpe_d1"] > 0,
        "sharpe_d2_gt_0": m["sharpe_d2"] > 0,
        "sharpe_stress_ge_0.4": m["sharpe_stress"] >= 0.4,
        "top5_share_le_0.5": m["top5_share"] is not None and m["top5_share"] <= 0.5,
        "main_mes_ev_gt_2se_and_per100_gt_0": (m["main_mes_ev"] > 2 * m["main_mes_ev_se"]) and m["main_mes_ev_per100"] > 0,
        "main_half_ev_ge_0": m["main_half_ev"] >= 0,
        "n_trades_ge_600": m["n_trades"] >= 600,
    }
    rej = {"sharpe_all_le_0.2": m["sharpe_all"] <= 0.2, "main_mes_ev_le_0": m["main_mes_ev"] <= 0}
    c = {k: bool(v) for k, v in c.items()}
    rej = {k: bool(v) for k, v in rej.items()}
    verdict = "PASS" if all(c.values()) else ("REJET" if any(rej.values()) else "INCERTAIN")
    return {"pass_conditions": c, "reject_conditions": rej, "verdict": verdict}


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


# --------------------------------------------------------------------------- principal
def check_equivalence(g_full, g_dec):
    """Verifie que la grille de decision donne exactement les jours ok et les trades de la grille
    complete restreinte a D1 u D2. Retourne (jours ok, trades)."""
    tr_dec = F.f2_orb_fade(g_dec, OR_LEN)
    g_fm = masked(g_full, ("D1", "D2"))
    tr_full = F.f2_orb_fade(g_fm, OR_LEN)
    ok_dec = {str(g_dec["dates"][i]) for i in np.flatnonzero(g_dec["ok"])}
    ok_full = {str(g_full["dates"][i]) for i in np.flatnonzero(g_fm["ok"])}
    assert ok_dec == ok_full, "jours ok differents entre grille de decision et grille complete"
    assert trade_key(g_dec, tr_dec) == trade_key(g_full, tr_full), "trades differents"
    assert all(period_of(g_dec["dates"][i]) in ("D1", "D2") for i in np.flatnonzero(g_dec["ok"]))
    return len(ok_dec), len(tr_dec)


def run_decision(full_dir, dec_dir):
    g_full = F.load(str(full_dir), NAME)
    g_dec = F.load(str(dec_dir), NAME)
    n_ok, n_tr = check_equivalence(g_full, g_dec)

    blocks = {}
    for key, per in (("D1uD2", ("D1", "D2")), ("D1", ("D1",)), ("D2", ("D2",)), ("BI3_sans_effet", ("BI3",)),
                     ("tout_2020_2026_sans_effet", ("D1", "BI3", "D2"))):
        st, full, tr = period_block(g_full, NAME, per)
        blocks[key] = st
        if key == "D1uD2":
            main_tr = tr
        if key == "tout_2020_2026_sans_effet":
            daily_all, tr_all = full, tr
    # Sharpe au cout du preenregistrement exact (2,22 / 3,22 USD), pour information
    gm = masked(g_full, ("D1", "D2"))
    s222 = daily_usd(gm, main_tr, COST_USD_PREREG, F.NOTIONAL[NAME])
    s322 = daily_usd(gm, main_tr, STRESS_USD_PREREG, F.NOTIONAL[NAME])
    per_s = np.array([period_of(g_full["dates"][i]) for i in s222.index])
    prereg_cost = {"sharpe_all_2.22": sharpe(s222), "sharpe_stress_3.22": sharpe(s322),
                   "sharpe_d1_2.22": sharpe(s222[per_s == "D1"]), "sharpe_d2_2.22": sharpe(s222[per_s == "D2"])}

    # daily.csv (toutes periodes 2020-2026, colonne decision)
    ntr = pd.Series(0, index=daily_all.index)
    for t in tr_all:
        ntr[int(t[0])] += 1
    daily = daily_all.assign(n_trades=ntr.reindex(daily_all.index).fillna(0).astype(int))
    daily["period"] = [period_of(d) for d in daily["date"]]
    daily["decision"] = daily["period"].isin(["D1", "D2"])
    daily = daily[["date", "period", "decision", "n_trades", "net", "net_st", "worst"]].rename(
        columns={"net": "net_usd", "net_st": "net_stress_usd", "worst": "worst_intraday_usd"})
    trades = pd.DataFrame([{"date": g_full["dates"][int(t[0])], "period": period_of(g_full["dates"][int(t[0])]),
                            "entry_bar": int(t[1]), "entry_px": t[2], "exit_bar": int(t[3]), "exit_px": t[4],
                            "side": int(t[5]), "worst_px": t[6]} for t in tr_all])

    fd = funded(dec_dir)
    assert fd["principale_mes"]["lib_days"] == blocks["D1uD2"]["days"], "bibliotheque funded != jours D1 u D2"
    m = {"sharpe_all": blocks["D1uD2"]["sharpe_net_exact"], "sharpe_d1": blocks["D1"]["sharpe_net_exact"],
         "sharpe_d2": blocks["D2"]["sharpe_net_exact"], "sharpe_stress": blocks["D1uD2"]["sharpe_stress_exact"],
         "top5_share": blocks["D1uD2"]["top5_share_exact"], "n_trades": blocks["D1uD2"]["n"],
         "main_mes_ev": fd["principale_mes"]["ev"], "main_mes_ev_se": fd["principale_mes"]["ev_se"],
         "main_mes_ev_per100": fd["principale_mes"]["ev_per100"], "main_half_ev": fd["principale_half"]["ev"]}
    ev = evaluate(m)
    return {"metrics": m, **ev, "blocks": blocks, "prereg_cost_info": prereg_cost, "funded": fd,
            "equivalence_check": {"ok_days": n_ok, "trades": n_tr, "identical": True}}, daily, trades


def run_variants(data_dir, work_dir):
    F.COST.setdefault("RUSSELL2000", M2K_CONST["cost"])
    F.TICKPCT.setdefault("RUSSELL2000", M2K_CONST["tick"])
    F.NOTIONAL.setdefault("RUSSELL2000", M2K_CONST["notional"])
    out = {}
    for name, start, end, per in (("SP500", HIST_START, D2[1], ("D1", "BI3", "D2")),
                                  ("DOW30", HIST_START, D2[1], ("D1", "BI3", "D2")),
                                  ("RUSSELL2000", dt.date(2000, 1, 1), None, ("pre", "D1", "BI3", "D2", "post"))):
        full_dir, _, info = prepare(data_dir, Path(work_dir) / name, name, start, end)
        g = F.load(str(full_dir), name)
        st, _, _ = period_block(g, name, per)
        out[name] = {"load": info, **st}
        print(name, json.dumps(_clean(st), default=str), flush=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--skip-variants", action="store_true")
    a = ap.parse_args(argv)
    full_dir, dec_dir, info = prepare(a.data_dir, a.work_dir)
    print("chargement", info, flush=True)
    res, daily, trades = run_decision(full_dir, dec_dir)
    res["load"] = info
    print(json.dumps(_clean({k: res[k] for k in ("metrics", "pass_conditions", "reject_conditions", "verdict")}),
                     indent=1), flush=True)
    prefix = Path(a.out_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(f"{prefix}_daily.csv", index=False)
    trades.to_csv(f"{prefix}_trades.csv", index=False)
    if not a.skip_variants:
        res["variants_sans_effet"] = run_variants(a.data_dir, a.work_dir)
    Path(f"{prefix}_criteria.json").write_text(json.dumps(_clean(res), indent=1, default=str), encoding="utf-8")
    print("verdict", res["verdict"])


if __name__ == "__main__":
    main()
