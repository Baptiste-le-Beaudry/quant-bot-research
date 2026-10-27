import json, time, requests, sys
T = "ADBE AMD AMZN AVGO BA BABA BAC C COST CRM CSCO DIS META GOOGL INTC JNJ KO MA MCD MU NFLX PEP PG PLTR PYPL QCOM TXN UBER V WMT XOM SPY QQQ".split()
out = {}
for t in T:
    q = t + "x"
    r = requests.get("https://lite-api.jup.ag/tokens/v2/search", params={"query": q}, timeout=15)
    if r.status_code == 429:
        time.sleep(5)
        r = requests.get("https://lite-api.jup.ag/tokens/v2/search", params={"query": q}, timeout=15)
    d = r.json() if r.ok else []
    hits = [x for x in d if (x.get('symbol') or '').lower() == q.lower()]
    out[t] = [{k: x.get(k) for k in ('symbol', 'id', 'name', 'liquidity', 'isVerified', 'decimals', 'tokenProgram', 'dev', 'usdPrice')}
              | {'vol24': ((x.get('stats24h') or {}).get('buyVolume') or 0) + ((x.get('stats24h') or {}).get('sellVolume') or 0)} for x in hits]
    print(t, r.status_code, ascii([(h['symbol'], h['id'], h['name'], round(h['liquidity'] or 0), h['isVerified'], round(h['vol24']), h['decimals']) for h in out[t]]), flush=True)
    time.sleep(1.5)
json.dump(out, open(sys.argv[1], 'w'), indent=1)
