"""Tests for the Exp 67 MNQ paper forward runner. Synthetic fixtures only, all under tmp_path."""
import datetime as dt
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("exp67", ROOT / "scripts" / "agents" / "exp67_mnq_forward.py")
m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m)
e64 = m.e64


def sessions(start, n):
    d, out = start, []
    while len(out) < n:
        if e64.is_session(d) and d not in e64.nyse_half_days(d.year):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def make_bars(days, price_fn, vol=100.0, drop=()):
    rows, idx = [], []
    for di, d in enumerate(days):
        base = pd.Timestamp(d.isoformat() + " 09:30", tz=e64.ET)
        for k in range(e64.N_MIN):
            if (d, k) in drop:
                continue
            o, c = price_fn(di, k), price_fn(di, k + 1)
            idx.append((base + pd.Timedelta(minutes=k)).tz_convert("UTC"))
            rows.append((o, max(o, c), min(o, c), c, vol))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=pd.DatetimeIndex(idx))


def trendy(di, k):
    """Quiet wiggle on history days, strong intraday trends (up/down/up-then-down) on the last days."""
    w = 1 + 0.0008 * math.sin(k / 7.0 + di)
    lvl = 20000.0 * (1 + 0.001 * di)
    if di >= 22:
        kind = di % 3
        if kind == 0:
            w += 0.00004 * k
        elif kind == 1:
            w -= 0.00004 * k
        else:
            w += 0.00006 * min(k, 150) - 0.00008 * max(0, k - 150)
    return lvl * w


DAYS = sessions(dt.date(2026, 3, 2), 25)


@pytest.fixture(scope="module")
def bars():
    return make_bars(DAYS, trendy)


def test_feed_sends_referer_and_decodes_like_downloader():
    assert m.HEADERS["Referer"] == "https://www.dukascopy.com/"           # WAF challenge otherwise (2026-10-08)
    payload = {"timestamp": 1_700_000_000_000, "multiplier": 0.001, "open": 100.0, "high": 100.5, "low": 99.5,
               "close": 100.2, "shift": 60000, "times": [0, 1, 2], "opens": [0, 200, -50], "highs": [0, 10, 0],
               "lows": [0, -5, 3], "closes": [0, 7, -9], "volumes": [0.01, 0.02, 0.0]}
    from quant_bot.data.download_dukascopy import decode_day
    ref = pd.DataFrame(decode_day(payload))
    got = m.decode(payload)
    assert list(got.index.as_unit("ms").asi8) == list(ref["timestamp"])
    for c in ("open", "high", "low", "close", "volume"):
        assert np.allclose(got[c].to_numpy(), ref[c].to_numpy())


def test_levels_asof_equal_full_day_at_decision(bars):
    day = DAYS[-1]
    df = bars.copy(); df.index = df.index.tz_convert(e64.ET)
    g = e64.build_grid(df); el = e64.eligibility(g); lv = e64.compute_levels(g, el)
    i = len(g["dates"]) - 1
    hist = df[df.index.date < day]
    today = df[df.index.date == day]
    for k, di in enumerate(e64.DECISION_IDX):
        _, el2, lv2, i2 = m.levels_asof(hist, today, day, di)
        assert lv2["tradable"][i2]
        for key in ("P", "ub", "lb", "vwap", "sigma"):
            assert lv2[key][i2, k] == pytest.approx(lv[key][i, k], rel=0, abs=1e-9)


def test_replay_reproduces_exp64_engine(bars, tmp_path):
    res = m.run_replay(bars, DAYS[-3:], tmp_path / "r", step_s=60)
    assert res["decision_mismatches"] == 0
    assert res["all_trades_identical"]
    assert sum(d["engine_trades"] for d in res["days"]) > 0                # the fixture really trades
    for d in res["days"]:
        assert d["live_statuses"] == {"decided": 12}
        assert d["engine_net_usd"] == pytest.approx(d["live_net_usd"])


def test_cost_is_2_22_and_paper_report_written(bars, tmp_path):
    m.run_replay(bars, DAYS[-3:], tmp_path / "r", step_s=60)
    import sqlite3
    db = sqlite3.connect(tmp_path / "r" / "replay.sqlite3")
    costs = {round(r[0], 6) for r in db.execute("SELECT cost_usd FROM trades")}
    assert costs == {2.22}
    gross_net = db.execute("SELECT SUM(gross_usd - cost_usd - net_usd) FROM trades").fetchone()[0]
    assert abs(gross_net) < 1e-9
    rep = (tmp_path / "r" / "reports" / f"MNQ_{DAYS[-1]}.md").read_text(encoding="utf-8")
    assert "Papier uniquement" in rep and "Décisions" in rep
    # next-day replay check ran for the first two replayed days (exact same data => 0 tick deviation)
    rows = db.execute("SELECT et_date, mean_abs_dev_ticks, decision_mismatches FROM replay_checks").fetchall()
    assert len(rows) >= 2 and all(r[1] == 0 and r[2] == 0 for r in rows)


def test_late_data_is_skipped_never_caught_up(bars, tmp_path):
    res = m.run_replay(bars, DAYS[-1:], tmp_path / "late", step_s=60, delay_s=400)
    d = res["days"][0]
    assert d["live_statuses"] == {"skipped_no_data": 12}            # nothing within 300 s: late or absent
    assert d["live_trades"] == 0


def test_missing_data_skipped_no_data(tmp_path):
    drop = {(DAYS[-1], k) for k in range(100, e64.N_MIN)}                  # feed dies at 11:10 ET
    b = make_bars(DAYS, trendy, drop=drop)
    res = m.run_replay(b, DAYS[-1:], tmp_path / "gap", step_s=60)
    st = res["days"][0]["live_statuses"]
    assert st.get("skipped_no_data", 0) == 9 and st.get("decided", 0) == 3     # 10:00, 10:30, 11:00 decided


def test_stop_rule_alerts(tmp_path):
    db = m.connect(tmp_path / "s.sqlite3")
    r = m.Runner(db, None, tmp_path / "rep")
    for n, d in enumerate(DAYS[:20]):
        late = 2 if n % 2 else 1                                          # 30 / 240 = 12.5 % > 10 %
        db.execute("INSERT INTO days VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (d.isoformat(), 0, 12 - late, late, 0, 0, 1, -200, 2.22, -220.0, -220.0 * (n + 1),
                    -220.0 * (n + 1), 10.0, 20.0, "x"))
    db.commit()
    now = pd.Timestamp.now(tz="UTC")
    r.check_alerts(now, DAYS[19])
    kinds = {k for (k,) in db.execute("SELECT kind FROM alerts")}
    assert kinds == {"IMPL_SKIPPED_DECISIONS", "COLLAPSE"}                 # -4400 <= -4200; traded window < 40
    assert r.summary()["status"].startswith("CLOSED")


def test_runner_down_whole_day_counts_as_skipped(bars, tmp_path):
    db = m.connect(tmp_path / "d.sqlite3")
    db.execute("INSERT INTO meta VALUES('start_day', ?)", (DAYS[-2].isoformat(),)); db.commit()
    r = m.Runner(db, m.ReplayFeed(bars.iloc[:0]), tmp_path / "rep")
    r.backfill_missing_days(pd.Timestamp(f"{DAYS[-1]} 09:00", tz=e64.ET).tz_convert("UTC"), DAYS[-1])
    row = db.execute("SELECT n_decided, n_no_data, n_trades FROM days WHERE et_date=?", (DAYS[-2].isoformat(),)).fetchone()
    assert row == (0, 12, 0)
