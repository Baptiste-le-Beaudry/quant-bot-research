"""Exp 61 step 0: Jupiter ``/build`` round-trip quotes for Solana tokens (public, read-only).

Preregistration: docs/agents/hypotheses/Exp-61.md. For JUP, JTO, PYTH, RAY, WIF, BONK
against USDC: BUY 116 USDC -> token on ``/swap/v2/build`` (no platform fee; placeholder
taker, nothing is signed or sent), then SELL exactly the units returned back to USDC.
One cycle (6 tokens x 2 requests) every ``--cycle-minutes`` (default 65), paced at one
request every 2 s keyless with one retry on HTTP 429 (same client as
paper_trading_bot/scripts/jupiter_quote_logger.py).

Stops when every token has ``--min-ok`` successful round trips AND the span between the
first and last cycle is >= ``--min-span-hours``, or after ``--max-cycles``.

  python scripts/agents/exp61_quote_collector.py --state <dir>/exp61_quotes.sqlite3

``summarize`` gives the per-token median round-trip cost (fraction of the 116 USD).
"""
from __future__ import annotations

import argparse
from contextlib import closing
import logging
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "paper_trading_bot" / "scripts"))
import jupiter_quote_logger as jql  # noqa: E402

# Verified 2026-10-07 with https://lite-api.jup.ag/tokens/v2/search (isVerified=True).
EXP61_TOKENS = {
    "JUPUSDT": ("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 6),
    "JTOUSDT": ("jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL", 9),
    "PYTHUSDT": ("HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", 6),
    "RAYUSDT": ("4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", 6),
    "WIFUSDT": ("EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 6),
    "1000BONKUSDT": ("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 5),
}
SIZE_USD = 116
EXCLUSION_THRESHOLD = 0.0010  # median AR cost > 0.10 % -> token excluded (preregistered)


class PatientQuoteLogger(jql.QuoteLogger):
    """On HTTP 429 or a transient 'Pool is disabled' 400: up to 3 retries after 10, 20, 30 s
    (the base client retries once after a short pause). Each stored row is the final attempt."""

    def request(self, endpoint, input_mint, output_mint, amount):
        result = self._request_once(endpoint, input_mint, output_mint, amount)
        for wait in (10.0, 20.0, 30.0):
            transient = result[1] == 429 or (result[1] == 400 and "Pool is disabled" in (result[4] or ""))
            if not transient:
                break
            self.sleep(wait)
            result = self._request_once(endpoint, input_mint, output_mint, amount)
        return result


def make_logger(db, session=None, **kw) -> "jql.QuoteLogger":
    jql.TOKENS.update(EXP61_TOKENS)
    return PatientQuoteLogger(db, session, symbols=tuple(EXP61_TOKENS), sizes=(SIZE_USD,),
                              endpoints=("build",), **kw)


def round_trips(db: sqlite3.Connection):
    """Pairs (cycle_ts, symbol, usdc_in, usdc_out) for complete BUY+SELL quotes."""
    rows = db.execute("""
        SELECT b.cycle_ts, b.symbol, b.in_units AS usdc_in, s.out_units AS usdc_out
        FROM quotes b JOIN quotes s
          ON s.cycle_ts=b.cycle_ts AND s.symbol=b.symbol AND s.endpoint=b.endpoint
         AND s.size_usd=b.size_usd AND s.side='SELL'
        WHERE b.side='BUY' AND b.error IS NULL AND s.error IS NULL
          AND b.endpoint='build' AND b.size_usd=?
        ORDER BY b.cycle_ts""", (SIZE_USD,)).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def summarize(db: sqlite3.Connection) -> dict:
    import statistics
    out = {}
    by = {}
    for cyc, sym, usdc_in, usdc_out in round_trips(db):
        by.setdefault(sym, []).append((cyc, 1.0 - usdc_out / usdc_in))
    for sym in EXP61_TOKENS:
        vals = by.get(sym, [])
        costs = [c for _, c in vals]
        ts = [t for t, _ in vals]
        n_err = db.execute("SELECT COUNT(*) FROM quotes WHERE symbol=? AND error IS NOT NULL",
                           (sym,)).fetchone()[0]
        med = statistics.median(costs) if costs else None
        out[sym] = {
            "n_ok": len(costs), "n_error_rows": n_err,
            "span_hours": (max(ts) - min(ts)) / 3.6e6 if ts else 0.0,
            "median_cost": med,
            "p10_cost": statistics.quantiles(costs, n=10)[0] if len(costs) >= 10 else None,
            "p90_cost": statistics.quantiles(costs, n=10)[-1] if len(costs) >= 10 else None,
            "min_cost": min(costs) if costs else None, "max_cost": max(costs) if costs else None,
            "excluded": (med is None) or (med > EXCLUSION_THRESHOLD),
        }
    return out


def done(summary: dict, min_ok: int, min_span_hours: float) -> bool:
    return all(v["n_ok"] >= min_ok and v["span_hours"] >= min_span_hours for v in summary.values())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--state", required=True)
    p.add_argument("--cycle-minutes", type=float, default=65.0)
    p.add_argument("--min-ok", type=int, default=22)
    p.add_argument("--min-span-hours", type=float, default=24.5)
    p.add_argument("--max-cycles", type=int, default=40)
    p.add_argument("--summarize", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with closing(jql.connect(a.state)) as db:
        if a.summarize:
            for k, v in summarize(db).items():
                print(k, v)
            return
        lock = jql.acquire_lock(a.state)
        try:
            lg = make_logger(db, min_interval_seconds=2.0, retry_429_seconds=5.0)
            done_cycles = db.execute("SELECT COUNT(DISTINCT cycle_ts) FROM quotes").fetchone()[0]
            last = db.execute("SELECT MAX(cycle_ts) FROM quotes").fetchone()[0]
            if last is not None:  # on restart keep the spacing from the last stored cycle
                target = last / 1000 + a.cycle_minutes * 60
                while time.time() < target:
                    time.sleep(min(30.0, max(0.0, target - time.time())))
            for i in range(done_cycles, a.max_cycles):
                t0 = time.time()
                cyc = int(t0 // 60 * 60 * 1000)
                try:
                    logging.info("cycle %d/%d: %s", i + 1, a.max_cycles, lg.cycle(cyc))
                except Exception:
                    logging.exception("cycle failed; continuing")
                s = summarize(db)
                logging.info("ok counts: %s", {k: (v["n_ok"], round(v["span_hours"], 1)) for k, v in s.items()})
                if done(s, a.min_ok, a.min_span_hours):
                    logging.info("stop rule met")
                    break
                # wall-clock schedule in short sleeps (a monotonic sleep stalls while the PC is asleep)
                target = t0 + a.cycle_minutes * 60
                while time.time() < target:
                    time.sleep(min(30.0, max(0.0, target - time.time())))
        finally:
            lock.close()


if __name__ == "__main__":
    main()
