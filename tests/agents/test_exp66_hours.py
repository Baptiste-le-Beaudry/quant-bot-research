"""Tests for Exp 66 (synthetic inputs only, fixtures in tmp_path)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp66", ROOT / "scripts" / "agents" / "exp66_hours.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def bars(start="2021-01-01", minutes=180, drop=()):
    idx = pd.date_range(start, periods=minutes, freq="1min", tz="UTC")
    o = 100.0 + np.arange(minutes, dtype=float)
    df = pd.DataFrame({"open": o, "high": o + 1, "low": o - 1, "close": o + 0.5}, index=idx)
    return df.drop(index=[idx[i] for i in drop])


def test_cost():
    assert m.COST_RT == pytest.approx(0.0002 + 0.02 / 116)


def test_hourly_returns_open_to_open():
    h, st = m.hourly_returns(bars())
    # hours 00 and 01 have a next-hour open; 02:00 has none (data ends 02:59)
    assert list(h.hour_start.dt.hour) == [0, 1]
    assert h.gross_ret.iloc[0] == pytest.approx(160 / 100 - 1)
    assert h.gross_ret.iloc[1] == pytest.approx(220 / 160 - 1)
    assert st["dropped_missing_next_or_nan"] == 1


def test_hourly_returns_missing_bar_dropped_not_filled():
    h, _ = m.hourly_returns(bars(drop=(60,)))  # 01:00 bar missing -> hour 00 has no exit, hour 01 no entry
    assert list(h.hour_start.dt.hour) == []


def make_hourly(means, n_days=200, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    days = pd.date_range("2021-01-01", periods=n_days, freq="D", tz="UTC")
    for d in days:
        common = rng.normal(0, 0.002, 24)
        for s in m.SYMBOLS:
            for hr in range(24):
                rows.append({"symbol": s, "hour_start": d + pd.Timedelta(hours=hr),
                             "gross_ret": means.get(hr, 0.0) + common[hr] + rng.normal(0, 0.0005)})
    return m.add_fields(pd.DataFrame(rows))


def test_t_decisional_is_min_and_daily_lower_with_common_shock():
    h = make_hourly({5: 0.0005})
    st = m.group_stats(h[h.hour == 5])
    assert st["t_daily"] < st["t_pooled"]
    assert st["t_decisional"] == pytest.approx(min(st["t_daily"], st["t_pooled"]))
    assert st["n_obs"] == 600 and st["n_portfolio_hours"] == 200


def test_select_top2_then_t_filter_no_reach_down():
    tab = pd.DataFrame({"hour_utc": range(24), "mean_net_pct": [0.0] * 24, "t_pooled": [0.0] * 24,
                        "t_daily": [0.0] * 24, "t_decisional": [0.0] * 24})
    tab.loc[3, ["mean_net_pct", "t_pooled", "t_daily", "t_decisional"]] = [0.05, 3.0, 2.6, 2.6]
    tab.loc[7, ["mean_net_pct", "t_pooled", "t_daily", "t_decisional"]] = [0.04, 2.0, 1.0, 1.0]
    tab.loc[9, ["mean_net_pct", "t_pooled", "t_daily", "t_decisional"]] = [0.03, 9.0, 9.0, 9.0]
    s = m.select_hours(tab)
    assert s["retained_hours"] == [3]  # hour 9 (3rd by mean) is never reached
    tab.loc[3, "t_decisional"] = 2.4
    assert m.select_hours(tab)["retained_hours"] == []
    assert m.select_hours(tab)["decision"].startswith("REJET")


def test_hour_table_and_selection_on_synthetic():
    h = make_hourly({13: 0.003, 14: 0.002}, n_days=300)
    tab = m.hour_table(h)
    assert len(tab) == 24 and tab.funding_hour.sum() == 3
    assert m.select_hours(tab)["retained_hours"] == [13, 14]


def test_verdict66():
    h = make_hourly({13: 0.003, 14: 0.002}, n_days=300)
    good = {"cagr_cad_pct": 15.0, "max_dd_pct": -10.0}
    assert m.verdict66(h, [13, 14], good)["verdict"] == "PASS"
    assert m.verdict66(h, [13, 14], {"cagr_cad_pct": 5.0, "max_dd_pct": -10.0})["verdict"] == "INCERTAIN"
    assert m.verdict66(h, [13, 14], {"cagr_cad_pct": 15.0, "max_dd_pct": -30.0})["verdict"] == "INCERTAIN"
    hz = make_hourly({}, n_days=300)  # zero gross -> net = -cost < 0
    assert m.verdict66(hz, [13, 14], good)["verdict"] == "REJET"


def test_extract_stage_on_tmp_fixture(tmp_path):
    for s in m.SYMBOLS:
        bars(minutes=300).to_pickle(tmp_path / f"{s}_full.pkl")
    out = tmp_path / "out"
    m.stage_extract(data_dir=tmp_path, out=out)
    h = pd.read_parquet(out / "hourly.parquet")
    assert len(h) == 3 * 4 and set(h.symbol) == set(m.SYMBOLS)
