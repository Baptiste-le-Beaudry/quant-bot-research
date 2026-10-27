"""Regression tests for Exp 64 (noise-area momentum). Synthetic fixtures only, in tmp_path."""
import datetime as dt
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp64", ROOT / "scripts" / "agents" / "exp64_noise_momentum.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


# ------------------------------------------------------------------ helpers
def sessions(start, n):
    d, out = start, []
    while len(out) < n:
        if m.is_session(d) and d not in m.nyse_half_days(d.year):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def write_csv(path, days, price_fn, vol=100.0, drop=None):
    rows = []
    for di, d in enumerate(days):
        base = pd.Timestamp(d.isoformat() + " 09:30", tz=m.ET)
        for k in range(m.N_MIN):
            if drop and (d, k) in drop:
                continue
            o, c = price_fn(di, k), price_fn(di, k + 1)
            ts = (base + pd.Timedelta(minutes=k)).tz_convert("UTC")
            rows.append((ts.strftime("%Y-%m-%d %H:%M:%S+00:00"), o, max(o, c), min(o, c), c, vol))
    pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"]).to_csv(path, index=False)


def wiggle(di, k):
    return 100.0 * (1 + 0.001 * math.sin(k / 7.0 + di))


def pipeline(path, decision=None):
    df = m.load_pre_holdout(path, decision)
    g = m.build_grid(df)
    e = m.eligibility(g)
    lv = m.compute_levels(g, e)
    return g, e, lv


# ------------------------------------------------------------------ calendar / tz / holdout
def test_calendar():
    assert dt.date(2024, 3, 29) in m.nyse_holidays(2024)          # Good Friday
    assert dt.date(2022, 12, 26) in m.nyse_holidays(2022)         # Christmas observed
    assert dt.date(2021, 12, 24) in m.nyse_holidays(2021)
    assert dt.date(2022, 6, 20) in m.nyse_holidays(2022)          # Juneteenth observed
    assert dt.date(2021, 6, 18) not in m.nyse_holidays(2021)      # before 2022
    assert dt.date(2025, 1, 9) in m.nyse_holidays(2025)
    assert dt.date(2022, 1, 1) not in m.nyse_holidays(2022) and dt.date(2021, 12, 31) not in m.nyse_holidays(2021)
    assert dt.date(2023, 11, 24) in m.nyse_half_days(2023)
    assert dt.date(2024, 7, 3) in m.nyse_half_days(2024)
    assert dt.date(2020, 7, 3) not in m.nyse_half_days(2020)      # holiday (observed July 4)
    assert dt.date(2021, 12, 24) not in m.nyse_half_days(2021)
    assert m.previous_session(dt.date(2024, 4, 1)) == dt.date(2024, 3, 28)


def test_timezone_dst(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame({"timestamp": ["2024-07-15 13:30:00+00:00", "2024-01-16 14:30:00+00:00"],
                  "open": [1, 1], "high": [1, 1], "low": [1, 1], "close": [1, 1], "volume": [1, 1]}).to_csv(p, index=False)
    df = m.load_pre_holdout(p, decision_file(tmp_path))
    assert [(t.hour, t.minute) for t in df.index] == [(9, 30), (9, 30)]


def decision_file(tmp_path):
    f = tmp_path / "decision.md"
    f.write_text("test")
    return str(f)


def test_holdout_rows_not_loaded(tmp_path):
    p = tmp_path / "x.csv"
    ts = pd.date_range("2020-01-02 15:00", periods=1000, freq="min", tz="UTC")
    pd.DataFrame({"timestamp": ts.strftime("%Y-%m-%d %H:%M:%S+00:00"), "open": 1.0, "high": 1.0,
                  "low": 1.0, "close": 1.0, "volume": 1.0}).to_csv(p, index=False)
    assert len(m.load_pre_holdout(p)) == 800
    with pytest.raises(m.HoldoutLockedError):
        m.load_pre_holdout(p, str(tmp_path / "missing.md"))
    assert len(m.load_pre_holdout(p, decision_file(tmp_path))) == 1000


# ------------------------------------------------------------------ eligibility
def test_eligibility_gap_and_history(tmp_path):
    days = sessions(dt.date(2023, 1, 3), 18)
    drop = {(days[16], k) for k in range(100, 107)}               # 7-minute hole
    p = tmp_path / "x.csv"
    write_csv(p, days, wiggle, drop=drop)
    g, e, lv = pipeline(p, decision_file(tmp_path))
    el = dict(zip(e["date"], e["eligible"]))
    assert not el[days[0]]                                         # no previous close
    assert not el[days[16]]
    assert el[days[17]]
    # 14 previous eligible days needed: days[1..14] eligible -> days[15] is the first tradable
    tr = dict(zip(g["dates"], lv["tradable"]))
    assert not tr[days[14]] and tr[days[15]] and not tr[days[16]] and tr[days[17]]


# ------------------------------------------------------------------ signals and fills
def trend_day_fn(trend_day, slope):
    def f(di, k):
        if di == trend_day:
            return 100.0 * (1 + slope * k)
        return wiggle(di, k)
    return f


def test_long_entry_next_open_and_eod_exit(tmp_path):
    days = sessions(dt.date(2023, 1, 3), 17)
    p = tmp_path / "x.csv"
    fn = trend_day_fn(16, 0.0001)                                   # +0.01 %/min, 0.6 % by 10:30
    write_csv(p, days, fn)
    g, e, lv = pipeline(p, decision_file(tmp_path))
    tr = m.price_trades(m.simulate_noise(g, e, lv), m.INSTRUMENTS["SP500"])
    t = tr[tr["date"] == days[16]]
    assert len(t) == 1
    r = t.iloc[0]
    assert r["side"] == 1 and r["decision"] == "10:00" and r["exit_reason"] == "eod"
    assert r["entry_bar"] == 30 and r["entry_px"] == pytest.approx(fn(16, 30))   # open of the 10:00 bar
    assert r["exit_bar"] == 389 and r["exit_px"] == pytest.approx(fn(16, 389))
    assert r["gross_usd"] == pytest.approx((fn(16, 389) - fn(16, 30)) * 5.0)
    assert r["cost_usd"] == pytest.approx(2 * (0.61 + 1.25))
    # the previous-close adjustment and sigma only use data before the day
    assert lv["ub"][16, 0] == pytest.approx(max(fn(16, 0), fn(15, 390)) * (1 + lv["sigma"][16, 0]))


def test_sigma_no_lookahead(tmp_path):
    days = sessions(dt.date(2023, 1, 3), 17)
    p1, p2 = tmp_path / "a.csv", tmp_path / "b.csv"
    write_csv(p1, days, wiggle)
    write_csv(p2, days, trend_day_fn(16, 0.0003))
    _, _, a = pipeline(p1, decision_file(tmp_path))
    _, _, b = pipeline(p2, decision_file(tmp_path))
    np.testing.assert_allclose(a["sigma"][16], b["sigma"][16])
    expected = np.mean([[abs(wiggle(di, i + 1) / wiggle(di, 0) - 1) for i in m.DECISION_IDX] for di in range(2, 16)], axis=0)
    np.testing.assert_allclose(a["sigma"][16], expected)


def make_grid(path_close):
    """One tradable day with given per-minute closes; open of bar k = close of bar k-1."""
    c = np.asarray(path_close, dtype=float)[None, :]
    o = np.concatenate([[c[0, 0]], c[0, :-1]])[None, :]
    g = {"dates": [dt.date(2023, 6, 1)], "open": o, "high": np.maximum(o, c), "low": np.minimum(o, c),
         "close": c, "volume": np.ones_like(c)}
    return g


def run_handmade(close, ub, lb, vwap):
    g = make_grid(close)
    e = pd.DataFrame({"eligible": [True]})
    lv = {"P": np.asarray(close)[m.DECISION_IDX][None, :], "ub": np.full((1, 12), ub), "lb": np.full((1, 12), lb),
          "vwap": np.asarray(vwap, dtype=float)[None, :], "tradable": np.array([True]), "o930": g["open"][:, 0]}
    return m.simulate_noise(g, e, lv), g


def test_stop_only_on_semi_hourly_and_filled_next_open():
    close = np.full(m.N_MIN, 100.0)
    close[20:] = 102.0                         # above UB=101 at 10:00 -> long
    close[35:58] = 99.0                        # dips under UB and LB-free zone between checks
    close[58:] = 102.0                         # back above by 10:30 check (bar 59)
    close[85:] = 100.5                         # 11:00 check (bar 89): below UB -> stop
    trades, g = run_handmade(close, ub=101.0, lb=95.0, vwap=np.full(12, 100.0))
    assert len(trades) == 1
    t = trades[0]
    assert t["entry_bar"] == 30 and t["exit_bar"] == 90 and t["exit_reason"] == "stop"
    assert t["exit_px"] == g["open"][0, 90]    # next-bar open, not the stop level 101


def test_vwap_trailing_stop_and_reversal():
    # VWAP above UB: long stopped when price < VWAP even if still above UB
    close = np.full(m.N_MIN, 100.0)
    close[20:] = 103.0
    close[50:] = 102.0
    vw = np.full(12, 100.0)
    vw[1] = 102.5                              # 10:30 vwap above price 102 > UB 101
    trades, _ = run_handmade(close, ub=101.0, lb=95.0, vwap=vw)
    assert trades[0]["exit_bar"] == 60 and trades[0]["exit_reason"] == "stop"
    # reversal: long, then price below LB -> close long and open short at same bar
    close = np.full(m.N_MIN, 100.0)
    close[20:] = 103.0
    close[50:] = 94.0
    trades, _ = run_handmade(close, ub=101.0, lb=95.0, vwap=np.full(12, 100.0))
    assert [t["exit_reason"] for t in trades] == ["reverse", "eod"]
    assert trades[1]["side"] == -1 and trades[1]["entry_bar"] == 60 and trades[0]["exit_bar"] == 60
    tr = m.price_trades(trades, m.INSTRUMENTS["NASDAQ100"])
    assert tr["cost_usd"].sum() == pytest.approx(2 * 2 * (0.61 + 0.5))


def test_next_state_table():
    assert m.next_state(0, 102, 101, 99, 100) == 1
    assert m.next_state(0, 98, 101, 99, 100) == -1
    assert m.next_state(0, 100, 101, 99, 100) == 0
    assert m.next_state(1, 101.5, 101, 99, 102) == 0     # below VWAP
    assert m.next_state(1, 102.5, 101, 99, 102) == 1
    assert m.next_state(-1, 98.5, 101, 99, 98) == 0      # above VWAP (min(LB,VWAP)=98)
    assert m.next_state(-1, 97.5, 101, 99, 98) == -1
    assert m.next_state(-1, 101.5, 101, 99, 98) == 1


def test_gao_variant(tmp_path):
    close = np.full(m.N_MIN, 100.0)
    close[200:] = 99.0
    g = make_grid(close)
    e = pd.DataFrame({"eligible": [True]})
    lv = {"P": close[m.DECISION_IDX][None, :], "o930": g["open"][:, 0], "tradable": np.array([True])}
    t = m.simulate_gao(g, e, lv)
    assert len(t) == 1 and t[0]["side"] == -1 and t[0]["entry_bar"] == 360 and t[0]["exit_bar"] == 389


def test_stats_and_verdict():
    days = pd.DataFrame({"date": [dt.date(2020, 1, i + 1) for i in range(4)], "n_trades": [1, 0, 1, 1],
                         "gross_usd": [10.0, 0, -5, 20], "cost_usd": [3.72, 0, 3.72, 3.72]})
    days["net_usd"] = days["gross_usd"] - days["cost_usd"]
    days["net_pct"] = days["net_usd"] / 1000
    s = m.period_stats(days)
    assert s["days_traded"] == 3 and s["n_trades"] == 3
    assert s["cost_share_of_gross"] == pytest.approx(11.16 / 25)
    assert s["maxdd_usd"] == pytest.approx(-8.72)
    v = m.verdict({"A": {"P1": {"sharpe_net": 0.6}, "P2": {"n_days": 0}}, "B": {"P1": {"sharpe_net": 0.7}, "P2": {"n_days": 0}}})
    assert v["verdict"].startswith("NON DETERMINABLE") and v["pass_still_possible"]
    mk = lambda s1, s2, n2: {"P1": {"sharpe_net": s1}, "P2": {"n_days": 300, "sharpe_net": s2, "days_traded": n2}}
    assert m.verdict({"A": mk(0.6, 0.6, 250), "B": mk(0.6, 0.7, 250)})["verdict"] == "PASS"
    assert m.verdict({"A": mk(0.6, -0.1, 250), "B": mk(0.6, 0.7, 250)})["verdict"] == "REJET"
    assert m.verdict({"A": mk(0.6, 0.4, 250), "B": mk(0.6, 0.3, 250)})["verdict"] == "REJET"
    assert m.verdict({"A": mk(0.6, 0.6, 150), "B": mk(0.6, 0.7, 250)})["verdict"] == "INCERTAIN"
    assert m.verdict({"A": mk(0.3, 0.6, 250), "B": mk(0.6, 0.7, 250)})["verdict"] == "INCERTAIN"
