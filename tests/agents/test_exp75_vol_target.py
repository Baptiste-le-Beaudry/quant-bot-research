"""Regression tests for Exp 75 (S&P volatility targeting). Synthetic fixtures only (no real data path)."""
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))
spec = importlib.util.spec_from_file_location("exp75", ROOT / "scripts" / "agents" / "exp75_vol_target.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def bdays(n, start="2000-01-03"):
    return pd.bdate_range(start, periods=n)


def rets(n, seed=0, sd=0.01, drift=0.0003):
    rng = np.random.default_rng(seed)
    return pd.Series(drift + sd * rng.standard_normal(n), index=bdays(n))


def test_sigma_uses_only_past_and_current_returns():
    r = rets(200, 1)
    s = m.realised_vol(r, 21)
    t = 100
    expected = r.iloc[t - 20:t + 1].std(ddof=1) * math.sqrt(252)
    assert s.iloc[t] == pytest.approx(expected)
    # shocking a future return must not change sigma at t (no look-ahead)
    r2 = r.copy()
    r2.iloc[t + 1] = 0.5
    assert m.realised_vol(r2, 21).iloc[t] == pytest.approx(s.iloc[t])
    assert m.realised_vol(r2, 21).iloc[t + 1] != pytest.approx(s.iloc[t + 1])
    assert s.iloc[:20].isna().all() and not math.isnan(s.iloc[20])


def test_target_cap_and_warmup():
    r = rets(100, 2, sd=0.001)  # very low vol -> V/sigma >> 3
    w = m.target_weights(r, 0.25, 21, 3.0)
    assert (w.iloc[:20] == 0).all()
    assert (w.iloc[21:] == 3.0).all()
    r_hi = rets(100, 3, sd=0.05)  # sigma ~ 79 % -> w ~ 0.32
    w2 = m.target_weights(r_hi, 0.25)
    sig = m.realised_vol(r_hi)
    assert w2.iloc[50] == pytest.approx(0.25 / sig.iloc[50])


def test_t_plus_one_execution_lag():
    idx = bdays(10)
    tgt = pd.Series(0.0, index=idx)
    tgt.iloc[3:] = 2.0  # decided at close of day 3
    held, traded = m.held_weights(tgt, band=0.25)
    # executed at close of day 4, earns from day 5
    assert traded.iloc[4] and not traded.iloc[3]
    assert (held.iloc[:5] == 0).all()
    assert (held.iloc[5:] == 2.0).all()


def test_band_blocks_small_changes_and_allows_large():
    idx = bdays(12)
    tgt = pd.Series([1.0, 1.0, 1.1, 1.2, 1.24, 1.26, 1.26, 1.0, 1.0, 1.3, 1.3, 1.3], index=idx)
    held, traded = m.held_weights(tgt, band=0.25)
    after = held.shift(-1)  # position after close e
    # first trade 0 -> 1.0 at close 1 (target of day 0)
    assert traded.iloc[1] and after.iloc[1] == 1.0
    # 1.1, 1.2, 1.24 blocked; 1.26 (decided day 5, executed close 6) passes
    assert not traded.iloc[3:6].any()
    assert traded.iloc[6] and after.iloc[6] == pytest.approx(1.26)
    # back to 1.0 (|diff| = 0.26) at close 8
    assert traded.iloc[8] and after.iloc[8] == 1.0
    # 1.3 (|diff| = 0.30) at close 10
    assert traded.iloc[10]
    assert int(traded.sum()) == 4


def test_band_exact_threshold_trades():
    idx = bdays(5)
    tgt = pd.Series([1.0, 1.25, 1.25, 1.25, 1.25], index=idx)
    held, traded = m.held_weights(tgt, 0.25)
    assert traded.iloc[2]  # |1.25-1.0| == 0.25 -> trade (>=)


def test_return_formula_and_costs():
    idx = bdays(4)
    r_tr = pd.Series([0.0, 0.01, -0.02, 0.005], index=idx)
    rf = pd.Series(0.0001, index=idx)
    held = pd.Series([0.0, 2.0, 2.0, 0.5], index=idx)
    out = m.rule_returns(held, r_tr, rf)
    g1 = 2 * 0.01 + (1 - 2) * 0.0001 - 0.0095 * 1 / 252
    assert out.iloc[1] == pytest.approx((1 + g1) * (1 - 0.001 * 2.0) - 1)
    g2 = 2 * -0.02 - 0.0001 - 0.0095 / 252
    assert out.iloc[2] == pytest.approx(g2)
    g3 = 0.5 * 0.005 + 0.5 * 0.0001
    assert out.iloc[3] == pytest.approx((1 + g3) * (1 - 0.001 * 1.5) - 1)
    assert out.iloc[0] == pytest.approx(0.0001)


def test_solve_L_matches_vol():
    r = rets(2000, 5, sd=0.012)
    rf = pd.Series(0.0001, index=r.index) + 0.00002 * np.sin(np.arange(2000) / 50)
    for target in (0.10, 0.19, 0.35):
        L = m.solve_L(r, rf, target)
        ref = m.weighted_returns(L, r, rf)
        assert m.ann_vol(ref) == pytest.approx(target, rel=1e-7)
    # constant rf: vol is exactly L * vol(r)
    rf0 = pd.Series(0.0001, index=r.index)
    L = m.solve_L(r, rf0, 0.3)
    assert L == pytest.approx(0.3 / m.ann_vol(r), rel=1e-7)


def test_weighted_returns_fee_only_above_one():
    idx = bdays(3)
    r = pd.Series(0.01, index=idx)
    rf = pd.Series(0.0, index=idx)
    assert m.weighted_returns(0.8, r, rf).iloc[0] == pytest.approx(0.008)
    assert m.weighted_returns(1.5, r, rf).iloc[0] == pytest.approx(0.015 - 0.0095 * 0.5 / 252)


def test_full_pipeline_no_lookahead(tmp_path):
    """Changing the level on the last day must not change any held weight (held depends on t-2 info)."""
    n = 400
    r = rets(n, 9, sd=0.015)
    lvl = 100 * (1 + r).cumprod()
    lvl.index = pd.bdate_range("1989-01-02", periods=n)
    irx = pd.Series(5.0, index=lvl.index)
    b1 = m.build(lvl, irx, 0.25)
    lvl2 = lvl.copy()
    lvl2.iloc[-1] *= 1.3
    lvl2.iloc[-2] *= 0.7
    b2 = m.build(lvl2, irx, 0.25)
    pd.testing.assert_series_equal(b1["held"].iloc[:-1], b2["held"].iloc[:-1])
    assert b1["held"].iloc[-1] == b2["held"].iloc[-1]  # day -1 earns with position after close -2 (decided at -3)
    pd.DataFrame({"h": b1["held"]}).to_csv(tmp_path / "held.csv")


def test_verdict_logic():
    base = dict(gap_full_25=0.15, sh_rule_pre=0.5, sh_rule_post=0.6, gap_pre=0.1, gap_post=0.1, gap_full_20=0.1,
                gap_full_30=0.1, idx_gaps={"a": 0.1, "b": 0.1, "c": -0.1}, post_cagr=0.16, full_maxdd=-0.4)
    assert m.verdict(**base)["verdict"] == "PASS"
    assert m.verdict(**(base | {"gap_full_25": -0.01}))["verdict"] == "REJET"
    assert m.verdict(**(base | {"idx_gaps": {"a": 0.1, "b": 0.0, "c": -0.1}}))["verdict"] == "REJET"
    assert m.verdict(**(base | {"gap_full_25": 0.05}))["verdict"] == "INCERTAIN"
    assert m.verdict(**(base | {"post_cagr": 0.14}))["verdict"] == "INCERTAIN"
    assert m.verdict(**(base | {"gap_post": -0.01}))["verdict"] == "INCERTAIN"


def test_top3_share():
    idx = pd.bdate_range("2000-01-03", "2004-12-31")
    rule = pd.Series(0.0, index=idx)
    ref = pd.Series(0.0, index=idx)
    rule[rule.index.year == 2001] = 0.001
    res = m.top3_share(rule, ref)
    assert res["top3_share"] == pytest.approx(1.0)
    assert res["n_years_positive"] == 1
