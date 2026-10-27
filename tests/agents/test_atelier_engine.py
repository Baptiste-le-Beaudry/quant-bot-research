"""T-073 atelier engine: lag, costs, reference, bond proxy. Synthetic data only (no file I/O)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("atelier_engine", ROOT / "scripts" / "agents" / "atelier" / "engine.py")
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)


def _days(n, start="2000-01-03"):
    return pd.bdate_range(start, periods=n)


def test_signal_at_t_earns_from_t_plus_2():
    idx = _days(10)
    rets = pd.DataFrame({"a": [0.0] * 10}, index=idx)
    rets.iloc[3, 0] = 0.10  # big move on day 3
    rf = pd.Series(0.0, index=idx)
    w = pd.DataFrame({"a": np.nan}, index=idx)
    w.iloc[0, 0] = 0.0
    w.iloc[2, 0] = 1.0  # decided at close of day 2 -> traded close day 3 -> first return day 4
    sim = E.simulate(w, rets, rf, cost=0.0, spread=0.0, drift_cost=False)
    assert sim["ret"].iloc[3] == 0.0
    w.iloc[1, 0] = 1.0  # decided day 1 -> earns day 3
    sim = E.simulate(w, rets, rf, cost=0.0, spread=0.0, drift_cost=False)
    assert sim["ret"].iloc[3] == pytest.approx(0.10)


def test_cash_earns_rf_and_spread_on_leverage():
    idx = _days(5)
    rets = pd.DataFrame({"a": [0.01] * 5}, index=idx)
    rf = pd.Series(0.0004, index=idx)
    w = pd.DataFrame({"a": [2.0] * 5}, index=idx)
    sim = E.simulate(w, rets, rf, lag=0, cost=0.0, spread=0.018, drift_cost=False)
    assert sim["ret"].iloc[1] == pytest.approx(0.0004 + 2 * (0.01 - 0.0004) - 0.018 / 252)
    w0 = pd.DataFrame({"a": [0.0] * 5}, index=idx)
    sim0 = E.simulate(w0, rets, rf, lag=0, cost=0.0, drift_cost=False)
    assert np.allclose(sim0["ret"], 0.0004)


def test_trading_cost_on_weight_change():
    idx = _days(4)
    rets = pd.DataFrame({"a": [0.0] * 4, "b": [0.0] * 4}, index=idx)
    rf = pd.Series(0.0, index=idx)
    w = pd.DataFrame({"a": [1.0, 1.0, 0.0, 0.0], "b": [0.0, 0.0, 1.0, 1.0]}, index=idx)
    sim = E.simulate(w, rets, rf, lag=0, cost=0.001, spread=0.0, drift_cost=False)
    assert sim["ret"].iloc[0] == pytest.approx(-0.001)  # initial buy
    assert sim["ret"].iloc[2] == pytest.approx(-0.002)  # sell a, buy b
    assert sim["orders"].iloc[2] == 2


def test_drift_cost_zero_for_single_asset_full_weight_and_positive_for_mix():
    idx = _days(60)
    rng = np.random.default_rng(0)
    rets = pd.DataFrame({"a": rng.normal(0, 0.01, 60), "b": rng.normal(0, 0.01, 60)}, index=idx)
    rf = pd.Series(0.0, index=idx)
    w1 = pd.DataFrame({"a": 1.0, "b": 0.0}, index=idx)
    s1 = E.simulate(w1, rets, rf, lag=0, cost=0.001, spread=0.0)
    s1n = E.simulate(w1, rets, rf, lag=0, cost=0.001, spread=0.0, drift_cost=False)
    assert np.allclose(s1["ret"], s1n["ret"])
    w2 = pd.DataFrame({"a": 0.5, "b": 0.5}, index=idx)
    s2 = E.simulate(w2, rets, rf, lag=0, cost=0.001, spread=0.0)
    s2n = E.simulate(w2, rets, rf, lag=0, cost=0.001, spread=0.0, drift_cost=False)
    assert (s2n["ret"] - s2["ret"]).sum() > 0


def test_reference_equal_vol_and_identity():
    idx = _days(2000)
    rng = np.random.default_rng(1)
    m = pd.Series(rng.normal(0.0004, 0.012, 2000), index=idx)
    rf = pd.Series(0.0001, index=idx)
    L = E.solve_L(0.25, m, rf)
    assert E.ann_vol(E.ref_returns(L, m, rf)) == pytest.approx(0.25, rel=1e-6)
    # a rule that IS the market x1 has dsharpe ~ 0 against its own equal-vol reference
    ev = E.evaluate(m, rf, m)
    assert ev["L_ref"] == pytest.approx(1.0, abs=1e-6)
    assert ev["dsharpe"] == pytest.approx(0.0, abs=1e-9)


def test_bond_proxy_carry_and_duration():
    idx = pd.to_datetime(["2000-01-03", "2000-01-04", "2000-01-05"])
    y = pd.Series([5.0, 5.0, 6.0], index=idx)
    r = E.bond_tr_from_yield(y)
    assert r.iloc[0] == pytest.approx(0.05 / 365.25, rel=1e-6)  # unchanged yield: carry only
    assert -0.08 < r.iloc[1] < -0.07  # +100 bp on a 10y par bond: about -7.4 %


def test_scale_to_vol_hits_target():
    idx = _days(1500)
    rng = np.random.default_rng(2)
    rets = pd.DataFrame({"a": rng.normal(0.0003, 0.01, 1500)}, index=idx)
    rf = pd.Series(0.0001, index=idx)
    w = pd.DataFrame({"a": 1.0}, index=idx)
    k, sim = E.scale_to_vol(w, rets, rf, target=0.20)
    assert E.ann_vol(sim["ret"]) == pytest.approx(0.20, rel=1e-3)
    assert k > 1


def test_monthly_period_index_works():
    idx = pd.period_range("2000-01", periods=24, freq="M")
    rets = pd.DataFrame({"a": [0.01] * 24}, index=idx)
    rf = pd.Series(0.001, index=idx)
    w = pd.DataFrame({"a": 1.0}, index=idx)
    sim = E.simulate(w, rets, rf, lag=1, ppy=12)
    assert sim["ret"].iloc[0] == pytest.approx(0.001)
    assert E.cagr(sim["ret"].iloc[2:], ppy=12) == pytest.approx(1.01 ** 12 - 1, rel=1e-3)
