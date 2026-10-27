import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location(
    "exp74", Path(__file__).resolve().parents[2] / "scripts" / "agents" / "exp74_leveraged_trend.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def _idx(n):
    return pd.bdate_range("2000-01-03", periods=n)


def test_sma_no_lookahead():
    rng = np.random.default_rng(0)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 600))), index=_idx(600))
    s1 = m.sma_signal(px)
    px2 = px.copy()
    px2.iloc[400:] *= 3.0  # change the future only
    s2 = m.sma_signal(px2)
    pd.testing.assert_series_equal(s1.iloc[:400], s2.iloc[:400])
    # warm-up: no signal before 200 closes
    assert (s1.iloc[:199] == 0).all()
    # value check at one date: SMA includes close t and the 199 previous ones
    t = 450
    sma = px.iloc[t - 199:t + 1].mean()
    assert s1.iloc[t] == int(px.iloc[t] > sma)


def test_positions_shift_t_plus_1():
    sig = pd.Series([0, 0, 1, 1, 1, 0, 0, 0], index=_idx(8))
    pos = m.positions(sig, lag=2)
    # signal turns on at close of day 2; executed at close of day 3; earns day 4 return first
    assert list(pos) == [0, 0, 0, 0, 1, 1, 1, 0]
    paper = m.positions(sig, lag=1)
    assert list(paper) == [0, 0, 0, 1, 1, 1, 0, 0]


def test_strategy_returns_formula_and_switch_cost():
    idx = _idx(5)
    pos = pd.Series([0, 1, 1, 0, 0], index=idx)
    rtr = pd.Series([0.01, 0.02, -0.01, 0.03, 0.0], index=idx)
    rf = pd.Series([0.0001] * 5, index=idx)
    r = m.strategy_returns(pos, rtr, rf, k=2.0, fee=0.0095, switch_cost=0.001)
    lev = lambda x: 2 * x - 0.0001 - 0.0095 / 252
    assert r.iloc[0] == pytest.approx(0.0001)
    assert r.iloc[1] == pytest.approx((1 + lev(0.02)) * 0.999 - 1)  # switch in
    assert r.iloc[2] == pytest.approx(lev(-0.01))
    assert r.iloc[3] == pytest.approx((1 + 0.0001) * 0.999 - 1)      # switch out
    assert r.iloc[4] == pytest.approx(0.0001)
    r3 = m.strategy_returns(pos, rtr, rf, k=3.0, fee=0.0, switch_cost=0.0)
    assert r3.iloc[2] == pytest.approx(3 * -0.01 - 2 * 0.0001)


def test_no_lookahead_end_to_end():
    rng = np.random.default_rng(1)
    n = 700
    idx = _idx(n)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n))), index=idx)
    irx = pd.Series(4.0, index=idx)
    r1, *_ = m.rule_on_index(px, px, irx, 2.0, 2, 0.0, start="2000-01-01")
    px2 = px.copy()
    px2.iloc[500:] = px2.iloc[500:] * np.exp(rng.normal(0, 0.05, n - 500)).cumprod()
    r2, *_ = m.rule_on_index(px2, px2, irx, 2.0, 2, 0.0, start="2000-01-01")
    # returns up to day 499 depend only on data up to day 499
    pd.testing.assert_series_equal(r1.iloc[:500], r2.iloc[:500])


def test_metrics():
    idx = pd.bdate_range("2000-01-03", periods=253)
    r = pd.Series(0.0, index=idx)
    r.iloc[10] = -0.5
    r.iloc[20] = 1.0
    assert m.max_dd(r) == pytest.approx(-0.5)
    g = pd.Series(0.10 ** 0 * ((1.1) ** (1 / 252) - 1), index=pd.bdate_range("2000-01-03", periods=252 * 10))
    assert m.cagr(g) == pytest.approx(0.10, abs=0.01)


def test_verdict_logic():
    assert m.verdict(0.16, -0.40, 0.12, 2)["verdict"] == "PASS"
    assert m.verdict(0.16, -0.40, 0.12, 1)["verdict"] == "INCERTAIN"
    assert m.verdict(0.09, -0.40, 0.05, 3)["verdict"] == "REJET"
    assert m.verdict(0.12, -0.40, 0.13, 3)["verdict"] == "REJET"
    assert m.verdict(0.20, -0.61, 0.10, 3)["verdict"] == "REJET"
    assert m.verdict(0.13, -0.50, 0.10, 3)["verdict"] == "INCERTAIN"


def test_proxy_correction_only_downward():
    idx = pd.bdate_range("2007-01-01", periods=252 * 5)
    etf = pd.Series(0.0003, index=idx)
    synth_hi = etf + 0.04 / 252
    c = m.proxy_correction(synth_hi, etf, "2007-01-01")
    assert c["extra_drag_applied"] > 0
    assert m.cagr(synth_hi - c["extra_drag_applied"] / 252) == pytest.approx(c["cagr_etf"], abs=1e-6)
    c2 = m.proxy_correction(etf - 0.04 / 252, etf, "2007-01-01")
    assert c2["extra_drag_applied"] == 0.0 and not c2["within_tolerance"]


def test_dsr_runs(tmp_path):
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2000-01-03", periods=2000)
    r = pd.Series(rng.normal(0.0005, 0.01, 2000), index=idx)
    d = m.deflated_sharpe(r, pd.Series(0.0, index=idx), 74)
    assert 0 <= d["dsr"] <= 1 and d["sr0_ann"] > 0
