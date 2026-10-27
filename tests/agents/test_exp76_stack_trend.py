"""Regression tests for Exp 76 (stacked US equities + TSMOM). Synthetic fixtures only (tmp_path, no real data path)."""
import importlib.util
import io
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp76", ROOT / "scripts" / "agents" / "exp76_stack_trend.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def months(n, start="1985-01"):
    return pd.period_range(start, periods=n, freq="M")


def ser(n, seed=0, sd=0.03, mu=0.005, start="1985-01"):
    rng = np.random.default_rng(seed)
    return pd.Series(mu + sd * rng.standard_normal(n), index=months(n, start))


# ---------------------------------------------------------------- vol scaling: no look-ahead
def test_vol_scale_uses_previous_36_months_only():
    raw = ser(120, 1)
    k = m.vol_scale(raw)
    t = 60
    exp = 0.10 / (raw.iloc[t - 36:t].std(ddof=1) * math.sqrt(12))
    assert k.iloc[t] == pytest.approx(exp)
    # first 36 months: undefined; month 36 (index 36) is the first defined
    assert k.iloc[:36].isna().all() and not math.isnan(k.iloc[36])
    # shocking month t itself must NOT change k_t; it must change k_{t+1}
    raw2 = raw.copy()
    raw2.iloc[t] = 0.9
    k2 = m.vol_scale(raw2)
    assert k2.iloc[t] == pytest.approx(k.iloc[t])
    assert k2.iloc[t + 1] != pytest.approx(k.iloc[t + 1])
    # shocking any future month leaves all earlier k unchanged
    raw3 = raw.copy()
    raw3.iloc[100:] = 5.0
    pd.testing.assert_series_equal(m.vol_scale(raw3).iloc[:101], k.iloc[:101])


def test_vol_scale_hits_target_on_iid_series():
    raw = ser(3000, 2, sd=0.04, mu=0.0)
    k = m.vol_scale(raw)
    scaled = (k * raw).dropna()
    assert m.ann_vol(scaled) == pytest.approx(0.10, rel=0.05)


def test_first_rule_month_is_1988_01_with_aqr_start_1985_01():
    raw = ser(60, 3)
    k = m.vol_scale(raw)
    mk = pd.DataFrame({"Mkt-RF": ser(60, 4), "RF": pd.Series(0.003, index=months(60))})
    df = m.rule_returns(mk["Mkt-RF"], mk["RF"], raw, k)
    assert df.index[0] == pd.Period("1988-01", "M")


# ---------------------------------------------------------------- rule formula and costs
def test_rule_formula_without_cost():
    n = 50
    raw, mkt = ser(n, 5), ser(n, 6)
    rf = pd.Series(0.002, index=months(n))
    k = m.vol_scale(raw)
    df = m.rule_returns(mkt, rf, raw, k, w=1.0, decote=0.03, fee=0.005, cost=0.0)
    i = df.index[3]
    exp = mkt[i] + rf[i] + 1.0 * (k[i] * raw[i] - 0.03 / 12) - 0.005 / 12
    assert df.loc[i, "gross"] == pytest.approx(exp)
    assert df.loc[i, "net"] == pytest.approx(exp)


def test_rebalancing_cost_and_turnover():
    n = 40
    raw, mkt = ser(n, 7), ser(n, 8)
    rf = pd.Series(0.0, index=months(n))
    k = pd.Series(1.0, index=months(n))
    df = m.rule_returns(mkt, rf, raw, k, w=1.0, decote=0.0, fee=0.0, cost=0.001)
    assert df["turnover"].iloc[0] == pytest.approx(2.0)
    g0 = 1 + df["gross"].iloc[0]
    exp_t1 = abs(1 - (1 + mkt.iloc[0]) / g0) + abs(1.0 - 1.0 / g0)
    assert df["turnover"].iloc[1] == pytest.approx(exp_t1)
    assert df["net"].iloc[1] == pytest.approx((1 + df["gross"].iloc[1]) * (1 - 0.001 * exp_t1) - 1)
    assert (df["net"] <= df["gross"] + 1e-15).all()


def test_decote_shift_is_exact():
    n = 80
    raw, mkt = ser(n, 9), ser(n, 10)
    rf = pd.Series(0.001, index=months(n))
    k = m.vol_scale(raw)
    a = m.rule_returns(mkt, rf, raw, k, decote=0.03, cost=0.0)["net"]
    b = m.rule_returns(mkt, rf, raw, k, decote=0.045, cost=0.0)["net"]
    assert (a - b).values == pytest.approx(0.015 / 12)


# ---------------------------------------------------------------- reference and L
def test_solve_L_equalises_vol():
    n = 300
    mkt = ser(n, 11, sd=0.045)
    rf = pd.Series(np.linspace(0.0, 0.004, n), index=months(n))
    for tv in (0.08, 0.15, 0.25, 0.40):
        L = m.solve_L(mkt, rf, tv)
        assert m.ann_vol(m.ref_returns(L, mkt, rf)) == pytest.approx(tv, rel=1e-8)


def test_ref_fee_only_above_one():
    n = 12
    mkt = pd.Series(0.01, index=months(n))
    rf = pd.Series(0.002, index=months(n))
    assert m.ref_returns(0.8, mkt, rf).iloc[0] == pytest.approx(0.8 * 0.01 + 0.002)
    assert m.ref_returns(2.0, mkt, rf).iloc[0] == pytest.approx(2 * 0.01 + 0.002 - 0.01 / 12)


def test_compare_resolves_L_per_period():
    n = 300
    mkt = ser(n, 12, sd=0.045, start="1988-01")
    rf = pd.Series(0.002, index=mkt.index)
    rule = pd.Series(np.r_[np.full(150, 0.0), np.zeros(150)], index=mkt.index) + ser(n, 13, sd=0.03, start="1988-01")
    rule.iloc[150:] = ser(150, 14, sd=0.08, start="2000-07").values
    a = m.compare(rule, mkt, rf, "1988-01", "2000-06")
    b = m.compare(rule, mkt, rf, "2000-07", None)
    assert a["L"] < b["L"]
    assert a["ref"]["vol"] == pytest.approx(a["rule"]["vol"], rel=1e-8)
    assert b["ref"]["vol"] == pytest.approx(b["rule"]["vol"], rel=1e-8)


def test_identical_rule_gives_zero_gap():
    n = 200
    mkt = ser(n, 15, sd=0.045, start="1988-01")
    rf = pd.Series(0.002, index=mkt.index)
    rule = m.ref_returns(1.3, mkt, rf)
    c = m.compare(rule, mkt, rf, "1988-01", None)
    assert c["L"] == pytest.approx(1.3, rel=1e-6)
    assert c["sharpe_gap"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- metrics
def test_cagr_maxdd():
    r = pd.Series([0.1, -0.5, 0.2], index=months(3))
    assert m.max_dd(r) == pytest.approx(-0.5)
    r12 = pd.Series(0.01, index=months(12))
    assert m.cagr(r12) == pytest.approx(1.01 ** 12 - 1)
    assert m.max_dd(pd.Series([-0.1], index=months(1))) == pytest.approx(-0.1)


# ---------------------------------------------------------------- verdict logic
BASE = dict(gap_full=0.15, gap_post=0.05, gap_w05=0.05, gap_w15=0.05, gap_d45=0.05,
            intl_gaps={"DevExUS": 0.1, "Europe": 0.1, "Japan": -0.1}, cagr_full=0.16, cagr_post=0.10,
            maxdd_full=-0.35)


def v(**kw):
    d = dict(BASE)
    d.update(kw)
    return m.verdict(**d)["verdict"]


def test_verdict_pass():
    assert v() == "PASS"
    assert v(cagr_full=0.10, cagr_post=0.15) == "PASS"


def test_verdict_reject():
    assert v(gap_full=0.0) == "REJET"
    assert v(gap_full=-0.2) == "REJET"
    assert v(intl_gaps={"DevExUS": 0.0, "Europe": -0.1, "Japan": 0.3}) == "REJET"


def test_verdict_uncertain():
    assert v(gap_full=0.09) == "INCERTAIN"
    assert v(gap_post=0.0) == "INCERTAIN"
    assert v(gap_w05=-0.01) == "INCERTAIN"
    assert v(gap_w15=-0.01) == "INCERTAIN"
    assert v(gap_d45=0.0) == "INCERTAIN"
    assert v(cagr_full=0.149, cagr_post=0.149) == "INCERTAIN"
    assert v(maxdd_full=-0.41) == "INCERTAIN"
    # exactly -40 % passes
    assert v(maxdd_full=-0.40) == "PASS"
    # only 1 of 3 positive, 2 non-positive -> REJET (not INCERTAIN)
    assert v(intl_gaps={"DevExUS": 0.1, "Europe": -0.1, "Japan": -0.1}) == "REJET"


# ---------------------------------------------------------------- parsers (synthetic files in tmp_path)
def test_parse_kf_csv_and_zip(tmp_path):
    txt = ("This file was created ...\n\n,Mkt-RF,SMB,HML,RF\n198801,   4.21,  -0.5,  1.0,   0.29\n"
           "198802,  -1.00,  0.1,  0.2,   0.46\n\n Annual Factors: January-December \n,Mkt-RF,SMB,HML,RF\n"
           "  1988,  10.0, 1.0, 1.0, 6.0\n")
    p = tmp_path / "x.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("X.csv", txt)
    d = m.kf_from_zip(p)
    assert list(d.index.astype(str)) == ["1988-01", "1988-02"]
    assert d.loc[pd.Period("1988-01", "M"), "Mkt-RF"] == pytest.approx(0.0421)
    assert d.loc[pd.Period("1988-02", "M"), "RF"] == pytest.approx(0.0046)


def test_parse_kf_rejects_missing_code():
    txt = ",Mkt-RF,SMB,HML,RF\n199001, -99.99, 0, 0, 0.5\n"
    with pytest.raises(ValueError):
        m.parse_kf_csv(txt)


def test_parse_aqr_xlsx(tmp_path):
    rows = [["AQR title", None, None], [None, None, None], [None, "TSMOM", "TSMOM^CM"],
            [pd.Timestamp("1985-01-31"), 0.04, 0.01], [pd.Timestamp("1985-02-28"), -0.02, 0.0],
            [pd.Timestamp("1985-03-29"), 0.01, 0.02]]
    p = tmp_path / "aqr.xlsx"
    pd.DataFrame(rows).to_excel(p, sheet_name="TSMOM Factors", header=False, index=False)
    s = m.parse_aqr_xlsx(p)
    assert list(s.index.astype(str)) == ["1985-01", "1985-02", "1985-03"]
    assert s.iloc[1] == pytest.approx(-0.02)


def test_top3_share():
    idx = months(48, "1990-01")
    ref = pd.Series(0.0, index=idx)
    rule = pd.Series(0.0, index=idx)
    rule[pd.Period("1990-06", "M")] = 0.10
    rule[pd.Period("1991-06", "M")] = 0.05
    rule[pd.Period("1992-06", "M")] = 0.02
    rule[pd.Period("1993-06", "M")] = 0.01
    t = m.top3_share(rule, ref)
    tot = sum(math.log1p(x) for x in (0.10, 0.05, 0.02, 0.01))
    assert t["top3_share"] == pytest.approx((tot - math.log1p(0.01)) / tot)
