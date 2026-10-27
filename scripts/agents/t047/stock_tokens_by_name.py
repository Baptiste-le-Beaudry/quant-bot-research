import json, sys, time, requests
NAMES = {"ADBE": "Adobe", "AMD": "Advanced Micro Devices", "AMZN": "Amazon", "AVGO": "Broadcom", "BA": "Boeing",
         "BABA": "Alibaba", "BAC": "Bank of America", "C": "Citigroup", "COST": "Costco", "CRM": "Salesforce",
         "CSCO": "Cisco", "DIS": "Walt Disney", "META": "Meta Platforms", "GOOGL": "Alphabet", "INTC": "Intel",
         "JNJ": "Johnson", "KO": "Coca-Cola", "MA": "Mastercard", "MCD": "McDonald", "MU": "Micron",
         "NFLX": "Netflix", "PEP": "PepsiCo", "PG": "Procter", "PLTR": "Palantir", "PYPL": "PayPal",
         "QCOM": "Qualcomm", "TXN": "Texas Instruments", "UBER": "Uber", "V": "Visa", "WMT": "Walmart",
         "XOM": "Exxon", "SPY": "S&P 500", "QQQ": "Nasdaq"}
out = {}
for t, n in NAMES.items():
    r = requests.get("https://lite-api.jup.ag/tokens/v2/search", params={"query": n}, timeout=15)
    if r.status_code == 429:
        time.sleep(10)
        r = requests.get("https://lite-api.jup.ag/tokens/v2/search", params={"query": n}, timeout=15)
    d = r.json() if r.ok else []
    rows = [{"sym": x.get('symbol'), "id": x.get('id'), "name": x.get('name'), "liq": round(x.get('liquidity') or 0),
             "tags": x.get('tags'), "price": x.get('usdPrice')}
            for x in d if 'stocks' in (x.get('tags') or []) and x.get('isVerified')]
    out[t] = rows
    print(t, r.status_code, ascii([(z['sym'], z['name'], z['liq'], [g for g in z['tags'] if g in ('xstocks', 'ondo', 'backpack', 'prestocks', 'remora')] or z['tags']) for z in rows]), flush=True)
    time.sleep(3)
json.dump(out, open(sys.argv[1], "w"), indent=1)
