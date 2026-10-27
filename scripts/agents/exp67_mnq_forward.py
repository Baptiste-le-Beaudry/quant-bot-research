"""Exp 67 -- paper forward of the "noise area" rule on MNQ (T-052, decision D-07).

Preregistration: docs/agents/hypotheses/Exp-67.md (frozen). The rule is NOT re-implemented here: every
signal quantity (grid, eligibility, sigma, bounds, VWAP, state machine, next-bar-open fill, USD pricing)
comes from scripts/agents/exp64_noise_momentum.py, imported as a module (reading frozen at 33b5a15).

Live specifics (the only things this file adds):
  * Feed: Dukascopy USATECH.IDX-USD 1-minute BID candles (same source/decoder as the Exp 64/65 CSV).
    Since 2026-10-08 the endpoint answers an AWS WAF challenge (HTTP 202, empty body) unless a
    Referer header is sent; with "Referer: https://www.dukascopy.com/" it answers 200 JSON.
  * Decision k (HH:00/HH:30 ET, 10:00..15:30) is taken as soon as a bar with index >= DECISION_IDX[k]
    has been seen; only bars <= DECISION_IDX[k] are used. latency_s = first-seen time of that bar
    minus the decision instant. latency > 300 s, or nothing after 300 s => decision SKIPPED and
    logged, never caught up (position unchanged).
  * Day eligibility is evaluated on the prefix known at decision time (the engine's criteria; the
    "15:59 bar present" criterion is unknowable live). Future minutes are filled with flat
    placeholders that cannot influence any quantity at or before the decision column.
  * History (sigma over the 14 previous eligible days, previous close) uses the completed-day
    Dukascopy data ("replay" bars), i.e. the same data the backtest uses.
  * Fills: open of the next bar (engine _exec_price), exit at the open of the 15:59 bar. 1 fictitious
    MNQ contract, 2.22 USD round trip (engine price_trades). PAPER ONLY: no key, no order, no broker.
  * Next day: the completed day is re-downloaded, live prices are compared with it (implementation
    alert > 1 tick mean) and the Exp 64 engine is re-run in batch on it (decision mismatches).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import logging
import logging.handlers
import os
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

_spec = importlib.util.spec_from_file_location("exp64", Path(__file__).with_name("exp64_noise_momentum.py"))
e64 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e64)

SPEC = e64.INSTRUMENTS["NASDAQ100"]           # MNQ: mult 2, tick 0.50 USD -> 2.22 USD round trip
TICK_PTS = 0.25                               # MNQ tick size in index points
CODE = "USATECH.IDX-USD"
API = "https://jetta.dukascopy.com/v1/candles/minute"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
           "Referer": "https://www.dukascopy.com/"}
MAX_LATENCY_S = 300.0
HISTORY_SESSIONS = 40
EXIT_WAIT_MIN = 10                            # finalize at 16:10 ET at the latest
COLLAPSE_USD = -4200.0
SKIP_WINDOW, SKIP_MAX = 20, 0.10
TRADED_WINDOW, TRADED_LO, TRADED_HI = 40, 0.30, 0.80
DEV_MAX_TICKS = 1.0
POLL_RETENTION_DAYS = 30
log = logging.getLogger("exp67")


# --------------------------------------------------------------------------- time helpers
def et(ts) -> pd.Timestamp:
    return pd.Timestamp(ts).tz_convert(e64.ET)


def decision_instant(day: dt.date, k: int) -> pd.Timestamp:
    """Decision k happens at the END of bar DECISION_IDX[k] (start-labelled), e.g. 10:00:00 ET."""
    return pd.Timestamp(f"{day} 09:30", tz=e64.ET) + pd.Timedelta(minutes=e64.DECISION_IDX[k] + 1)


def bar_index(ts_et: pd.Timestamp) -> int:
    return ts_et.hour * 60 + ts_et.minute - 570


# --------------------------------------------------------------------------- data feed
def decode(data: dict) -> pd.DataFrame:
    """Same delta decoding as quant_bot/data/download_dukascopy.decode_day (the CSV's downloader)."""
    mult = data["multiplier"]
    s = f"{mult:.10f}".rstrip("0")
    scale = len(s.split(".")[1]) if "." in s else 0
    ts = data["timestamp"]
    o, h, l, c = (round(data[k] / mult) for k in ("open", "high", "low", "close"))
    rows = []
    for i, d in enumerate(data.get("times") or []):
        ts += d * data["shift"]
        o += data["opens"][i]; h += data["highs"][i]; l += data["lows"][i]; c += data["closes"][i]
        rows.append((ts, round(o * mult, scale), round(h * mult, scale), round(l * mult, scale),
                     round(c * mult, scale), data["volumes"][i] * 1_000_000))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    return df


class DukascopyFeed:
    def __init__(self, timeout=20.0):
        self.timeout = timeout

    def _get(self, url, params=None):
        r = requests.get(url, params=params, headers=HEADERS, timeout=self.timeout)
        if r.status_code == 404:
            return None
        if r.status_code != 200 or not r.content:
            raise ConnectionError(f"dukascopy HTTP {r.status_code} waf={r.headers.get('x-amzn-waf-action')}")
        return r.json()

    def live(self, now: pd.Timestamp) -> pd.DataFrame:
        start = now.tz_convert("UTC").floor("D")
        data = self._get(f"{API}/{CODE}/BID", {"from": int(start.timestamp() * 1000)})
        return decode(data) if data and data.get("times") else decode({"times": [], "multiplier": 1,
                                                                        "timestamp": 0, "open": 0, "high": 0,
                                                                        "low": 0, "close": 0})

    def day(self, d: dt.date) -> pd.DataFrame | None:
        data = self._get(f"{API}/{CODE}/BID/{d.year}/{d.month}/{d.day}")
        if data is None or not data.get("times"):
            return None
        return decode(data)


class ReplayFeed:
    """Historical bars served as if live: a bar is visible once bar_start + 60 s + delay <= now."""

    def __init__(self, bars_utc: pd.DataFrame, delay_s: float = 4.0):
        self.bars = bars_utc.sort_index()
        self.delay = pd.Timedelta(seconds=delay_s)
        self._start = self.bars.index.as_unit("ns").asi8
        self._avail = self._start + int((pd.Timedelta(minutes=1) + self.delay).value)

    def live(self, now):
        now = now.tz_convert("UTC")
        lo = np.searchsorted(self._start, now.floor("D").value, side="left")
        hi = np.searchsorted(self._avail, now.value, side="right")      # avail is sorted like start
        return self.bars.iloc[lo:max(lo, hi)].copy()

    def day(self, d):
        b = self.bars[(self.bars.index >= pd.Timestamp(d, tz="UTC"))
                      & (self.bars.index < pd.Timestamp(d, tz="UTC") + pd.Timedelta(days=1))]
        return b.copy() if len(b) else None


def rth_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Keep bars 09:30..15:59 ET of NYSE sessions; adds et_date / idx columns."""
    if df is None or not len(df):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "et_date", "idx"])
    e = df.index.tz_convert(e64.ET)
    idx = (e.hour * 60 + e.minute).to_numpy() - 570
    keep = (idx >= 0) & (idx < e64.N_MIN)
    out = df.loc[keep].copy()
    out["et_date"] = [d.isoformat() for d in e[keep].date]
    out["idx"] = idx[keep]
    sess = {d: e64.is_session(dt.date.fromisoformat(d)) for d in set(out["et_date"])}
    return out.loc[np.array([sess[d] for d in out["et_date"]], dtype=bool)]


# --------------------------------------------------------------------------- storage
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS live_bars(ts_utc TEXT PRIMARY KEY, et_date TEXT, idx INTEGER, open REAL, high REAL,
  low REAL, close REAL, volume REAL, first_seen TEXT, latency_s REAL, n_revisions INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS live_bars_day ON live_bars(et_date);
CREATE TABLE IF NOT EXISTS replay_bars(ts_utc TEXT PRIMARY KEY, et_date TEXT, idx INTEGER, open REAL, high REAL,
  low REAL, close REAL, volume REAL);
CREATE INDEX IF NOT EXISTS replay_bars_day ON replay_bars(et_date);
CREATE TABLE IF NOT EXISTS replay_days(et_date TEXT PRIMARY KEY, fetched_at TEXT, n_bars INTEGER);
CREATE TABLE IF NOT EXISTS decisions(et_date TEXT, k INTEGER, label TEXT, decision_time TEXT, processed_at TEXT,
  status TEXT, reason TEXT, latency_s REAL, data_bar TEXT, price REAL, sigma REAL, ub REAL, lb REAL, vwap REAL,
  o930 REAL, prev_close REAL, pos_before INTEGER, pos_after INTEGER, fill_bar INTEGER, fill_px REAL,
  fill_seen_at TEXT, PRIMARY KEY(et_date, k));
CREATE TABLE IF NOT EXISTS trades(et_date TEXT, n INTEGER, side INTEGER, decision TEXT, entry_bar INTEGER,
  entry_px REAL, exit_bar INTEGER, exit_px REAL, exit_reason TEXT, gross_usd REAL, cost_usd REAL, net_usd REAL,
  fill_note TEXT, PRIMARY KEY(et_date, n));
CREATE TABLE IF NOT EXISTS days(et_date TEXT PRIMARY KEY, half_day INTEGER, n_decided INTEGER, n_late INTEGER,
  n_no_data INTEGER, n_not_tradable INTEGER, n_trades INTEGER, gross_usd REAL, cost_usd REAL, net_usd REAL,
  cum_net_usd REAL, drawdown_usd REAL, latency_med_s REAL, latency_max_s REAL, finalized_at TEXT);
CREATE TABLE IF NOT EXISTS replay_checks(et_date TEXT PRIMARY KEY, checked_at TEXT, n_prices INTEGER,
  mean_abs_dev_ticks REAL, max_abs_dev_ticks REAL, live_positions TEXT, engine_positions TEXT,
  decision_mismatches INTEGER, live_n_trades INTEGER, engine_n_trades INTEGER, live_net_usd REAL,
  engine_net_usd REAL, detail TEXT);
CREATE TABLE IF NOT EXISTS alerts(ts TEXT, et_date TEXT, kind TEXT, message TEXT, PRIMARY KEY(et_date, kind));
CREATE TABLE IF NOT EXISTS polls(ts TEXT, ok INTEGER, n_new INTEGER, last_bar TEXT, error TEXT);
"""


def connect(path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    db.execute("INSERT OR IGNORE INTO meta VALUES('created_at', ?)", (pd.Timestamp.now(tz="UTC").isoformat(),))
    db.execute("INSERT OR REPLACE INTO meta VALUES('rule', 'exp64_noise_momentum.py NASDAQ100->MNQ, "
               "1 contract, 2.22 USD RT, paper only')")
    db.commit()
    return db


# --------------------------------------------------------------------------- engine glue
def _bars_frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["ts_utc", "open", "high", "low", "close", "volume"])
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("ts_utc"), utc=True).dt.tz_convert(e64.ET), name="et")
    return df


def levels_asof(hist: pd.DataFrame, today_bars: pd.DataFrame, day: dt.date, cut: int):
    """Engine levels for `day` using only bars idx <= cut of that day (+ full history before it).

    Returns (grid, elig, lv, i) where i is the row of `day`. Columns after `cut` get flat placeholder
    bars (price = last close, volume 1): with the engine's start-to-column cumulative / forward-fill
    definitions they cannot change P, VWAP, sigma or the bounds at any column <= cut.
    """
    t = today_bars[[bar_index(x) <= cut for x in today_bars.index]] if len(today_bars) else today_bars
    df = pd.concat([hist, t]).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    grid = e64.build_grid(df)
    if not grid["dates"] or grid["dates"][-1] != day:
        return grid, None, None, None
    i = len(grid["dates"]) - 1
    c = grid["close"][i]
    present = np.flatnonzero(~np.isnan(c))
    if not len(present):
        return grid, None, None, None
    last = float(c[present[-1]])
    real_v = grid["volume"][i, present]
    for k in ("open", "high", "low", "close"):
        grid[k][i, cut + 1:] = last
    grid["volume"][i, cut + 1:] = 1.0
    elig = e64.eligibility(grid)
    prefix_zero = float((real_v == 0).mean())
    if prefix_zero > e64.MAX_ZERO_VOL_FRAC:
        elig.loc[i, "eligible"] = False
    elig.loc[i, "zero_vol_frac"] = prefix_zero
    lv = e64.compute_levels(grid, elig)
    return grid, elig, lv, i


def trades_from_changes(day, orow, changes):
    """Same loop as e64.simulate_noise, driven by the decisions actually taken live (skips respected)."""
    trades, notes, pos, entry = [], [], 0, None
    for k, new in changes:
        j, px = e64._exec_price(orow, e64.DECISION_IDX[k] + 1)
        if pos != 0:
            trades.append(e64._close(day, entry, j, px, "reverse" if new != 0 else "stop"))
            notes.append("")
        pos = new
        entry = (new, j, px, e64.DECISION_LABELS[k]) if new != 0 else None
    if pos != 0:
        px, note = orow[e64.EXIT_IDX], ""
        j = e64.EXIT_IDX
        if np.isnan(px):                                  # 15:59 bar missing live: last open before it
            ok = np.flatnonzero(~np.isnan(orow[:e64.EXIT_IDX]))
            j = int(ok[-1]); px = orow[j]; note = "exit_fallback_last_bar"
        trades.append(e64._close(day, entry, j, float(px), "eod"))
        notes.append(note)
    return trades, notes


# --------------------------------------------------------------------------- runner
class Runner:
    def __init__(self, db: sqlite3.Connection, feed, report_dir: Path):
        self.db, self.feed, self.report_dir = db, feed, Path(report_dir)
        self._last_maint = None

    # ---- history (completed days, the backtest's data)
    def _sessions_before(self, day: dt.date, n: int):
        out, d = [], day
        while len(out) < n:
            d = e64.previous_session(d)
            out.append(d)
        return out[::-1]

    def ensure_history(self, now: pd.Timestamp, today: dt.date):
        have = {r[0] for r in self.db.execute("SELECT et_date FROM replay_days")}
        for d in self._sessions_before(today, HISTORY_SESSIONS):
            if d.isoformat() in have:
                continue
            if now.tz_convert("UTC") < pd.Timestamp(d, tz="UTC") + pd.Timedelta(days=1, minutes=15):
                continue                                   # UTC day not complete yet
            try:
                df = self.feed.day(d)
            except Exception as exc:
                log.warning("history %s: %s", d, exc)
                return
            self._store_replay(d, df, now)

    def _store_replay(self, d, df, now):
        r = rth_rows(df)
        r = r[r["et_date"] == d.isoformat()]
        self.db.executemany("INSERT OR REPLACE INTO replay_bars VALUES(?,?,?,?,?,?,?,?)",
                            [(ts.isoformat(), x.et_date, int(x.idx), x.open, x.high, x.low, x.close, x.volume)
                             for ts, x in r.iterrows()])
        self.db.execute("INSERT OR REPLACE INTO replay_days VALUES(?,?,?)", (d.isoformat(), now.isoformat(), len(r)))
        self.db.commit()

    def history_frame(self, today: dt.date) -> pd.DataFrame:
        days = [d.isoformat() for d in self._sessions_before(today, HISTORY_SESSIONS)]
        q = ",".join("?" * len(days))
        rows = self.db.execute(f"SELECT ts_utc, open, high, low, close, volume FROM replay_bars WHERE et_date IN ({q})",
                               days).fetchall()
        have = {r[0] for r in self.db.execute(f"SELECT DISTINCT et_date FROM replay_bars WHERE et_date IN ({q})", days)}
        missing = [d for d in days if d not in have]
        if missing:                                       # fall back to live bars for days not yet replayed
            q2 = ",".join("?" * len(missing))
            rows += self.db.execute(f"SELECT ts_utc, open, high, low, close, volume FROM live_bars "
                                    f"WHERE et_date IN ({q2})", missing).fetchall()
        return _bars_frame(rows)

    def live_frame(self, day: dt.date) -> pd.DataFrame:
        rows = self.db.execute("SELECT ts_utc, open, high, low, close, volume FROM live_bars WHERE et_date=?",
                               (day.isoformat(),)).fetchall()
        return _bars_frame(rows)

    # ---- live polling
    def poll(self, now: pd.Timestamp, day: dt.date) -> int:
        try:
            df = self.feed.live(now)
        except Exception as exc:
            self.db.execute("INSERT INTO polls VALUES(?,?,?,?,?)", (now.isoformat(), 0, 0, None, str(exc)[:300]))
            self.db.commit()
            log.warning("poll failed: %s", exc)
            return 0
        df = df[df.index + pd.Timedelta(minutes=1) <= now]              # complete bars only
        r = rth_rows(df)
        r = r[r["et_date"] == day.isoformat()]
        known = {row[0]: row[1:] for row in self.db.execute(
            "SELECT ts_utc, open, high, low, close, volume FROM live_bars WHERE et_date=?", (day.isoformat(),))}
        new, now_iso = 0, now.isoformat()
        arr = r[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
        for ts, ed, ix, vals in zip(r.index, r["et_date"], r["idx"], arr):
            key = ts.isoformat()
            vals = tuple(float(v) for v in vals)
            if key not in known:
                lat = (now - (ts + pd.Timedelta(minutes=1))).total_seconds()
                self.db.execute("INSERT INTO live_bars VALUES(?,?,?,?,?,?,?,?,?,?,0)",
                                (key, ed, int(ix), *vals, now_iso, lat))
                new += 1
            elif any(abs(a - b) > 1e-9 for a, b in zip(known[key], vals)):
                self.db.execute("UPDATE live_bars SET n_revisions=n_revisions+1 WHERE ts_utc=?", (key,))
        last = r.index.max().isoformat() if len(r) else None
        self.db.execute("INSERT INTO polls VALUES(?,?,?,?,?)", (now.isoformat(), 1, new, last, None))
        self.db.commit()
        return new

    # ---- decisions
    def _position(self, day: dt.date) -> int:
        row = self.db.execute("SELECT pos_after FROM decisions WHERE et_date=? AND status='decided' "
                              "ORDER BY k DESC LIMIT 1", (day.isoformat(),)).fetchone()
        return int(row[0]) if row else 0

    def _record(self, day, k, now, status, reason=None, **kw):
        cols = ["latency_s", "data_bar", "price", "sigma", "ub", "lb", "vwap", "o930", "prev_close",
                "pos_before", "pos_after"]
        vals = [kw.get(c) for c in cols]
        self.db.execute("INSERT OR IGNORE INTO decisions(et_date,k,label,decision_time,processed_at,status,reason,"
                        + ",".join(cols) + ") VALUES(" + ",".join("?" * (7 + len(cols))) + ")",
                        (day.isoformat(), k, e64.DECISION_LABELS[k], decision_instant(day, k).isoformat(),
                         now.isoformat(), status, reason, *vals))
        self.db.commit()

    def decide(self, now: pd.Timestamp, day: dt.date):
        done = {r[0] for r in self.db.execute("SELECT k FROM decisions WHERE et_date=?", (day.isoformat(),))}
        for k, di in enumerate(e64.DECISION_IDX):
            if k in done:
                continue
            D = decision_instant(day, k)
            if now < D:
                break
            row = self.db.execute("SELECT ts_utc, first_seen FROM live_bars WHERE et_date=? AND idx>=? "
                                  "ORDER BY first_seen, idx LIMIT 1", (day.isoformat(), di)).fetchone()
            pos = self._position(day)
            if row is None:
                if (now - D).total_seconds() > MAX_LATENCY_S:
                    self._record(day, k, now, "skipped_no_data", "no bar at/after decision within 300 s",
                                 pos_before=pos, pos_after=pos)
                    log.warning("%s %s skipped: no data", day, e64.DECISION_LABELS[k])
                    continue
                break                                       # wait for data (decisions are sequential)
            latency = (pd.Timestamp(row[1]) - D).total_seconds()
            if latency > MAX_LATENCY_S or (now - D).total_seconds() > MAX_LATENCY_S:
                why = (f"data latency {latency:.0f} s > 300 s" if latency > MAX_LATENCY_S
                       else f"runner processed {(now - D).total_seconds():.0f} s after the decision time")
                self._record(day, k, now, "skipped_late", why,
                             latency_s=latency, data_bar=row[0], pos_before=pos, pos_after=pos)
                log.warning("%s %s skipped: %s", day, e64.DECISION_LABELS[k], why)
                continue
            grid, elig, lv, i = levels_asof(self.history_frame(day), self.live_frame(day), day, di)
            if lv is None or not lv["tradable"][i]:
                reason = "no RTH bar today" if lv is None else (
                    "prefix not eligible" if not elig.loc[i, "eligible"] else "sigma/VWAP undefined (history)")
                extra = {}
                if lv is not None:
                    extra = dict(price=float(lv["P"][i, k]), sigma=float(lv["sigma"][i, k]), ub=float(lv["ub"][i, k]),
                                 lb=float(lv["lb"][i, k]), vwap=float(lv["vwap"][i, k]), o930=float(lv["o930"][i]),
                                 prev_close=float(elig.loc[i, "prev_close"]))
                self._record(day, k, now, "not_tradable", reason, latency_s=latency, data_bar=row[0],
                             pos_before=pos, pos_after=pos, **extra)
                continue
            new = e64.next_state(pos, lv["P"][i, k], lv["ub"][i, k], lv["lb"][i, k], lv["vwap"][i, k])
            self._record(day, k, now, "decided", None, latency_s=latency, data_bar=row[0],
                         price=float(lv["P"][i, k]), sigma=float(lv["sigma"][i, k]), ub=float(lv["ub"][i, k]),
                         lb=float(lv["lb"][i, k]), vwap=float(lv["vwap"][i, k]), o930=float(lv["o930"][i]),
                         prev_close=float(elig.loc[i, "prev_close"]), pos_before=pos, pos_after=int(new))
            log.info("%s %s P=%.3f ub=%.3f lb=%.3f vwap=%.3f pos %d->%d lat=%.1fs", day, e64.DECISION_LABELS[k],
                     lv["P"][i, k], lv["ub"][i, k], lv["lb"][i, k], lv["vwap"][i, k], pos, new, latency)

    def resolve_fills(self, now, day):
        rows = self.db.execute("SELECT k FROM decisions WHERE et_date=? AND status='decided' AND pos_after<>pos_before "
                               "AND fill_px IS NULL", (day.isoformat(),)).fetchall()
        if not rows:
            return
        orow = self._open_row(day)
        for (k,) in rows:
            nxt = e64.DECISION_IDX[k] + 1
            if np.isnan(orow[nxt:]).all():
                continue
            j, px = e64._exec_price(orow, nxt)
            self.db.execute("UPDATE decisions SET fill_bar=?, fill_px=?, fill_seen_at=? WHERE et_date=? AND k=?",
                            (int(j), float(px), now.isoformat(), day.isoformat(), k))
        self.db.commit()

    def _open_row(self, day, source="live_bars"):
        o = np.full(e64.N_MIN, np.nan)
        for idx, v in self.db.execute(f"SELECT idx, open FROM {source} WHERE et_date=?", (day.isoformat(),)):
            o[int(idx)] = v
        return o

    # ---- end of day
    def finalize(self, now, day):
        if self.db.execute("SELECT 1 FROM days WHERE et_date=?", (day.isoformat(),)).fetchone():
            return
        half = day in e64.nyse_half_days(day.year)
        dec = pd.read_sql_query("SELECT * FROM decisions WHERE et_date=? ORDER BY k", self.db, params=(day.isoformat(),))
        orow = self._open_row(day)
        fill_note = ""
        if not np.isfinite(orow).any():
            orow = self._open_row(day, "replay_bars"); fill_note = "fills_from_replay"
        d = dec[dec["status"] == "decided"]
        changes = [(int(r.k), int(r.pos_after)) for r in d.itertuples() if r.pos_after != r.pos_before]
        trades, notes = trades_from_changes(day, orow, changes) if np.isfinite(orow).any() else ([], [])
        tr = e64.price_trades(trades, SPEC)
        self.db.execute("DELETE FROM trades WHERE et_date=?", (day.isoformat(),))
        for n, (t, note) in enumerate(zip(tr.itertuples(), notes)):
            self.db.execute("INSERT INTO trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (day.isoformat(), n, int(t.side), t.decision, int(t.entry_bar), float(t.entry_px),
                             int(t.exit_bar), float(t.exit_px), t.exit_reason, float(t.gross_usd), float(t.cost_usd),
                             float(t.net_usd), (note + " " + fill_note).strip() or None))
        prev = self.db.execute("SELECT cum_net_usd FROM days WHERE et_date<? ORDER BY et_date DESC LIMIT 1",
                               (day.isoformat(),)).fetchone()
        net = float(tr["net_usd"].sum()) if len(tr) else 0.0
        cum = (prev[0] if prev else 0.0) + net
        series = [r[0] for r in self.db.execute("SELECT net_usd FROM days WHERE et_date<? ORDER BY et_date",
                                                (day.isoformat(),))] + [net]
        eq = np.cumsum(series)
        ddown = float(eq[-1] - max(0.0, eq.max()))
        lat = dec.loc[dec["latency_s"].notna(), "latency_s"]
        self.db.execute("INSERT INTO days VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (day.isoformat(), int(half), int((dec.status == "decided").sum()),
                         int((dec.status == "skipped_late").sum()), int((dec.status == "skipped_no_data").sum()),
                         int((dec.status == "not_tradable").sum()), int(len(tr)),
                         float(tr["gross_usd"].sum()) if len(tr) else 0.0,
                         float(tr["cost_usd"].sum()) if len(tr) else 0.0, net, cum, ddown,
                         float(lat.median()) if len(lat) else None, float(lat.max()) if len(lat) else None,
                         now.isoformat()))
        self.db.commit()
        log.info("finalized %s: %d trades, net %.2f USD, cum %.2f", day, len(tr), net, cum)
        self.check_alerts(now, day)
        self.write_report(day)

    # ---- next-day replay check
    def replay_check(self, now, day):
        if self.db.execute("SELECT 1 FROM replay_checks WHERE et_date=?", (day.isoformat(),)).fetchone():
            return
        if not self.db.execute("SELECT 1 FROM replay_days WHERE et_date=? AND n_bars>0", (day.isoformat(),)).fetchone():
            return
        dec = pd.read_sql_query("SELECT * FROM decisions WHERE et_date=? ORDER BY k", self.db, params=(day.isoformat(),))
        rows = self.db.execute("SELECT ts_utc, open, high, low, close, volume FROM replay_bars WHERE et_date IN (%s)"
                               % ",".join("?" * (HISTORY_SESSIONS + 1)),
                               [x.isoformat() for x in self._sessions_before(day, HISTORY_SESSIONS)] + [day.isoformat()]
                               ).fetchall()
        df = _bars_frame(rows)
        grid = e64.build_grid(df)
        if not grid["dates"] or grid["dates"][-1] != day:
            return
        elig = e64.eligibility(grid)
        lv = e64.compute_levels(grid, elig)
        i = len(grid["dates"]) - 1
        cf = e64._ffill_rows(grid["close"])
        devs, detail = [], []
        for r in dec[dec["status"] == "decided"].itertuples():
            rp = float(cf[i, e64.DECISION_IDX[r.k]])
            devs.append(abs(r.price - rp) / TICK_PTS)
            if r.fill_px is not None and not pd.isna(r.fill_px):
                ro = grid["open"][i, int(r.fill_bar)]
                if np.isfinite(ro):
                    devs.append(abs(r.fill_px - ro) / TICK_PTS)
        eng_pos, pos = [], 0
        if lv["tradable"][i]:
            for k in range(len(e64.DECISION_IDX)):
                pos = e64.next_state(pos, lv["P"][i, k], lv["ub"][i, k], lv["lb"][i, k], lv["vwap"][i, k])
                eng_pos.append(int(pos))
        live_pos = {int(r.k): int(r.pos_after) for r in dec.itertuples() if r.status == "decided"}
        mism = sum(1 for k, p in live_pos.items() if (eng_pos[k] if eng_pos else 0) != p)
        etr = [t for t in e64.simulate_noise(grid, elig, lv) if t["date"] == day]
        etp = e64.price_trades(etr, SPEC)
        ltr = self.db.execute("SELECT COUNT(*), COALESCE(SUM(net_usd),0) FROM trades WHERE et_date=?",
                              (day.isoformat(),)).fetchone()
        detail = {"engine_tradable": bool(lv["tradable"][i]), "engine_eligible": bool(elig.loc[i, "eligible"]),
                  "engine_trades": etp[["side", "decision", "entry_px", "exit_px", "exit_reason", "net_usd"]]
                  .to_dict("records") if len(etp) else []}
        self.db.execute("INSERT INTO replay_checks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (day.isoformat(), now.isoformat(), len(devs), float(np.mean(devs)) if devs else None,
                         float(np.max(devs)) if devs else None, json.dumps(live_pos), json.dumps(eng_pos), mism,
                         int(ltr[0]), int(len(etp)), float(ltr[1]), float(etp["net_usd"].sum()) if len(etp) else 0.0,
                         json.dumps(detail, default=str)))
        self.db.commit()
        if devs and np.mean(devs) > DEV_MAX_TICKS:
            self.alert(now, day, "IMPL_PRICE_DEVIATION",
                       f"mean |live - Dukascopy replay| = {np.mean(devs):.2f} ticks > 1 tick ({len(devs)} prices)")
        self.write_report(day)

    # ---- alerts (Exp-67 stop rule)
    def alert(self, now, day, kind, msg):
        cur = self.db.execute("INSERT OR IGNORE INTO alerts VALUES(?,?,?,?)", (now.isoformat(), day.isoformat(), kind, msg))
        self.db.commit()
        if cur.rowcount:
            log.error("ALERT %s %s: %s", day, kind, msg)

    def check_alerts(self, now, day):
        days = pd.read_sql_query("SELECT * FROM days WHERE half_day=0 ORDER BY et_date", self.db)
        if not len(days):
            return
        w = days.tail(SKIP_WINDOW)
        tot = 12 * len(w)
        skipped = int((w["n_late"] + w["n_no_data"]).sum())
        if len(w) >= SKIP_WINDOW and skipped / tot > SKIP_MAX:
            self.alert(now, day, "IMPL_SKIPPED_DECISIONS", f"{skipped}/{tot} decisions skipped over {len(w)} days")
        w = days.tail(TRADED_WINDOW)
        frac = float((w["n_trades"] > 0).mean())
        if len(w) >= TRADED_WINDOW and not (TRADED_LO <= frac <= TRADED_HI):
            self.alert(now, day, "IMPL_TRADED_DAYS", f"traded-day fraction {frac:.0%} over {len(w)} sessions "
                                                     f"outside [30%, 80%]")
        cum = float(days["cum_net_usd"].iloc[-1])
        if cum <= COLLAPSE_USD:
            self.alert(now, day, "COLLAPSE", f"cumulative net {cum:.0f} USD <= -4200 USD per contract: track CLOSED")

    # ---- reporting
    def summary(self) -> dict:
        days = pd.read_sql_query("SELECT * FROM days ORDER BY et_date", self.db)
        full = days[days["half_day"] == 0]
        chk = pd.read_sql_query("SELECT * FROM replay_checks ORDER BY et_date", self.db)
        al = pd.read_sql_query("SELECT * FROM alerts ORDER BY ts", self.db)
        lat = pd.read_sql_query("SELECT latency_s FROM decisions WHERE latency_s IS NOT NULL", self.db)["latency_s"]
        w20, w40 = full.tail(SKIP_WINDOW), full.tail(TRADED_WINDOW)
        return {
            "sessions_finalized": int(len(days)), "first_day": days["et_date"].min() if len(days) else None,
            "last_day": days["et_date"].max() if len(days) else None,
            "n_trades": int(days["n_trades"].sum()) if len(days) else 0,
            "cum_net_usd": float(days["cum_net_usd"].iloc[-1]) if len(days) else 0.0,
            "max_drawdown_usd": float(days["drawdown_usd"].min()) if len(days) else 0.0,
            "skipped_frac_last20": float((w20["n_late"] + w20["n_no_data"]).sum() / (12 * len(w20))) if len(w20) else None,
            "days_in_skip_window": int(len(w20)),
            "traded_day_frac_last40": float((w40["n_trades"] > 0).mean()) if len(w40) else None,
            "days_in_traded_window": int(len(w40)),
            "decision_latency_s_median": float(lat.median()) if len(lat) else None,
            "decision_latency_s_p95": float(lat.quantile(0.95)) if len(lat) else None,
            "decision_latency_s_max": float(lat.max()) if len(lat) else None,
            "replay_mean_dev_ticks": float(chk["mean_abs_dev_ticks"].mean()) if len(chk) and chk["mean_abs_dev_ticks"].notna().any() else None,
            "replay_decision_mismatches": int(chk["decision_mismatches"].sum()) if len(chk) else 0,
            "alerts": al[["et_date", "kind", "message"]].to_dict("records"),
            "status": "CLOSED (collapse alert)" if (al["kind"] == "COLLAPSE").any() else "RUNNING",
        }

    def write_report(self, day: dt.date):
        self.report_dir.mkdir(parents=True, exist_ok=True)
        s = self.summary()
        dec = pd.read_sql_query("SELECT label, status, reason, latency_s, price, ub, lb, vwap, pos_before, pos_after, "
                                "fill_bar, fill_px FROM decisions WHERE et_date=? ORDER BY k", self.db,
                                params=(day.isoformat(),))
        tr = pd.read_sql_query("SELECT side, decision, entry_bar, entry_px, exit_bar, exit_px, exit_reason, gross_usd, "
                               "cost_usd, net_usd, fill_note FROM trades WHERE et_date=? ORDER BY n", self.db,
                               params=(day.isoformat(),))
        drow = self.db.execute("SELECT * FROM days WHERE et_date=?", (day.isoformat(),)).fetchone()
        chk = self.db.execute("SELECT n_prices, mean_abs_dev_ticks, max_abs_dev_ticks, decision_mismatches, "
                              "live_n_trades, engine_n_trades, live_net_usd, engine_net_usd FROM replay_checks "
                              "WHERE et_date=?", (day.isoformat(),)).fetchone()

        def table(df):
            if not len(df):
                return "(aucun)\n"
            df = df.copy()
            for c in df.columns:
                if df[c].dtype.kind == "f":
                    df[c] = df[c].map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
            head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
            return head + "".join("| " + " | ".join("" if v is None else str(v) for v in r) + " |\n"
                                  for r in df.itertuples(index=False))

        txt = [f"# Exp 67 — forward papier MNQ (zone de bruit) — {day}\n",
               "Papier uniquement, 1 contrat MNQ fictif, coût 2,22 USD aller-retour, remplissage théorique à l'open "
               "de la barre suivante, sortie à l'open de la barre 15:59 ET. Catégorie : **forward en cours** "
               "(ne prouve pas l'edge, voir Exp-67.md).\n",
               "## Journée\n"]
        if drow:
            txt.append(f"- Décisions prises / en retard / sans données / non négociables : {drow[2]} / {drow[3]} / "
                       f"{drow[4]} / {drow[5]} ; trades {drow[6]} ; brut {drow[7]:.2f} ; coûts {drow[8]:.2f} ; "
                       f"**net {drow[9]:.2f} USD** ; cumul {drow[10]:.2f} ; drawdown {drow[11]:.2f}\n")
            if drow[1]:
                txt.append("- Demi-séance : exclue par la règle (aucune décision).\n")
        else:
            txt.append("- Journée non finalisée.\n")
        txt += ["\n## Décisions\n", table(dec), "\n## Trades\n", table(tr), "\n## Contrôle rejoué (lendemain)\n"]
        if chk:
            txt.append(f"- Prix comparés {chk[0]}, écart moyen {chk[1] if chk[1] is not None else float('nan'):.2f} tick, "
                       f"max {chk[2] if chk[2] is not None else float('nan'):.2f} ; décisions différentes du moteur "
                       f"Exp 64 rejoué : {chk[3]} ; trades live/moteur {chk[4]}/{chk[5]} ; net live/moteur "
                       f"{chk[6]:.2f}/{chk[7]:.2f} USD\n")
        else:
            txt.append("- Pas encore disponible (données Dukascopy du jour complet publiées après 00:00 UTC).\n")
        txt += ["\n## Cumul et règle d'arrêt\n", "```json\n" + json.dumps(s, indent=2, default=str,
                                                                       ensure_ascii=False) + "\n```\n"]
        body = "".join(txt)
        (self.report_dir / f"MNQ_{day}.md").write_text(body, encoding="utf-8")
        (self.report_dir / "LATEST.md").write_text(body, encoding="utf-8")
        (self.report_dir / "summary.json").write_text(json.dumps(s, indent=2, default=str), encoding="utf-8")

    # ---- maintenance
    def retention(self, now):
        cut = (now - pd.Timedelta(days=POLL_RETENTION_DAYS)).isoformat()
        self.db.execute("DELETE FROM polls WHERE ts < ?", (cut,))
        self.db.commit()

    def backfill_missing_days(self, now, today):
        """Sessions since the start day with no record at all (runner down): 12 skipped decisions each."""
        row = self.db.execute("SELECT value FROM meta WHERE key='start_day'").fetchone()
        if not row:
            return
        d = dt.date.fromisoformat(row[0])
        while d < today:
            if e64.is_session(d) and not self.db.execute("SELECT 1 FROM days WHERE et_date=?",
                                                         (d.isoformat(),)).fetchone():
                if d not in e64.nyse_half_days(d.year):
                    self.decide(now, d)
                self.finalize(now, d)
            d += dt.timedelta(days=1)

    def maintenance(self, now, today):
        self.ensure_history(now, today)
        self.backfill_missing_days(now, today)
        pending = [r[0] for r in self.db.execute(
            "SELECT DISTINCT et_date FROM decisions WHERE et_date NOT IN (SELECT et_date FROM days)")]
        for d in pending:
            dd = dt.date.fromisoformat(d)
            if dd < today or et(now) >= pd.Timestamp(f"{dd} 16:00", tz=e64.ET) + pd.Timedelta(minutes=EXIT_WAIT_MIN):
                self.finalize(now, dd)
        for (d,) in self.db.execute("SELECT et_date FROM days WHERE et_date NOT IN (SELECT et_date FROM replay_checks)"
                                    ).fetchall():
            dd = dt.date.fromisoformat(d)
            if now.tz_convert("UTC") >= pd.Timestamp(dd, tz="UTC") + pd.Timedelta(days=1, minutes=15):
                if not self.db.execute("SELECT 1 FROM replay_days WHERE et_date=?", (d,)).fetchone():
                    try:
                        self._store_replay(dd, self.feed.day(dd), now)
                    except Exception as exc:
                        log.warning("replay fetch %s: %s", d, exc)
                        continue
                self.replay_check(now, dd)
        self.retention(now)

    # ---- one tick of the main loop
    def step(self, now: pd.Timestamp) -> float:
        """Returns the number of seconds to sleep before the next step."""
        n = et(now)
        today = n.date()
        if self._last_maint is None or (now - self._last_maint).total_seconds() >= 600:
            self.maintenance(now, today)
            self._last_maint = now
        if not e64.is_session(today):
            return 60.0
        start = pd.Timestamp(f"{today} 09:29", tz=e64.ET)
        end = pd.Timestamp(f"{today} 16:00", tz=e64.ET) + pd.Timedelta(minutes=EXIT_WAIT_MIN)
        if today in e64.nyse_half_days(today.year):
            if n >= end and not self.db.execute("SELECT 1 FROM days WHERE et_date=?", (today.isoformat(),)).fetchone():
                self.finalize(now, today)
            return 60.0
        if n < start:
            return 60.0
        if n <= end + pd.Timedelta(minutes=1):
            self.poll(now, today)
            self.decide(now, today)
            self.resolve_fills(now, today)
            if self.db.execute("SELECT 1 FROM live_bars WHERE et_date=? AND idx=?",
                               (today.isoformat(), e64.EXIT_IDX)).fetchone() or n >= end:
                if not self.db.execute("SELECT 1 FROM days WHERE et_date=?", (today.isoformat(),)).fetchone():
                    self.decide(now, today)            # records any trailing skipped decisions
                    self.finalize(now, today)
            return 10.0
        if not self.db.execute("SELECT 1 FROM days WHERE et_date=?", (today.isoformat(),)).fetchone():
            self.decide(now, today)
            self.finalize(now, today)
        return 60.0


# --------------------------------------------------------------------------- lock / main
def acquire_lock(state: Path):
    lock_path = Path(str(state) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    h = lock_path.open("a+b")
    if lock_path.stat().st_size == 0:
        h.write(b"\0"); h.flush()
    h.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(h.fileno(), msvcrt.LK_NBLCK, 1)
        else:  # pragma: no cover
            import fcntl
            fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        h.close()
        raise SystemExit(f"another exp67 runner owns {lock_path}")
    return h


def setup_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(log_dir / "exp67_mnq_forward.log", maxBytes=5_000_000, backupCount=3,
                                             encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[h, logging.StreamHandler()])


def run_live(a):
    root = Path(a.root)
    lock = acquire_lock(root / "state" / "exp67_mnq_forward.sqlite3")   # before opening the rotating log
    setup_logging(root / "logs")
    db = connect(root / "state" / "exp67_mnq_forward.sqlite3")
    db.execute("INSERT OR IGNORE INTO meta VALUES('start_day', ?)", (et(pd.Timestamp.now(tz="UTC")).date().isoformat(),))
    db.commit()
    r = Runner(db, DukascopyFeed(), root / "reports")
    log.info("exp67 MNQ paper forward started (paper only, no keys, no orders)")
    while True:
        try:
            wait = r.step(pd.Timestamp.now(tz="UTC"))
        except Exception:
            log.exception("step failed")
            wait = 30.0
        if a.once:
            break
        time.sleep(wait)
    db.close(); lock.close()


# --------------------------------------------------------------------------- replay control (step 3)
def run_replay(bars_utc: pd.DataFrame, days: list, workdir: Path, step_s: int = 30, delay_s: float = 4.0) -> dict:
    """Drive the live runner minute by minute on historical bars and compare with the Exp 64 batch engine."""
    workdir.mkdir(parents=True, exist_ok=True)
    dbp = workdir / "replay.sqlite3"
    if dbp.exists():
        dbp.unlink()
    db = connect(dbp)
    db.execute("INSERT OR IGNORE INTO meta VALUES('start_day', ?)", (days[0].isoformat(),))
    db.commit()
    feed = ReplayFeed(bars_utc, delay_s)
    r = Runner(db, feed, workdir / "reports")
    for d in days:
        t = pd.Timestamp(f"{d} 09:20", tz=e64.ET).tz_convert("UTC")
        stop = pd.Timestamp(f"{d} 16:15", tz=e64.ET).tz_convert("UTC")
        r.maintenance(t, d)
        while t <= stop:
            r.step(t)
            t += pd.Timedelta(seconds=step_s)
    # batch engine on the same bars (full days)
    df = bars_utc.copy()
    df.index = df.index.tz_convert(e64.ET)
    grid = e64.build_grid(df)
    elig = e64.eligibility(grid)
    lv = e64.compute_levels(grid, elig)
    eng = e64.price_trades(e64.simulate_noise(grid, elig, lv), SPEC)
    eng = eng[eng["date"].isin(days)]
    live = pd.read_sql_query("SELECT * FROM trades ORDER BY et_date, n", db)
    dec = pd.read_sql_query("SELECT * FROM decisions ORDER BY et_date, k", db)
    pos_of = {d: i for i, d in enumerate(grid["dates"])}
    per_day, mism_total = [], 0
    for d in days:
        i = pos_of.get(d)
        eng_pos, pos = [], 0
        if i is not None and lv["tradable"][i]:
            for k in range(len(e64.DECISION_IDX)):
                pos = e64.next_state(pos, lv["P"][i, k], lv["ub"][i, k], lv["lb"][i, k], lv["vwap"][i, k])
                eng_pos.append(int(pos))
        dd = dec[dec["et_date"] == d.isoformat()]
        live_pos = [int(x) if s == "decided" else None for x, s in zip(dd["pos_after"], dd["status"])]
        mism = sum(1 for k, p in enumerate(live_pos) if p is not None and (eng_pos[k] if eng_pos else 0) != p)
        mism_total += mism
        et_ = eng[eng["date"] == d]
        lt_ = live[live["et_date"] == d.isoformat()]
        same_trades = (len(et_) == len(lt_)) and all(
            int(a.side) == int(b.side) and a.entry_bar == b.entry_bar and a.exit_bar == b.exit_bar
            and abs(a.entry_px - b.entry_px) < 1e-9 and abs(a.exit_px - b.exit_px) < 1e-9
            for a, b in zip(et_.itertuples(), lt_.itertuples()))
        per_day.append({"date": str(d), "engine_tradable": bool(i is not None and lv["tradable"][i]),
                        "live_statuses": dd["status"].value_counts().to_dict(),
                        "engine_positions": eng_pos, "live_positions": live_pos, "decision_mismatches": mism,
                        "engine_trades": int(len(et_)), "live_trades": int(len(lt_)), "same_trades": bool(same_trades),
                        "engine_net_usd": round(float(et_["net_usd"].sum()), 2),
                        "live_net_usd": round(float(lt_["net_usd"].sum()), 2)})
    db.close()
    return {"days": per_day, "decision_mismatches": mism_total,
            "all_trades_identical": all(x["same_trades"] for x in per_day)}


def fetch_days(feed, start: dt.date, end: dt.date, pause=0.2) -> pd.DataFrame:
    parts, d = [], start
    while d <= end:
        if d.weekday() < 5:
            x = feed.day(d)
            if x is not None and len(x):
                parts.append(x)
            time.sleep(pause)
        d += dt.timedelta(days=1)
    return pd.concat(parts).sort_index()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lv = sub.add_parser("live")
    lv.add_argument("--root", required=True, help="runner folder (state/, logs/, reports/ are created inside)")
    lv.add_argument("--once", action="store_true")
    rp = sub.add_parser("replay")
    rp.add_argument("--start", required=True, help="first replayed session (YYYY-MM-DD)")
    rp.add_argument("--end", required=True)
    rp.add_argument("--workdir", required=True)
    rp.add_argument("--out", required=True, help="JSON result path")
    a = ap.parse_args(argv)
    if a.cmd == "live":
        run_live(a)
        return 0
    logging.basicConfig(level=logging.WARNING)
    s, e = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    hist_start = s - dt.timedelta(days=75)
    cache = Path(a.workdir) / f"bars_{hist_start}_{e}.pkl"
    if cache.exists():
        bars = pd.read_pickle(cache)
    else:
        bars = fetch_days(DukascopyFeed(), hist_start, e)
        Path(a.workdir).mkdir(parents=True, exist_ok=True)
        bars.to_pickle(cache)
    days = [d.date() for d in pd.date_range(s, e) if e64.is_session(d.date())]
    res = run_replay(bars, days, Path(a.workdir))
    res.update({"start": a.start, "end": a.end, "history_from": str(hist_start), "bars": int(len(bars))})
    Path(a.out).write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "days"}, indent=2))
    for x in res["days"]:
        print(x["date"], x["live_statuses"], "mism", x["decision_mismatches"], "trades e/l", x["engine_trades"],
              x["live_trades"], "same", x["same_trades"], "net e/l", x["engine_net_usd"], x["live_net_usd"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
