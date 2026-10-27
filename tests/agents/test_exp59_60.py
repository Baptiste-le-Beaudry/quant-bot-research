"""Exp 59 / Exp 60 regression tests -- synthetic in-memory data only, never the real data paths."""
import numpy as np
import pandas as pd

from scripts.agents import exp59_resid as E59
from scripts.agents import exp60_regime as E60


def _close(n, seed=0, start="2024-01-01"):
    r = np.random.default_rng(seed).normal(0, 0.001, n)
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


# ------------------------------------------------------------------ Exp 59
def test_minute_returns_undefined_across_gaps():
    c = _close(100)
    c = c.drop(c.index[50:53])
    r = E59.minute_returns(c)
    assert np.isnan(r.iloc[0]) and np.isnan(r.loc[c.index[50]])  # first bar after the gap
    assert np.isfinite(r.loc[c.index[51]])


def test_r15_is_causal_and_exact():
    c = _close(500, 1)
    t = pd.DatetimeIndex([c.index[200], c.index[10]])
    r = E59.r_window(c, t, 15)
    assert np.isclose(r[0], c.iloc[200] / c.iloc[185] - 1)
    assert np.isnan(r[1])  # t-15 not available
    c2 = c.copy()
    c2.iloc[201:] *= 1.5  # any change after the signal bar
    assert np.isclose(E59.r_window(c2, t[:1], 15)[0], r[0])


def test_beta_uses_only_the_30_days_strictly_before_t():
    n = 45 * 1440
    x = E59.minute_returns(_close(n, 2))
    y = 1.7 * x + 0.0002 * np.random.default_rng(3).normal(size=n)
    y = pd.Series(y.to_numpy(), index=x.index)
    t = pd.DatetimeIndex([x.index[40 * 1440]])
    b, nb = E59.RollingBeta(y, x, 30).at(t)
    w = (x.index >= t[0] - pd.Timedelta(days=30)) & (x.index < t[0])
    xx, yy = x[w], y[w]
    ok = xx.notna() & yy.notna()
    ref = np.cov(xx[ok], yy[ok], ddof=0)[0, 1] / np.var(xx[ok])
    assert np.isclose(b[0], ref, rtol=1e-6) and nb[0] == ok.sum()
    # perturbing the signal bar and everything after leaves beta unchanged
    y2 = y.copy()
    y2[y2.index >= t[0]] *= -5
    b2, _ = E59.RollingBeta(y2, x, 30).at(t)
    assert np.isclose(b2[0], b[0], rtol=1e-12)
    # perturbing a bar inside the window changes it
    y3 = y.copy()
    y3[t[0] - pd.Timedelta(minutes=1)] += 0.05
    b3, _ = E59.RollingBeta(y3, x, 30).at(t)
    assert not np.isclose(b3[0], b[0], rtol=1e-9)


def test_residual_share_and_terciles():
    R, S = E59.residual_share(np.array([-0.01, -0.01, 0.0]), np.array([-0.01, 0.0, 0.01]), np.array([1.0, 1.0, 1.0]))
    assert np.allclose(R[:2], [0.0, -0.01]) and np.allclose(S[:2], [0.0, 1.0]) and np.isnan(S[2])
    s = pd.Series([5, 1, 3, np.nan, 2, 6, 4])
    t = E59.tercile(s)
    assert np.isnan(t[3]) and t[1] == 1 and t[5] == 3 and (t.value_counts() == 2).all()


def test_tercile_table_delta():
    df = pd.DataFrame({"population": "P1", "symbol": ["SOLUSDT"] * 6, "S": [1, 2, 3, 4, 5, 6],
                       "net_pct": [0.0, 0.0, 0.1, 0.1, 0.3, 0.3]})
    tab = E59.tercile_table(df, "S")
    row = tab[tab.symbol == "SOLUSDT"].iloc[0]
    assert np.isclose(row.delta_T3_minus_T1, 0.3)


# ------------------------------------------------------------------ Exp 60
def test_daily_sma_shifted_one_day_is_causal():
    c = _close(40 * 1440, 4)
    above = E60.daily_above_sma(c, 20)
    daily = c.resample("1D").last()
    d = daily.index[25]
    assert above[d] == float(daily[d] > daily.iloc[6:26].mean())
    assert above.iloc[:19].isna().all()
    # a signal on day T uses day T-1 only
    T = daily.index[30]
    t = pd.DatetimeIndex([T + pd.Timedelta(hours=13)])
    r = E60.regime_at(above, t)[0]
    assert r == above[daily.index[29]]
    # changing every price from 00:00 of day T onwards leaves R unchanged
    c2 = c.copy()
    c2[c2.index >= T] *= 0.5
    assert E60.regime_at(E60.daily_above_sma(c2, 20), t)[0] == r
    # first minute of day T: still day T-1's regime
    assert E60.regime_at(above, pd.DatetimeIndex([T]))[0] == r


def test_regime_sizer():
    reg = {("SOLUSDT", pd.Timestamp("2024-01-02", tz="UTC")): 0.0,
           ("SOLUSDT", pd.Timestamp("2024-01-03", tz="UTC")): 1.0}
    half, excl = E60.make_regime_sizer(reg, 0.5), E60.make_regime_sizer(reg, 0.0)
    row = lambda d: pd.Series({"symbol": "SOLUSDT", "signal_time": pd.Timestamp(d, tz="UTC")})  # noqa: E731
    assert half(row("2024-01-02"), 100, [], 33.0) == (16.5, "r0_scaled")
    assert half(row("2024-01-03"), 100, [], 33.0) == (33.0, "r1_full")
    assert half(row("2024-01-04"), 100, [], 33.0) == (33.0, "r_nan_full")
    assert excl(row("2024-01-02"), 100, [], 33.0)[0] == 0.0
