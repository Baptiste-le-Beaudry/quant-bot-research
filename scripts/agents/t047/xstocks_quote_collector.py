"""T-047 xStocks quote collector: public read-only Jupiter quotes + Yahoo underlying price.

No wallet, no signature, no transaction sent. Placeholder taker for /build.
Each cycle, per token: BUY 160 USDC -> token, SELL exact units back (round trip),
on /build (no platform fee) and /order (fee included). Every Nth cycle, a /build
BUY ladder (1k/5k/20k USD) for the more liquid tokens (price impact).
Underlying: Yahoo chart meta (regular/pre/post last price) per cycle.
Output: JSONL, one line per request.
"""
import json, sys, time, datetime as dt
import requests

OUT = sys.argv[1]
END_UTC = dt.datetime.fromisoformat(sys.argv[2])  # e.g. 2026-10-08T16:00:00+00:00
CYCLE_S = float(sys.argv[3]) if len(sys.argv) > 3 else 900
SPACING = 2.5
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TAKER = "11111111111111111111111111111111"
URL = {"build": "https://api.jup.ag/swap/v2/build", "order": "https://api.jup.ag/swap/v2/order"}
TOK = {  # official Backed xStocks (isVerified, mint prefix Xs), Jupiter token search 2026-10-07
    "ADBE": "XsDZMGEU8zadWFCkTtPBoPWYcUX3JHVmghnwf2Mve2q", "AMD": "XsXcJ6GZ9kVnjqGsjBnktRcuwMBmvKWh8S93RefZ1rF",
    "AMZN": "Xs3eBt7uRfJX8QUs4suhyU8p2M6DoUDrJyWBa8LLZsg", "AVGO": "XsgSaSvNSqLTtFuyWPBhK9196Xb9Bbdyjj4fH3cPJGo",
    "BABA": "XsJBX1kSf58ymLVKFSm2MkbLtsPiVRMWTvkvF7TSiVT", "BAC": "XswsQk4duEQmCbGzfqUUWYmi7pV7xpJ9eEmLHXCaEQP",
    "CRM": "XsczbcQ3zfcgAEt9qHQES8pxKAVG5rujPSHQEXi4kaN", "CSCO": "Xsr3pdLQyXvDJBFgpR5nexCEZwXvigb8wbPYp4YoNFf",
    "DIS": "Xsg93jDV656ULQ5u9yT2x5DS9b4xGD8aDCtfESSW6Bb", "META": "Xsa62P5mvPszXL1krVUnU5ar38bBSVcWAB6fmPCo5Zu",
    "GOOGL": "XsCPL9dNWBMvFtTmwcCA5v3xWPSMEBCszbQdiLLq6aN", "INTC": "XshPgPdXFRWB8tP1j82rebb2Q9rPgGX37RuqzohmArM",
    "JNJ": "XsGVi5eo1Dh2zUpic4qACcjuWGjNv8GCt3dm5XcX6Dn", "KO": "XsaBXg8dU5cPM6ehmVctMkVqoiRG2ZjMo1cyBJ3AykQ",
    "MCD": "XsqE9cRRpzxcGKDXj1BJ7Xmg4GRhZoyY1KpmGSxAWT2", "MU": "XsQLZycSZ7QnBBdBXQaTbQdiUcbRqjNJgyBGAMzhHav",
    "NFLX": "XsEH7wWfJJu2ZT3UCFeVfALnVA6CP5ur7Ee11KmzVpL", "PEP": "Xsv99frTRUeornyvCfvhnDesQDWuvns1M852Pez91vF",
    "PG": "XsYdjDjNUygZ7yGKfQaB6TxLh2gC6RRjzLtLAGJrhzV", "PLTR": "XsoBhf2ufR8fTyNSjqfU71DYGaE6Z3SUGAidpzriAA4",
    "PYPL": "XshWQWYVp5ff8CrAEsGmLVKD47nBWi3Ygn5v8wXK27G", "QCOM": "XsUUG8bjFN2KvzLTpzavvEKdAjMAeLTZiTeAQJ9uhvB",
    "TXN": "XsU4fHhJEFcrwNh4RYuHmWdaoCfsrWKEm4UEs3zTJwH", "UBER": "XsAsZLF4MmsvS1sDxRMrUz7REjHfwbC9UAMXSRBqgEB",
    "V": "XsqgsbXwWogGJsNcVZ3TyVouy2MbTkfCFhCGGGcQZ2p", "WMT": "Xs151QeqTCiuKtinzfRATnUESM2xTU6V9Wy8Vy538ci",
    "XOM": "XsaHND8sHyfMfsWPj6kSdd5VwvCayZvjYgKmmcNL5qh",
    "SPY": "XsoCS1TfEyfFhfvj8EtZ528L3CaKBDBRqRapnBbDF2W", "QQQ": "Xs8S1uUs1zvS2p7iwtsG3b6fkhpvmwz4GYU3gWAmWHZ",
}
LADDER_TOK = ("SPY", "QQQ", "GOOGL", "META", "AMZN", "MCD", "PLTR", "KO", "AVGO", "INTC")
LADDER_USD = (1000, 5000, 20000)
LADDER_EVERY = 4
S = requests.Session()
_last = [0.0]


def jget(url, params, spacing=SPACING):
    wait = _last[0] + spacing - time.time()
    if wait > 0:
        time.sleep(wait)
    status, err = None, "unknown"
    for attempt in range(3):
        t0 = time.time()
        try:
            r = S.get(url, params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            _last[0] = time.time()
            status = r.status_code
            if r.status_code == 429:
                err = "429"
                time.sleep(10 * (attempt + 1))
                continue
            try:
                body = r.json()
            except ValueError:
                body = {"error": r.text[:200]}
            return r.status_code, body, round((time.time() - t0) * 1000)
        except Exception as e:  # noqa
            _last[0] = time.time()
            err = repr(e)[:200]
            time.sleep(5)
    return status, {"error": err}, None


def slim(d):
    if not isinstance(d, dict):
        return d
    keep = ("inAmount", "outAmount", "priceImpactPct", "priceImpact", "feeBps", "platformFee", "router",
            "swapType", "mode", "gasless", "prioritizationFeeLamports", "signatureFeeLamports", "slippageBps",
            "error", "errorCode", "errorMessage", "inUsdValue", "outUsdValue")
    o = {k: d.get(k) for k in keep if k in d}
    o["route"] = " > ".join(f"{(l.get('swapInfo') or {}).get('label')}:{l.get('percent')}" for l in d.get("routePlan") or [])
    return o


def log(f, rec):
    f.write(json.dumps(rec) + "\n")
    f.flush()


def main():
    cycle = 0
    with open(OUT, "a", encoding="utf-8") as f:
        while dt.datetime.now(dt.timezone.utc) < END_UTC:
            c0 = time.time()
            cts = dt.datetime.now(dt.timezone.utc).isoformat()
            for sym in TOK:  # underlying
                st, d, lat = jget(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                                  {"interval": "1m", "range": "1d", "includePrePost": "true"}, spacing=0.4)
                try:
                    res = d["chart"]["result"][0]
                    m = res["meta"]
                    ts, cl = res.get("timestamp") or [], (res["indicators"]["quote"][0].get("close") or [])
                    last = [(t, c) for t, c in zip(ts, cl) if c is not None]
                    rec = {"kind": "under", "cycle": cycle, "cts": cts, "sym": sym, "rmp": m.get("regularMarketPrice"),
                           "rmt": m.get("regularMarketTime"), "last_bar_t": last[-1][0] if last else None,
                           "last_bar_c": last[-1][1] if last else None, "prev_close": m.get("previousClose")}
                except Exception as e:  # noqa
                    rec = {"kind": "under", "cycle": cycle, "cts": cts, "sym": sym, "status": st, "err": repr(e)[:200]}
                log(f, rec)
            for sym, mint in TOK.items():
                for ep in ("build", "order"):
                    p = {"inputMint": USDC, "outputMint": mint, "amount": 160_000_000}
                    if ep == "build":
                        p["taker"] = TAKER
                    t_req = time.time()
                    st, d, lat = jget(URL[ep], p)
                    b = slim(d)
                    log(f, {"kind": "q", "cycle": cycle, "cts": cts, "t": t_req, "sym": sym, "ep": ep, "side": "buy",
                            "size": 160, "status": st, "lat": lat, **(b or {})})
                    units = (d or {}).get("outAmount") if st == 200 and isinstance(d, dict) else None
                    if units and int(units) > 0:
                        p = {"inputMint": mint, "outputMint": USDC, "amount": int(units)}
                        if ep == "build":
                            p["taker"] = TAKER
                        t_req = time.time()
                        st, d, lat = jget(URL[ep], p)
                        log(f, {"kind": "q", "cycle": cycle, "cts": cts, "t": t_req, "sym": sym, "ep": ep, "side": "sell",
                                "size": 160, "status": st, "lat": lat, **(slim(d) or {})})
            if cycle % LADDER_EVERY == 0:
                for sym in LADDER_TOK:
                    for usd in LADDER_USD:
                        p = {"inputMint": USDC, "outputMint": TOK[sym], "amount": usd * 1_000_000, "taker": TAKER}
                        t_req = time.time()
                        st, d, lat = jget(URL["build"], p)
                        log(f, {"kind": "q", "cycle": cycle, "cts": cts, "t": t_req, "sym": sym, "ep": "build",
                                "side": "buy", "size": usd, "status": st, "lat": lat, **(slim(d) or {})})
            print(f"cycle {cycle} done {cts} in {time.time()-c0:.0f}s", flush=True)
            cycle += 1
            rest = CYCLE_S - (time.time() - c0)
            if rest > 0:
                time.sleep(rest)


if __name__ == "__main__":
    main()
