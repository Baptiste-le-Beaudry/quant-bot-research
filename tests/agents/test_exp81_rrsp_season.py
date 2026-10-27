"""Regression tests for Exp 81 (RRSP season TSX vs S&P). Synthetic fixtures only (tmp_path, no real data path)."""
import importlib.util
import math
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp81", ROOT / "scripts" / "agents" / "exp81_rrsp_season.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def P(y, mo):
    return pd.Period(year=y, month=mo, freq="M")


# ------------------------------------------------------------------ RRSP deadline
def test_day60_leap_and_non_leap():
    assert m.day60(2023) == date(2023, 3, 1)
    assert m.day60(2025) == date(2025, 3, 1)
    assert m.day60(2024) == date(2024, 2, 29)
    assert m.day60(2000) == date(2000, 2, 29)
    assert m.day60(1900) == date(1900, 3, 1)


def test_deadline_next_business_day_weekend_and_holiday():
    bd = pd.bdate_range("2024-12-01", "2026-03-31")
    # 2025-03-01 is a Saturday -> Monday 2025-03-03 (CRA deadline that year)
    assert m.rrsp_deadline(2025, bd) == pd.Timestamp("2025-03-03")
    # 2026-03-01 is a Sunday -> Monday 2026-03-02
    assert m.rrsp_deadline(2026, bd) == pd.Timestamp("2026-03-02")
    # a holiday on the deadline Monday pushes it to Tuesday
    bd2 = bd.drop(pd.Timestamp("2025-03-03"))
    assert m.rrsp_deadline(2025, bd2) == pd.Timestamp("2025-03-04")
    bd3 = pd.bdate_range("2024-01-01", "2024-03-31")
    assert m.rrsp_deadline(2024, bd3) == pd.Timestamp("2024-02-29")  # leap year, Thursday


def test_last_and_first_trading_day():
    bd = pd.bdate_range("2022-12-01", "2023-01-31").drop(pd.Timestamp("2022-12-30"))
    assert m.last_trading_day(2022, 12, bd) == pd.Timestamp("2022-12-29")
    bd = bd.drop(pd.Timestamp("2023-01-02"))
    assert m.first_trading_day(2023, 1, bd) == pd.Timestamp("2023-01-03")


def test_close_at_uses_last_close_and_guards_staleness():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-02", "2020-01-03"]))
    assert m.close_at(s, pd.Timestamp("2020-01-06")) == 2.0
    with pytest.raises(ValueError):
        m.close_at(s, pd.Timestamp("2020-01-20"))


# ------------------------------------------------------------------ monthly statistic D
def _closes(ret_by_month: dict, start="1999-12", end="2001-12", default=0.0):
    idx = pd.period_range(start, end, freq="M")
    lvl, out = 100.0, []
    for p in idx:
        if p != idx[0]:
            lvl *= 1 + ret_by_month.get((p.year, p.month), default)
        out.append(lvl)
    return pd.Series(out, index=idx)


def test_monthly_D_window_and_reference():
    # TSX +10 % in Jan 2001 and +5 % in Jun 2001, S&P flat: E_S = 0.10, E_R = 0.05 * 2/10
    a = _closes({(2001, 1): 0.10, (2001, 6): 0.05})
    b = _closes({})
    t = m.monthly_season_table(a, b, [2001])
    assert t.loc[2001, "E_S"] == pytest.approx(0.10)
    assert t.loc[2001, "E_R"] == pytest.approx(0.01)
    assert t.loc[2001, "D"] == pytest.approx(0.09)
    # a December move of y-1 is NOT in the season of y; a March move is in the reference
    a2 = _closes({(2000, 12): 0.20, (2001, 3): 0.10})
    t2 = m.monthly_season_table(a2, b, [2001])
    assert t2.loc[2001, "E_S"] == pytest.approx(0.0)
    assert t2.loc[2001, "D"] == pytest.approx(-0.02)


def test_monthly_controls_single_windows():
    a = _closes({(2001, 1): 0.04, (2001, 2): 0.02, (2001, 12): -0.03, (2001, 4): 0.01})
    b = _closes({})
    c = m.monthly_controls(a, b, [2001])
    er1 = (1.01 * 0.97 - 1) / 10
    assert c.loc[2001, "jan"] == pytest.approx(0.04 - er1)
    assert c.loc[2001, "feb"] == pytest.approx(0.02 - er1)
    assert c.loc[2001, "dec"] == pytest.approx(-0.03 - 0.01 / 9)
    assert c.loc[2001, "mar_apr"] == pytest.approx(0.01 - (0.97 - 1) * 2 / 8)


def test_daily_variants_windows():
    cal = pd.bdate_range("2023-11-01", "2024-12-31").drop(pd.Timestamp("2024-01-01"))  # New Year holiday
    a = pd.Series(100.0, index=cal)
    b = pd.Series(100.0, index=cal)
    # jump on the first January session (2024-01-02): in (a), excluded from (b)
    a.loc["2024-01-02":] *= 1.05
    t_a = m.daily_season_table(a, b, [2024], "a")
    t_b = m.daily_season_table(a, b, [2024], "b")
    assert t_a.loc[2024, "start"] == "2023-12-29" and t_a.loc[2024, "end"] == "2024-02-29"
    assert t_a.loc[2024, "D"] == pytest.approx(0.05)
    assert t_b.loc[2024, "start"] == "2024-01-02" and t_b.loc[2024, "D"] == pytest.approx(0.0)
    # a move on the day AFTER the deadline belongs to the reference of (a)
    a2 = pd.Series(100.0, index=cal)
    a2.loc["2024-03-01":] *= 1.10
    t2 = m.daily_season_table(a2, b, [2024], "a")
    assert t2.loc[2024, "E_S"] == pytest.approx(0.0)
    assert t2.loc[2024, "E_R"] == pytest.approx(0.02)


def test_kf_and_uk_tables():
    idx = pd.period_range("1990-01", "1990-12", freq="M")
    ra = pd.Series(0.0, index=idx)
    rb = pd.Series(0.0, index=idx)
    ra[P(1990, 1)] = 0.02
    ra[P(1990, 3)] = 0.03
    t = m.kf_season_table(ra, rb, [1990])
    assert t.loc[1990, "D"] == pytest.approx(0.02 - 0.03 * 0.2)
    u = m.uk_table(ra, rb, [1990])
    assert u.loc[1990, "U"] == pytest.approx(0.03 - 0.02 / 11)


# ------------------------------------------------------------------ portfolio, t+1 and costs
def test_rule_uses_tsx_only_in_jan_feb_and_charges_two_switches():
    idx = pd.period_range("2000-01", "2001-12", freq="M")
    rt = pd.Series(0.01, index=idx)
    rs = pd.Series(0.02, index=idx)
    r = m.rule_returns(rt, rs)
    assert r[P(2000, 12)] == pytest.approx(0.02)            # December: still S&P (switch at Dec close)
    assert r[P(2001, 1)] == pytest.approx(0.01 - 0.001)     # first TSX month, switch cost
    assert r[P(2001, 2)] == pytest.approx(0.01)
    assert r[P(2001, 3)] == pytest.approx(0.02 - 0.001)     # back to S&P, switch cost
    assert r[P(2001, 4)] == pytest.approx(0.02)
    yearly_cost = (np.where([p.month in (1, 2) for p in idx], rt, rs) - r.values).reshape(2, 12).sum(axis=1)
    assert yearly_cost == pytest.approx([0.002, 0.002])


def test_rule_has_no_lookahead_on_returns():
    idx = pd.period_range("2000-01", "2002-12", freq="M")
    rng = np.random.default_rng(0)
    rt = pd.Series(rng.normal(0, 0.04, len(idx)), index=idx)
    rs = pd.Series(rng.normal(0, 0.04, len(idx)), index=idx)
    r = m.rule_returns(rt, rs)
    rt2 = rt.copy()
    rt2.iloc[20:] = 0.5
    r2 = m.rule_returns(rt2, rs)
    pd.testing.assert_series_equal(r.iloc[:20], r2.iloc[:20])


def test_mix_drift_cost():
    idx = pd.period_range("2000-01", "2000-02", freq="M")
    rt = pd.Series([0.12, 0.0], index=idx)
    rs = pd.Series([0.0, 0.0], index=idx)
    mx = m.mix_returns(rt, rs)
    rp = 0.12 / 6
    w1 = (1 / 6) * 1.12 / (1 + rp)
    turn = 2 * abs(w1 - 1 / 6)
    assert mx.iloc[0] == pytest.approx(rp - 0.0005 * turn)
    assert mx.iloc[1] == pytest.approx(0.0)


def test_evaluate_reference_matches_rule_vol():
    idx = pd.period_range("1980-01", "2019-12", freq="M")
    rng = np.random.default_rng(1)
    rt = pd.Series(rng.normal(0.006, 0.05, len(idx)), index=idx)
    rs = pd.Series(rng.normal(0.007, 0.045, len(idx)), index=idx)
    rf = pd.Series(0.003, index=idx)
    res = m.evaluate(m.rule_returns(rt, rs), m.mix_returns(rt, rs), rf)
    assert res["ref"]["vol"] == pytest.approx(res["rule"]["vol"], rel=1e-4)
    assert res["n_months"] == len(idx)


# ------------------------------------------------------------------ statistics and verdict
def test_ttest():
    x = pd.Series([0.01, 0.02, 0.03, 0.04], index=[1, 2, 3, 4])
    r = m.ttest(x)
    assert r["mean"] == pytest.approx(0.025)
    assert r["t"] == pytest.approx(0.025 / (x.std(ddof=1) / 2))


def _s(mean, t):
    return {"mean": mean, "t": t}


def test_verdict_pass_reject_uncertain():
    port_ok = {"dsharpe": 0.05, "surplus_cagr": 0.005}
    rob_ok = {"a": _s(0.01, 1), "b": _s(0.001, 0.2), "c": _s(0.002, 0.5)}
    v = m.verdict(_s(0.008, 2.1), _s(0.01, 1), _s(0.005, 1), _s(0.002, 1.6), port_ok, rob_ok)
    assert v["verdict"] == "PASS"
    # mean exactly at threshold passes c1; t below 2 -> INCERTAIN
    assert m.verdict(_s(0.0075, 2.0), _s(0.01, 1), _s(0.005, 1), _s(0.002, 1.6), port_ok, rob_ok)["verdict"] == "PASS"
    assert m.verdict(_s(0.008, 1.9), _s(0.01, 1), _s(0.005, 1), _s(0.002, 1.6), port_ok, rob_ok)["verdict"] == "INCERTAIN"
    # REJET triggers
    assert m.verdict(_s(0.0, 0.0), _s(0.01, 1), _s(0.005, 1), _s(0.002, 1.6), port_ok, rob_ok)["verdict"] == "REJET"
    assert m.verdict(_s(0.02, 3.0), _s(0.01, 1), _s(0.005, 1), _s(-0.001, -0.5), port_ok, rob_ok)["verdict"] == "REJET"
    # surplus below 0.4 %/yr, or one robustness control <= 0 -> INCERTAIN
    assert m.verdict(_s(0.02, 3.0), _s(0.01, 1), _s(0.005, 1), _s(0.002, 1.6), {"dsharpe": 0.05, "surplus_cagr": 0.0039}, rob_ok)["verdict"] == "INCERTAIN"
    rob_bad = {**rob_ok, "b": _s(-0.001, -0.2)}
    v = m.verdict(_s(0.02, 3.0), _s(0.01, 1), _s(0.005, 1), _s(0.002, 1.6), port_ok, rob_bad)
    assert v["verdict"] == "INCERTAIN" and v["c5_detail"]["b"] is False
    # sub-period sign
    assert m.verdict(_s(0.02, 3.0), _s(-0.001, -1), _s(0.005, 1), _s(0.002, 1.6), port_ok, rob_ok)["verdict"] == "INCERTAIN"


def test_dsr_monotone_in_n():
    rng = np.random.default_rng(2)
    ex = pd.Series(rng.normal(0.006, 0.04, 600))
    a, b = m.deflated_sharpe(ex, 95), m.deflated_sharpe(ex, 132)
    assert 0 <= b["dsr"] <= a["dsr"] <= 1


# ------------------------------------------------------------------ parsers on synthetic files
def test_parse_statcan_zip(tmp_path):
    csv = ('"REF_DATE","GEO","DGUID","Toronto Stock Exchange statistics","UOM","UOM_ID","SCALAR_FACTOR","SCALAR_ID",'
           '"VECTOR","COORDINATE","VALUE","STATUS","SYMBOL","TERMINATED","DECIMALS"\n'
           '"1956-01","Canada","x","Standard and Poor\'s/Toronto Stock Exchange Composite Index, close","Index","1","units","0","v1","1.1","100.5","","","","1"\n'
           '"1956-02","Canada","x","Standard and Poor\'s/Toronto Stock Exchange Composite Index, close","Index","1","units","0","v1","1.1","101.5","","","","1"\n'
           '"1956-01","Canada","x","Standard and Poor\'s/Toronto Stock Exchange Composite Index, high","Index","1","units","0","v2","1.2","999","","","","1"\n')
    p = tmp_path / "t.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("10100125.csv", csv)
        z.writestr("10100125_MetaData.csv", "x")
    s = m.parse_statcan_zip(p)
    assert list(s.values) == [100.5, 101.5] and s.index[0] == P(1956, 1)


def test_kf_country_parser(tmp_path):
    txt = ("This file was created ...\n\n Monthly returns\n,Mkt,BM High,BM Low\n197501,  1.00, 2.0, -99.99\n"
           "197502, -2.00, 1.0, 0.5\n\n Annual returns\n,Mkt,BM High,BM Low\n1975, 3.0, 1.0, 1.0\n")
    p = tmp_path / "kf.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("UK.csv", txt)
        z.writestr("Canada.csv", txt.replace("1.00", "4.00"))
    uk = m.kf_country_market(p, "UK")
    assert list(uk.values) == pytest.approx([0.01, -0.02]) and uk.index[0] == P(1975, 1)
    assert m.kf_country_market(p, "Canada").iloc[0] == pytest.approx(0.04)
    blocks = m.kf_blocks(txt)
    assert math.isnan(blocks[0][1]["BM Low"].iloc[0])
    with pytest.raises(ValueError):
        m.kf_country_market(p, "US")


DAT = """
     Value-Weight Dollar Returns      All 4 Data Items Not Reqd
                -- BE/ME --   --- E/P ---
          Mkt   High    Low   High    Low
197501   1.50   2.00  -1.00   0.00   0.00
197502  -2.00   1.00   0.50   0.00   0.00

     Value-Weight Local  Returns      All 4 Data Items Not Reqd
                -- BE/ME --   --- E/P ---
          Mkt   High    Low   High    Low
197501   9.00   2.00  -1.00   0.00   0.00
197502   9.00   1.00   0.50   0.00   0.00

     Value-Weight Dollar Returns      All 4 Data Items Required
                -- BE/ME --   --- E/P ---
          Mkt   High    Low   High    Low
197501   7.00   2.00  -1.00   0.00   0.00
197502   7.00   1.00   0.50   0.00   0.00

     Value-Weight Dollar Returns      All 4 Data Items Not Reqd
              -- BE/ME --   --- E/P ---
        Mkt   High    Low   High    Low
1975     5.0    1.0    1.0    1.0    1.0
"""


def test_kf_dat_selects_dollar_not_reqd_monthly(tmp_path):
    p = tmp_path / "kf.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("UK.Dat", DAT)
        z.writestr("Austria.Dat", DAT)
        z.writestr("Austrlia.Dat", DAT)
    uk = m.kf_country_market(p, "UK")
    assert list(uk.values) == pytest.approx([0.015, -0.02])
    assert uk.index[-1] == P(1975, 2)
    with pytest.raises(ValueError):          # 'us' inside 'Austria' must not match
        m.kf_country_market(p, "US")


def test_splice_monthly_chains_returns_after_junction():
    a = pd.Series([100.0, 110.0], index=pd.period_range("2023-08", "2023-09", freq="M"))
    b = pd.Series([1000.0, 1200.0, 1260.0], index=pd.period_range("2023-09", "2023-11", freq="M"))
    s = m.splice_monthly(a, b)
    assert list(s.values) == pytest.approx([100.0, 110.0, 132.0, 138.6])
    assert s.attrs["junction"] == "2023-09"
