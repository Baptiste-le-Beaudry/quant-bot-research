"""Regression tests for Exp 68 (multi-horizon Donchian trend long/cash). Synthetic fixtures only."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp68", ROOT / "scripts" / "agents" / "exp68_trend.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def days(n, start="2021-01-01"):
    return pd.date_range(start, periods=n, freq="1D", tz="UTC")


def walk(n, seed, drift=0.0, sd=0.03):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(drift + sd * rng.standard_normal(n)))


def panel(n=900, seed=0):
    idx = days(n)
    return pd.DataFrame({s: walk(n, seed + i, drift=0.001 * (i - 1)) for i, s in enumerate(m.SYMS)}, index=idx)


# ------------------------------------------------------------------ daily builder
def test_daily_close_is_price_at_midnight(tmp_path):
    idx = pd.date_range("2024-01-01 00:00", "2024-01-03 23:59", freq="1min", tz="UTC")
    bars = pd.DataFrame({"close": np.arange(len(idx), dtype=float)}, index=idx)
    bars["high"] = bars["close"] + 0.5
    bars["low"] = bars["close"] - 0.5
    bars.to_pickle(tmp_path / "X_full.pkl")
    d = m.daily_from_minutes(pd.read_pickle(tmp_path / "X_full.pkl"))
    lab = pd.Timestamp("2024-01-02", tz="UTC")
    # bar opening 2024-01-01 23:59 is index 1439 -> its close is the price at 2024-01-02 00:00
    assert d.loc[lab, "close"] == 1439.0
    assert d.loc[lab, "n_bars"] == 1440
    assert d.loc[lab, "high"] == 1439.5 and d.loc[lab, "low"] == -0.5


def test_daily_missing_day_forward_filled():
    idx = pd.date_range("2024-01-01", "2024-01-06", freq="1min", tz="UTC", inclusive="left")
    idx = idx[(idx < "2024-01-03") | (idx >= "2024-01-04")]  # whole 2024-01-03 missing
    bars = pd.DataFrame({"close": 1.0, "high": 1.0, "low": 1.0}, index=idx)
    d = m.daily_from_minutes(bars)
    assert pd.Timestamp("2024-01-04", tz="UTC") in d.index
    assert d.loc[pd.Timestamp("2024-01-04", tz="UTC"), "n_bars"] == 0
    assert d.index.to_series().diff().dropna().eq(pd.Timedelta("1D")).all()


# ------------------------------------------------------------------ states
def test_state_entry_hold_and_mid_exit():
    c = pd.Series([10, 11, 12, 13, 14, 12.6, 12.4, 11.0, 15.0], index=days(9), dtype=float)
    st = m.states(c, 3)
    # t=3: 13 > max(10,11,12) -> 1 ; t=4 stays ; t=5: mid of (13,14,12.6)=13.3 -> 0
    assert list(st.values[:3]) == [0, 0, 0]
    assert st.iloc[3] == 1 and st.iloc[4] == 1
    assert st.iloc[5] == 0
    assert st.iloc[6] == 0 and st.iloc[7] == 0
    assert st.iloc[8] == 1  # 15 > max(12.6, 12.4, 11)


def test_state_kept_between_mid_and_high():
    c = pd.Series([10, 10, 10, 12, 11.5, 11.2], index=days(6), dtype=float)
    st = m.states(c, 3)
    # entry at t=3 ; t=4: mid(10,12,11.5)=11 -> 11.5 kept ; t=5: mid(12,11.5,11.2)=11.6 -> 11.2 exits
    assert list(st.values) == [0, 0, 0, 1, 1, 0]


def test_state_needs_n_previous_closes():
    c = pd.Series(np.arange(1, 8, dtype=float), index=days(7))
    st = m.states(c, 5)
    assert st.iloc[:5].eq(0).all() and st.iloc[5] == 1


# ------------------------------------------------------------------ weights
def test_weight_formula_is_written_rule_not_reference():
    n = 400
    idx = days(n)
    rng = np.random.default_rng(1)
    # low vol (~10%/yr annualised), steady uptrend: sigma < 0.25
    c = pd.DataFrame({s: 100 * np.exp(np.cumsum(0.002 + 0.005 * rng.standard_normal(n))) for s in m.SYMS}, index=idx)
    w = m.target_weights(c)
    wr = m.target_weights(c, reference=True)
    sig = m.signal(c)
    sv = m.vol(c)
    exp = (sig * np.minimum(1.0, 0.25 / sv) / 3).fillna(0)
    pd.testing.assert_frame_equal(w, exp, check_names=False)
    assert (w <= 1 / 3 + 1e-12).all().all()
    assert (w.sum(axis=1) <= 1 + 1e-12).all()
    # where 0 < signal < 1 and sigma < 0.25, the reference weight is larger
    mask = (sig > 0) & (sig < 1) & (sv < 0.25)
    assert mask.values.any()
    assert (wr[mask] > w[mask] + 1e-9).stack().any()


def test_weight_high_vol_scales_down():
    idx = days(5)
    sig = pd.Series([1.0] * 5, index=idx)
    sv = pd.Series([0.5] * 5, index=idx)
    assert np.allclose(sig * np.minimum(1.0, 0.25 / sv) / 3, 0.5 / 3)


# ------------------------------------------------------------------ causality
def test_no_lookahead_weights():
    C = panel()
    w = m.target_weights(C)
    cut = 600
    C2 = C.copy()
    C2.iloc[cut + 1:] = C2.iloc[cut + 1:] * np.exp(np.linspace(0, 3, len(C2) - cut - 1))[:, None]
    w2 = m.target_weights(C2)
    pd.testing.assert_frame_equal(w.iloc[: cut + 1], w2.iloc[: cut + 1])


def test_return_on_day_j_uses_weight_decided_at_j_minus_1():
    C = panel()
    w = m.target_weights(C)
    bt = m.backtest(C, w, 0.0)
    R = C.pct_change()
    j = 700
    assert bt["gross"].iloc[j] == pytest.approx((w.iloc[j - 1] * R.iloc[j]).sum())
    # changing the return of day J must not change the weight used on day J
    C2 = C.copy()
    C2.iloc[j:] *= 1.5
    assert m.target_weights(C2).iloc[j - 1].equals(w.iloc[j - 1])


# ------------------------------------------------------------------ costs / cash
def test_cost_drift_turnover():
    idx = days(3)
    C = pd.DataFrame({"A": [100.0, 110.0, 110.0], "B": [100.0, 100.0, 100.0], "C": [100.0, 100.0, 100.0]}, index=idx)
    w = pd.DataFrame({"A": [0.5, 0.5, 0.5], "B": 0.0, "C": 0.0}, index=idx)
    bt = m.backtest(C, w, 0.002)
    # day1: return 0.5*10% = 5% ; drifted A weight = 0.5*1.1/1.05 ; trade back to 0.5 at close day1
    drift = 0.5 * 1.1 / 1.05
    assert bt["gross"].iloc[1] == pytest.approx(0.05)
    assert bt["cost"].iloc[1] == pytest.approx(0.5 * 0.001)        # initial buy at close day0
    assert bt["cost"].iloc[2] == pytest.approx((drift - 0.5) * 0.001)
    bt_ref = m.backtest(C, w, 0.002, drift_turnover=False)
    assert bt_ref["cost"].iloc[2] == 0.0


def test_per_asset_cost_and_cash_yield():
    idx = days(4)
    C = pd.DataFrame({s: [100.0] * 4 for s in m.SYMS}, index=idx)
    w = pd.DataFrame({"BTCUSDT": [0.2, 0.0, 0.0, 0.0], "ETHUSDT": 0.0, "SOLUSDT": [0.2, 0.0, 0.0, 0.0]}, index=idx)
    bt = m.backtest(C, w, {"BTCUSDT": 0.002, "ETHUSDT": 0.002, "SOLUSDT": 0.0005})
    assert bt["cost"].iloc[1] == pytest.approx(0.2 * 0.001 + 0.2 * 0.00025)
    apy = pd.Series(0.04, index=idx)
    bt2 = m.backtest(C, w, 0.0, cash_apy=apy)
    d = 1.04 ** (1 / 365) - 1
    assert bt2["cash"].iloc[1] == pytest.approx(0.6 * d)
    assert bt2["cash"].iloc[2] == pytest.approx(1.0 * d)
    assert bt2["cash"].iloc[0] == 0.0


# ------------------------------------------------------------------ stats / verdict
def test_stats_maxdd_counts_first_day():
    r = pd.Series([-0.1, 0.05, 0.05], index=days(3))
    s = m.stats(r)
    assert s["maxdd"] == pytest.approx(-0.1)


def test_basket_buy_and_hold():
    idx = days(3)
    C = pd.DataFrame({"A": [1.0, 2.0, 2.0], "B": [1.0, 1.0, 1.0], "C": [1.0, 1.0, 1.0]}, index=idx)
    reb, bh = m.basket(C, "2021-01-02", "2021-01-03")
    assert reb.iloc[0] == pytest.approx(1 / 3)
    assert bh.iloc[0] == pytest.approx(1 / 3) and bh.iloc[1] == pytest.approx(0.0)


@pytest.mark.parametrize("sh,dd,cagr,shb,exp", [
    (0.6, -0.10, 0.05, 0.1, "PASS"),
    (0.6, -0.16, 0.05, 0.1, "INCERTAIN"),
    (0.4, -0.10, 0.05, 0.1, "INCERTAIN"),
    (0.6, -0.10, 0.05, 0.7, "INCERTAIN"),
    (0.0, -0.10, 0.00, -1.0, "REJET"),
    (0.8, -0.21, 0.30, 0.1, "REJET"),
])
def test_verdict(sh, dd, cagr, shb, exp):
    assert m.verdict(sh, dd, cagr, shb)["verdict"] == exp
