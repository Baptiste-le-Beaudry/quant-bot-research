"""Build the markdown tables of XSTOCKS_<date>.md from xstocks_analyze.py outputs."""
import csv, sys, collections, statistics as st

sys.stdout.reconfigure(encoding="utf-8")
summ, ladder_csv = sys.argv[1], sys.argv[2]
UNIVERSE = set("ADBE AMD AMZN AVGO BA BABA BAC C COST CRM CSCO DIS META GOOGL INTC JNJ KO MA MCD MU NFLX PEP PG PLTR PYPL QCOM TXN UBER V WMT XOM".split())
rows = list(csv.DictReader(open(summ)))
by = collections.defaultdict(dict)
for r in rows:
    by[(r["family"], r["sym"])][r["ep"]] = r


def f(x):
    return "—" if x in (None, "") else f"{float(x):.3f}"


out = ["| Jeton | Émetteur | Univers A-Equity | n | `/build` AR médian % (min-max) | `/order` AR médian % | écart abs. médian au sous-jacent % |",
       "|---|---|---|---|---|---|---|"]
keyf = lambda k: min(float(v["rt_med_all"]) for v in by[k].values())
for k in sorted(by, key=keyf):
    fam, sym = k
    b, o = by[k].get("build"), by[k].get("order")
    bs = f"{f(b['rt_med_all'])} ({f(b['rt_min'])}-{f(b['rt_max'])})" if b else "pas de route"
    gap = (b or o)["gap_absmed_off"]
    n = (b or o)["n"]
    name = sym + ("x" if fam == "xstocks" else " (Backpack)")
    out.append(f"| {name} | {fam} | {'oui' if sym in UNIVERSE else 'non'} | {n} | {bs} | {f(o['rt_med_all']) if o else '—'} | {f(gap)} |")
print("\n".join(out))
print()
lad = collections.defaultdict(list)
for r in csv.DictReader(open(ladder_csv)):
    lad[(r["file"], r["sym"], int(r["size"]))].append(float(r["rel_to_160_pct"]))
syms = sorted({(a, b) for a, b, _ in lad})
out = ["| Jeton | 1 000 USD | 5 000 USD | 20 000 USD | taille max < 0,1 % |", "|---|---|---|---|---|"]
for a, s in syms:
    med = {z: st.median(lad[(a, s, z)]) for z in (1000, 5000, 20000) if (a, s, z) in lad}
    ok = [z for z in (1000, 5000, 20000) if z in med and med[z] < 0.1]
    mx = f"≥ {max(ok):,} USD".replace(",", " ") if ok else "< 1 000 USD"
    name = s + (" (Backpack)" if a == "bp" else "x")
    out.append(f"| {name} | " + " | ".join(f"{med[z]:+.3f} %" if z in med else "—" for z in (1000, 5000, 20000)) + f" | {mx} |")
print("\n".join(out))
