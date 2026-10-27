"""T-029 : liquidite USDC disponible sur Kamino (reserve principale) aux heures d entree P2.
Usage : python scripts/agents/t029_kamino_liquidity_at_entries.py <kamino_history_hourly.json> docs/agents/results/Exp-52_2026-10-07_ledgers.csv
Historique : GET https://api.kamino.finance/kamino-market/7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF/reserves/D6q6wuQSrifJKZYpR1M8R4YawnLDtDsMmWM1NbBmgJ59/metrics/history?env=mainnet-beta&start=2025-10-01T00:00:00Z&end=2026-10-07T00:00:00Z&frequency=hour
"""
import json, csv, sys, bisect
from datetime import datetime, timezone
h = json.load(open(sys.argv[1]))['history']
ts = [datetime.fromisoformat(x['timestamp'].replace('Z', '+00:00')) for x in h]
av = [float(x['metrics'].get('actualAvailableLiquidityUsd', 0)) for x in h]
ut = [float(x['metrics']['totalBorrows']) / float(x['metrics']['totalSupply']) for x in h]
apy = [x['metrics']['supplyInterestAPY'] for x in h]
res = []
for r in csv.DictReader(open(sys.argv[2])):
    if r['population'] != 'P2' or r['account'] != 'SOL_BTC_ETH' or r['variant'] != 'UNCAPPED':
        continue
    e = datetime.fromisoformat(r['entry_time'])
    i = bisect.bisect_right(ts, e) - 1
    if i < 0 or (e - ts[i]).total_seconds() > 7200:
        continue
    res.append((av[i], ut[i], apy[i], r['entry_time']))
print('entries matched', len(res))
res.sort()
print('min avail at entry', res[:3])
print('median util at entries %.3f vs all hours %.3f' % (sorted(x[1] for x in res)[len(res) // 2], sorted(ut)[len(ut) // 2]))
print('mean apy at entries %.4f vs all %.4f' % (sum(x[2] for x in res) / len(res), sum(apy) / len(apy)))
for day in ('2025-10-10', '2025-10-11', '2026-02-05', '2026-02-06'):
    v = [(a, u) for t, a, u in zip(ts, av, ut) if t.isoformat().startswith(day)]
    print(day, 'min avail %.1fM max util %.3f' % (min(a for a, _ in v) / 1e6, max(u for _, u in v)))
