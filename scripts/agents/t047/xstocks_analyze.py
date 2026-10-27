"""Analyse T-047 quotes: round-trip cost (160 USD), gap to underlying, ladder impact. Writes CSVs."""
import json, sys, statistics as st, datetime as dt, csv, collections, math

mints = json.load(open(sys.argv[1]))
files = {"xstocks": sys.argv[2], "bp": sys.argv[3], "tn": sys.argv[4]}
outdir = sys.argv[5]
by_sym_fam = {}
for m, r in mints.items():
    by_sym_fam[(r["sym"], r["family"])] = r


def session(t):
    d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    if d.weekday() >= 5:
        return "weekend"
    m = d.hour * 60 + d.minute  # EDT = UTC-4 in October
    if 13 * 60 + 30 <= m < 20 * 60:
        return "regular"
    if 8 * 60 <= m < 13 * 60 + 30:
        return "pre"
    if 20 * 60 <= m < 24 * 60:
        return "post"
    return "overnight"


rows = []
under = {}  # (file, cycle, sym) -> rec
for fam_file, path in files.items():
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    for r in recs:
        if r["kind"] == "under":
            under[(fam_file, r["cycle"], r["sym"])] = r
    pend = {}
    for r in recs:
        if r["kind"] != "q" or r["size"] != 160:
            continue
        key = (r["cycle"], r["sym"], r["ep"])
        if r["side"] == "buy":
            pend[key] = r
        elif key in pend:
            b = pend.pop(key)
            fam = "backpack" if fam_file == "bp" and r["sym"] not in ("C", "MA") else "xstocks"
            meta = by_sym_fam[(r["sym"], fam)]
            try:
                usdc_in = int(b["inAmount"]) / 1e6
                raw = int(b["outAmount"])
                usdc_out = int(r["outAmount"]) / 1e6
            except Exception:
                continue
            shares = raw / 10 ** meta["decimals"] * meta["multiplier"]
            p_buy, p_sell = usdc_in / shares, usdc_out / shares
            mid = math.sqrt(p_buy * p_sell)
            u = under.get((fam_file, r["cycle"], r["sym"]))
            uprice, ustale = None, None
            if u and u.get("last_bar_c"):
                uprice = u["last_bar_c"]
                ustale = (b["t"] - u["last_bar_t"]) / 60.0
            rows.append({"family": fam, "sym": r["sym"], "ep": r["ep"], "cycle": r["cycle"], "t": b["t"],
                         "utc": dt.datetime.fromtimestamp(b["t"], dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
                         "session": session(b["t"]), "rt_cost_pct": (1 - usdc_out / usdc_in) * 100,
                         "p_buy": p_buy, "p_sell": p_sell, "mid": mid, "under": uprice, "under_age_min": ustale,
                         "gap_pct": (mid / uprice - 1) * 100 if uprice else None,
                         "route_buy": b.get("route"), "route_sell": r.get("route"), "fee_bps": b.get("feeBps"),
                         "impact_buy": b.get("priceImpactPct")})
with open(f"{outdir}/xstocks_quotes_rt.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

g = collections.defaultdict(list)
for r in rows:
    g[(r["family"], r["sym"], r["ep"])].append(r)
summ = []
for (fam, sym, ep), rs in sorted(g.items()):
    def med(xs):
        xs = [x for x in xs if x is not None]
        return round(st.median(xs), 4) if xs else None
    reg = [r for r in rs if r["session"] == "regular"]
    off = [r for r in rs if r["session"] != "regular"]
    gap_reg = [r["gap_pct"] for r in reg if r["gap_pct"] is not None and r["under_age_min"] is not None and r["under_age_min"] < 5]
    gap_off = [r["gap_pct"] for r in off if r["gap_pct"] is not None]
    summ.append({"family": fam, "sym": sym, "ep": ep, "n": len(rs), "n_regular": len(reg), "n_off": len(off),
                 "rt_med_all": med([r["rt_cost_pct"] for r in rs]), "rt_med_regular": med([r["rt_cost_pct"] for r in reg]),
                 "rt_med_off": med([r["rt_cost_pct"] for r in off]),
                 "rt_min": round(min(r["rt_cost_pct"] for r in rs), 4), "rt_max": round(max(r["rt_cost_pct"] for r in rs), 4),
                 "gap_med_regular_fresh": med(gap_reg), "n_gap_reg": len(gap_reg),
                 "gap_absmed_regular_fresh": med([abs(x) for x in gap_reg]),
                 "gap_med_off_vs_last": med(gap_off), "gap_absmed_off": med([abs(x) for x in gap_off])})
with open(f"{outdir}/xstocks_summary.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(summ[0]))
    w.writeheader()
    w.writerows(summ)
for s in summ:
    print(s)

# ladder
lad = []
for fam_file, path in files.items():
    recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    base = {}
    for r in recs:
        if r["kind"] == "q" and r["ep"] == "build" and r["side"] == "buy" and r.get("status") == 200 and r.get("outAmount"):
            k = (r["cycle"], r["sym"])
            px = int(r["inAmount"]) / int(r["outAmount"])
            if r["size"] == 160:
                base[k] = px
            elif k in base:
                lad.append({"file": fam_file, "sym": r["sym"], "cycle": r["cycle"], "session": session(r["t"]), "size": r["size"],
                            "rel_to_160_pct": (px / base[k] - 1) * 100, "jup_impact": r.get("priceImpactPct")})
with open(f"{outdir}/xstocks_ladder.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(lad[0]) if lad else ["none"])
    w.writeheader()
    w.writerows(lad)
lg = collections.defaultdict(list)
for r in lad:
    lg[(r["file"], r["sym"], r["size"])].append(r["rel_to_160_pct"])
for k, v in sorted(lg.items()):
    print("LADDER", k, len(v), round(st.median(v), 4))
