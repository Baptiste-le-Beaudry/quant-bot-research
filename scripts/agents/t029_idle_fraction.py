"""T-029 : part du temps et du capital inactifs a partir des ledgers Exp 52/57.
Usage : python scripts/agents/t029_idle_fraction.py docs/agents/results/Exp-52_2026-10-07_ledgers.csv
"""
import csv, sys
from datetime import datetime
from collections import defaultdict

rows = defaultdict(list)
for r in csv.DictReader(open(sys.argv[1])):
    rows[(r['population'], r['account'], r['variant'])].append(r)
P = datetime.fromisoformat
for k, rs in sorted(rows.items()):
    ev = []
    for r in rs:
        e, x = P(r['entry_time']), P(r['exit_time'])
        f = float(r['notional_usd']) / float(r['equity_before'])
        ev.append((e, 1, f)); ev.append((x, -1, -f))
    ev.sort(key=lambda t: (t[0], t[1]))
    t0 = min(P(r['entry_time']) for r in rs); t1 = max(P(r['exit_time']) for r in rs)
    T = (t1 - t0).total_seconds()
    n = 0; fr = 0.0; last = t0; dep = 0.0; mx = 0; occ = defaultdict(float); opens = 0; maxfr = 0
    gaps = []; gap_start = t0
    for t, d, f in ev:
        dt = (t - last).total_seconds(); dep += fr * dt; occ[n] += dt; last = t
        if d == 1 and n == 0:
            opens += 1; gaps.append((t - gap_start).total_seconds() / 3600)
        n += d; fr += f; mx = max(mx, n); maxfr = max(maxfr, fr)
        if n == 0: gap_start = t
    yrs = T / 3.15576e7
    gaps.sort()
    med = gaps[len(gaps) // 2]
    print(k, 'trades', len(rs), 'years %.3f' % yrs, 'deployed %.4f' % (dep / T), 'idle %.4f' % (1 - dep / T),
          'maxpos', mx, 'maxfrac %.3f' % maxfr,
          'occ', {i: round(v / T, 5) for i, v in sorted(occ.items())},
          'busy_episodes', opens, 'per_year %.0f' % (opens / yrs), 'trades/yr %.0f' % (len(rs) / yrs),
          'median_idle_gap_h %.1f' % med, 'p10_gap_h %.2f' % gaps[len(gaps) // 10])
