"""Exp 55 (PRED-FAV-001) - Kalshi favourite-longshot test, as preregistered in
docs/agents/hypotheses/Exp-55.md (commit 8c9d4ff).

Rule (frozen): buy at the best ask, 24 h before market close, any side (YES or NO)
whose ask is in [0.80, 0.95]; categories Economics / Financials / Climate and Weather;
hold to settlement; Kalshi taker fee as in force at the trade date.

Data (public, unauthenticated Kalshi Trade API v2):
  - /series                      -> series list + category + current fee_type/multiplier
  - /series/fee_changes          -> per-series fee change history (show_historical=true)
  - /events?series_ticker&status=settled -> all settled events (old ones too)
  - /markets?event_ticker / /historical/markets?event_ticker -> markets (result, open/close)
  - /series/{s}/markets/{t}/candlesticks or /historical/markets/{t}/candlesticks,
    period_interval=60 -> hourly OHLC of yes_bid / yes_ask quotes.
"Best ask at T-24h" = yes_ask.close (YES side) or 1 - yes_bid.close (NO side) of the last
hourly candle whose end_period_ts <= close_time - 24h (candles are only emitted for hours
in which the quote or trades changed, so the last candle's close is the standing quote).

Usage:
  py -I scripts/agents/exp55_kalshi_fav.py download   # writes C:/AAProjet/quant_bot_v1/data/kalshi/
  py -I scripts/agents/exp55_kalshi_fav.py analyze    # writes docs/agents/results/exp55/*.csv
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

API = "https://api.elections.kalshi.com/trade-api/v2"
DATA = r"C:\AAProjet\quant_bot_v1\data\kalshi"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(REPO, "docs", "agents", "results", "exp55")
CATEGORIES = ("Economics", "Financials", "Climate and Weather")
END_DATE = datetime(2026, 10, 1, tzinfo=timezone.utc)  # sample ends 2026-09-30
ORDER_CONTRACTS = 25  # fee rounding: one order of 25 contracts (~USD 20-24, 500 CAD bankroll / ~15 positions)

_lock = threading.Lock()
_last = [0.0]
MIN_INTERVAL = float(os.environ.get("KALSHI_MIN_INTERVAL", "0.30"))  # global throttle; public API 429s above ~3-4 req/s


STATS = {}


def _stat(k):
    with _lock:
        STATS[k] = STATS.get(k, 0) + 1
        tot = sum(STATS.values())
    if tot % 500 == 0:
        print("http stats", dict(STATS), flush=True)


def get(path: str, params: dict | None = None, tries: int = 8):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for k in range(tries):
        with _lock:
            wait = _last[0] + MIN_INTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "exp55-research"})
            with urllib.request.urlopen(req, timeout=60) as r:
                _stat("200")
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            _stat(str(e.code))
            if e.code in (400, 404):
                return None
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 + 2 * k)
                continue
            raise
        except Exception as e:
            _stat("exc:" + type(e).__name__)
            time.sleep(min(60, 2 ** k))
    raise RuntimeError("failed " + url)


def paged(path, params, key):
    out, cursor = [], None
    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        d = get(path, p)
        if not d:
            break
        page = d.get(key) or []
        out += page
        nxt = d.get("cursor")
        if not nxt or not page or nxt == cursor:
            break
        cursor = nxt
    return out


def cfile(ticker):
    """Windows-safe candle file name for a market ticker."""
    for ch in '<>:"/\\|?*':
        ticker = ticker.replace(ch, "_")
    return ticker + ".json"


def ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# --------------------------------------------------------------------------- download
def download():
    raw = os.path.join(DATA, "raw")
    for sub in ("events", "markets", "candles"):
        os.makedirs(os.path.join(raw, sub), exist_ok=True)
    sp = os.path.join(raw, "series_all.json")
    if not os.path.exists(sp):
        json.dump(get("/series"), open(sp, "w", encoding="utf-8"))
    fp = os.path.join(raw, "series_fee_changes.json")
    if not os.path.exists(fp):
        json.dump(get("/series/fee_changes", {"show_historical": "true"}), open(fp, "w", encoding="utf-8"))
    series = [s for s in json.load(open(sp, encoding="utf-8"))["series"] if s.get("category") in CATEGORIES]
    print("series in scope:", len(series), flush=True)
    cutoff = ts(get("/historical/cutoff")["market_settled_ts"])

    def do_events(s):
        ep = os.path.join(raw, "events", s["ticker"] + ".json")
        if os.path.exists(ep):
            return
        ev = paged("/events", {"series_ticker": s["ticker"], "status": "settled", "limit": 200}, "events")
        json.dump(ev, open(ep + ".tmp", "w", encoding="utf-8"))
        os.replace(ep + ".tmp", ep)
        print("events", s["ticker"], len(ev), round(time.time() - T0), dict(STATS), flush=True)

    T0 = time.time()
    for s_ in series:
        do_events(s_)
    nev = {s["ticker"]: len(json.load(open(os.path.join(raw, "events", s["ticker"] + ".json"), encoding="utf-8")))
           for s in series}
    print("events stage done: series with settled events =", sum(1 for v in nev.values() if v),
          "total settled events =", sum(nev.values()), flush=True)
    if os.environ.get("EXP55_STAGE") == "events":
        return

    def do_series(s):
        st = s["ticker"]
        mp = os.path.join(raw, "markets", st + ".json")
        if os.path.exists(mp):
            return
        ev = json.load(open(os.path.join(raw, "events", st + ".json"), encoding="utf-8"))
        if not ev:
            json.dump([], open(mp, "w"))
            return
        # markets: bulk by series first (both tiers), then per-event for events not covered
        mk = {}
        for path in ("/markets", "/historical/markets"):
            prm = {"series_ticker": st, "limit": 1000}
            if path == "/markets":
                prm["status"] = "settled"
            for m in paged(path, prm, "markets"):
                mk[m["ticker"]] = m
        have = {m["event_ticker"] for m in mk.values()}
        for e in ev:
            et = e["event_ticker"]
            if et in have:
                continue
            for path in ("/historical/markets", "/markets"):
                ms = paged(path, {"event_ticker": et, "limit": 1000}, "markets")
                for m in ms:
                    mk[m["ticker"]] = m
                if ms:
                    break
        for m in mk.values():
            m["_series"] = st
        json.dump(list(mk.values()), open(mp + ".tmp", "w", encoding="utf-8"))
        os.replace(mp + ".tmp", mp)
        print(f"{st}: events={len(ev)} markets={len(mk)} t={round(time.time() - T0)} {dict(STATS)}", flush=True)

    with ThreadPoolExecutor(2) as ex:
        list(ex.map(do_series, series))
    print("markets stage done", round(time.time() - T0), dict(STATS), flush=True)
    if os.environ.get("EXP55_STAGE") == "markets":
        return

    # candles for eligible markets (index built once; random order -> a partial download is a random sample)
    elig = load_index()
    limit = int(os.environ.get("EXP55_MAX_MARKETS", "0")) or len(elig)
    elig = elig[:limit]
    if os.environ.get("EXP55_TICKERS_FILE"):  # re-fetch a given list (used once to repair live-tier parsing)
        want = set(open(os.environ["EXP55_TICKERS_FILE"]).read().split())
        elig = [m for m in load_index() if m["ticker"] in want]
    print("eligible markets in index:", len(load_index()), "-> downloading first", len(elig), flush=True)
    cdir = os.path.join(raw, "candles")

    def do_candles(m):
        t = m["ticker"]
        p = os.path.join(cdir, cfile(t))
        if os.path.exists(p):
            return
        c = int(ts(m["close_time"]))
        o = int(ts(m["open_time"]))
        prm = {"start_ts": max(o, c - 120 * 86400), "end_ts": c - 3600, "period_interval": 60}
        settled = ts(m.get("settlement_ts") or m.get("expiration_time") or m["close_time"])
        order = [f"/historical/markets/{t}/candlesticks", f"/series/{m["series"]}/markets/{t}/candlesticks"]
        if settled and settled >= cutoff:
            order.reverse()
        d = None
        for path in order:
            d = get(path, prm)
            if d and d.get("candlesticks"):
                break
        cs = (d or {}).get("candlesticks") or []
        def cl(o):  # historical tier uses "close", live tier uses "close_dollars"
            o = o or {}
            return o.get("close", o.get("close_dollars"))
        slim = [[x["end_period_ts"], cl(x.get("yes_bid")), cl(x.get("yes_ask")),
                 cl(x.get("price")), x.get("volume", x.get("volume_fp"))] for x in cs]
        json.dump(slim, open(p + ".tmp", "w"))
        os.replace(p + ".tmp", p)

    n = [0]

    def wrap(m):
        do_candles(m)
        n[0] += 1
        if n[0] % 1000 == 0:
            print("candles", n[0], "/", len(elig), round(time.time() - T0), dict(STATS), flush=True)

    with ThreadPoolExecutor(3) as ex:
        list(ex.map(wrap, elig))
    print("download done", flush=True)


INDEX = os.path.join(DATA, "eligible_index.jsonl")
IDX_FIELDS = ("ticker", "event_ticker", "open_time", "close_time", "result", "settlement_ts", "expiration_time")


def build_index():
    """Parse the raw market lists once -> eligible markets, slim, shuffled with seed 55."""
    import random
    raw = os.path.join(DATA, "raw")
    series = {s["ticker"]: s for s in json.load(open(os.path.join(raw, "series_all.json"), encoding="utf-8"))["series"]
              if s.get("category") in CATEGORIES}
    out, nall = [], 0
    for st in sorted(series):
        mp = os.path.join(raw, "markets", st + ".json")
        if not os.path.exists(mp):
            continue
        for m in json.load(open(mp, encoding="utf-8")):
            nall += 1
            if eligible_market(m):
                r = {k: m.get(k) for k in IDX_FIELDS}
                r["series"] = st
                r["category"] = series[st]["category"]
                out.append(r)
    out.sort(key=lambda r: r["ticker"])
    random.Random(55).shuffle(out)
    with open(INDEX, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    print("markets parsed:", nall, "eligible:", len(out))


def load_index():
    return [json.loads(l) for l in open(INDEX, encoding="utf-8")]


def eligible_market(m):
    if m.get("result") not in ("yes", "no"):
        return False
    c, o = ts(m.get("close_time")), ts(m.get("open_time"))
    if not c or not o or c - o < 86400 or c >= END_DATE.timestamp():
        return False
    try:
        vol = float(m.get("volume_fp") or m.get("volume") or 0)
    except ValueError:
        vol = 0
    return vol > 0


# --------------------------------------------------------------------------- fees
def load_fee_history():
    d = json.load(open(os.path.join(DATA, "raw", "series_fee_changes.json"), encoding="utf-8"))
    h = {}
    for r in d.get("series_fee_change_arr", []):
        h.setdefault(r["series_ticker"], []).append((ts(r["scheduled_ts"]), r["fee_type"], r["fee_multiplier"]))
    for v in h.values():
        v.sort()
    return h


def fee_params(series, t, cur, hist):
    """(fee_type, multiplier) in force at time t, from the series fee-change history.
    No change recorded at all -> the series' current params. Changes recorded but none
    before t -> pre-change state unknown -> standard quadratic x1 (0.07*P*(1-P))."""
    ch = hist.get(series, [])
    state = None
    for when, ft, mul in ch:
        if when <= t:
            state = (ft, mul)
    if state is not None:
        return state
    if not ch:
        return cur
    return ("quadratic", 1)


def taker_fee_per_contract(price, ftype, mult, n=ORDER_CONTRACTS):
    if not ftype or not str(ftype).startswith("quadratic") or not mult:
        return 0.0
    raw = 0.07 * float(mult) * n * price * (1 - price)
    return math.ceil(round(raw * 100, 6)) / 100 / n  # rounded up to the cent per order


# --------------------------------------------------------------------------- analysis
def quote_at(candles, t_entry):
    last = None
    for row in candles:
        if row[0] <= t_entry:
            last = row
        else:
            break
    return last


def f(x):
    try:
        return None if x is None else float(x)
    except ValueError:
        return None


def build_trades():
    raw = os.path.join(DATA, "raw")
    allser = {s["ticker"]: s for s in json.load(open(os.path.join(raw, "series_all.json"), encoding="utf-8"))["series"]}
    hist = load_fee_history()
    rows = []
    stats = {"index": 0, "with_candles_file": 0, "empty_candles": 0}
    for m in load_index():
        stats["index"] += 1
        st = m["series"]
        s = allser[st]
        if True:
            cp = os.path.join(raw, "candles", cfile(m["ticker"]))
            if not os.path.exists(cp):
                continue
            stats["with_candles_file"] += 1
            candles = json.load(open(cp))
            if not candles:
                stats["empty_candles"] += 1
            c, o = ts(m["close_time"]), ts(m["open_time"])
            for win, lag in (("24h", 86400), ("1h", 3600)):
                te = c - lag
                if te < o:
                    continue
                q = quote_at(candles, te)
                if not q:
                    continue
                if te - q[0] > 30 * 86400:
                    pass  # standing quote, kept (flag below)
                yb, ya = f(q[1]), f(q[2])
                sides = []
                if ya is not None and 0 < ya < 1:
                    sides.append(("yes", ya))
                if yb is not None and 0 < yb < 1:
                    sides.append(("no", round(1 - yb, 4)))
                ft, mul = fee_params(st, te, (s.get("fee_type"), s.get("fee_multiplier")), hist)
                for side, ask in sides:
                    if not (0.70 <= ask <= 0.99):
                        continue
                    fee = taker_fee_per_contract(ask, ft, mul)
                    fee_unr = 0.07 * float(mul or 0) * ask * (1 - ask) if str(ft).startswith("quadratic") else 0.0
                    pay = 1.0 if m["result"] == side else 0.0
                    rows.append({
                        "window": win, "series": st, "category": s["category"], "event": m["event_ticker"],
                        "ticker": m["ticker"], "side": side, "ask": ask, "fee": fee, "fee_unrounded": fee_unr,
                        "fee_type": ft, "fee_mult": mul, "payout": pay,
                        "ret_net": (pay - ask - fee) / (ask + fee),
                        "ret_net_unrounded_fee": (pay - ask - fee_unr) / (ask + fee_unr),
                        "ret_gross": (pay - ask) / ask,
                        "spread": round(ya - yb, 4) if (ya is not None and yb is not None) else None,
                        "quote_age_h": round((te - q[0]) / 3600, 1),
                        "open_time": m["open_time"], "close_time": m["close_time"],
                        "term_days": round((c - o) / 86400, 2),
                        "close_year": datetime.fromtimestamp(c, timezone.utc).year,
                    })
    print("coverage:", stats, flush=True)
    return rows


def cluster_ci(vals, groups):
    n = len(vals)
    if n == 0:
        return (float("nan"),) * 4 + (0, 0)
    mu = sum(vals) / n
    agg = {}
    for v, g in zip(vals, groups):
        agg[g] = agg.get(g, 0.0) + (v - mu)
    G = len(agg)
    if G < 2:
        return mu, float("nan"), float("nan"), float("nan"), n, G
    var = G / (G - 1) * sum(x * x for x in agg.values()) / (n * n)
    se = math.sqrt(var)
    return mu, se, mu - 1.96 * se, mu + 1.96 * se, n, G


def summarize(rows, label, col="ret_net"):
    v = [r[col] for r in rows]
    mu, se, lo, hi, n, G = cluster_ci(v, [r["event"] for r in rows])
    wins = sum(r["payout"] for r in rows)
    return {"subset": label, "metric": col, "n_contracts": n, "n_events": G,
            "mean_ret": mu, "se_cluster": se, "ci95_lo": lo, "ci95_hi": hi,
            "win_rate": wins / n if n else float("nan"),
            "mean_ask": sum(r["ask"] for r in rows) / n if n else float("nan"),
            "mean_fee": sum(r["fee"] for r in rows) / n if n else float("nan")}


def in_period(r, a, b):
    t = ts(r["close_time"])
    return a.timestamp() <= t < b.timestamp()


def write_csv(path, rows):
    import csv
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def analyze():
    os.makedirs(OUT, exist_ok=True)
    rows = build_trades()
    write_csv(os.path.join(OUT, "exp55_trades_all.csv"), rows)
    P1 = (datetime(2021, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc))
    P2 = (datetime(2025, 4, 1, tzinfo=timezone.utc), END_DATE)
    bands = {"primary_0.80-0.95": (0.80, 0.95), "report_0.70-0.80": (0.70, 0.80), "report_0.95-0.99": (0.95, 0.99)}
    out = []
    for win in ("24h", "1h"):
        for bname, (lo, hi) in bands.items():
            if win == "1h" and bname != "primary_0.80-0.95":
                continue
            if bname.startswith("primary"):
                ok = lambda a: 0.80 <= a <= 0.95
            elif lo == 0.70:
                ok = lambda a: 0.70 <= a < 0.80
            else:
                ok = lambda a: 0.95 < a <= 0.99
            base = [r for r in rows if r["window"] == win and ok(r["ask"])]
            tag = f"{win}|{bname}"
            out.append(summarize(base, tag + "|all"))
            out.append(summarize([r for r in base if in_period(r, *P1)], tag + "|2021-2024"))
            out.append(summarize([r for r in base if in_period(r, *P2)], tag + "|2025-04..2026-09"))
            if win == "24h" and bname.startswith("primary"):
                out.append(summarize(base, tag + "|all", "ret_gross"))
                out.append(summarize(base, tag + "|all", "ret_net_unrounded_fee"))
                for cat in CATEGORIES:
                    out.append(summarize([r for r in base if r["category"] == cat], tag + "|cat=" + cat))
                for y in range(2021, 2027):
                    out.append(summarize([r for r in base if r["close_year"] == y], tag + f"|year={y}"))
                out.append(summarize([r for r in base if r["term_days"] >= 30], tag + "|term>=30d (descriptive)"))
                out.append(summarize([r for r in base if r["spread"] is not None and r["spread"] <= 0.05],
                                     tag + "|spread<=5c (descriptive)"))
                out.append(summarize([r for r in base if r["quote_age_h"] <= 24], tag + "|quote_age<=24h (descriptive)"))
                out.append(summarize([r for r in base if r["spread"] is not None and r["spread"] <= 0.20],
                                     tag + "|spread<=20c, Burgi filter (descriptive)"))
                out.append(summarize([r for r in base if r["spread"] is not None and r["spread"] <= 0.02],
                                     tag + "|spread<=2c (descriptive)"))
                out.append(summarize([r for r in base if r["close_time"].endswith(":00Z")],
                                     tag + "|excl. early-closed markets (descriptive)"))
                out.append(summarize([r for r in base if r["side"] == "no"], tag + "|side=NO (descriptive)"))
                out.append(summarize([r for r in base if r["side"] == "yes"], tag + "|side=YES (descriptive)"))
    write_csv(os.path.join(OUT, "exp55_summary.csv"), out)
    for o in out:
        print(f"{o['subset']:<60} {o['metric']:<22} n={o['n_contracts']:>6} ev={o['n_events']:>5} "
              f"mean={o['mean_ret']*100:+.2f}% CI=[{o['ci95_lo']*100:+.2f},{o['ci95_hi']*100:+.2f}] "
              f"win={o['win_rate']:.3f} ask={o['mean_ask']:.3f} fee={o['mean_fee']*100:.2f}c")


if __name__ == "__main__":
    {"download": download, "index": build_index, "analyze": analyze}[sys.argv[1]]()
