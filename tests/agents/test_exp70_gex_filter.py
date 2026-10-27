"""Tests for the Exp 70 GEX filter (synthetic fixtures only, tmp_path)."""
import datetime as dt
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp70", ROOT / "scripts" / "agents" / "exp70_gex_filter.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _sessions(start, n):
    out, d = [], start
    while len(out) < n:
        if m.e64.is_session(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def test_percentile_strict_rank_and_window():
    g = pd.DataFrame({"date": _sessions(dt.date(2020, 1, 2), 5), "gex": [1.0, 2.0, 3.0, 2.0, 0.5]})
    p = m.gex_percentile(g, window=3)
    assert np.isnan(p["pct"].iloc[2])
    assert p["pct"].iloc[3] == 1 / 3          # prev 1,2,3 ; strictly below 2 -> {1}
    assert p["pct"].iloc[4] == 0.0


def test_percentile_matches_gex_split_reference():
    rng = np.random.default_rng(0)
    g = pd.DataFrame({"date": _sessions(dt.date(2015, 1, 2), 400), "gex": rng.normal(size=400)})
    p = m.gex_percentile(g)
    s = g.set_index("date")["gex"]
    ref = s.rolling(252, min_periods=252).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    assert np.allclose(p["pct"].to_numpy()[251:], ref.to_numpy()[251:])


def test_prev_alignment_strictly_before_and_gap():
    ses = _sessions(dt.date(2021, 3, 1), 6)
    gexp = pd.DataFrame({"date": [ses[0], ses[1], ses[3]], "gex": [1.0, 2.0, 3.0], "pct": [0.1, 0.9, 0.5]})
    days = pd.DataFrame({"date": ses[1:5], "n_trades": 1, "gross_usd": 5.0, "cost_usd": 1.0, "net_usd": 4.0,
                         "gross_pct": 0.0, "net_pct": 0.0})
    a = m.attach_prev_gex(days, gexp)
    # day ses[1] uses ses[0] (never same-day value)
    assert list(a["gex_prev_date"]) == [ses[0], ses[1], ses[1], ses[3]]
    assert list(a["gex_prev_is_prev_session"]) == [True, True, False, True]
    assert list(a["pct_prev"]) == [0.1, 0.9, 0.9, 0.5]


def test_filter_zeroes_whole_day_and_threshold_strict():
    days = pd.DataFrame({"date": _sessions(dt.date(2022, 1, 3), 4), "n_trades": [1, 2, 1, 0],
                         "gross_usd": [10.0, -20.0, 5.0, 0.0], "cost_usd": [2.22, 4.44, 2.22, 0.0],
                         "net_usd": [7.78, -24.44, 2.78, 0.0], "gross_pct": 0.1, "net_pct": 0.1,
                         "pct_prev": [2 / 3, 0.9, np.nan, 0.99]})
    f, flat = m.apply_filter(days, 2 / 3)
    assert list(flat) == [False, True, False, True]      # exactly 2/3 is not > 2/3 ; NaN -> trade
    assert f.loc[1, ["n_trades", "gross_usd", "cost_usd", "net_usd", "net_pct"]].tolist() == [0, 0, 0, 0, 0]
    assert f.loc[0, "net_usd"] == 7.78 and f.loc[2, "net_usd"] == 2.78


def _st(s, mdd, t5):
    return {"sharpe_net": s, "maxdd_usd": mdd, "top5_share_of_net": t5}


def test_verdict70():
    u = _st(0.81, -3949, 0.9)
    assert m.verdict70(_st(0.9, -1900, 0.4), u)["verdict"] == "PASS"
    assert m.verdict70(_st(0.9, -2600, 0.4), u)["verdict"] == "REJET"
    assert m.verdict70(_st(0.49, -1000, 0.4), u)["verdict"] == "REJET"
    assert m.verdict70(_st(0.80, -1000, 0.4), u)["verdict"] == "REJET"     # below unfiltered 0.81
    assert m.verdict70(_st(0.9, -2200, 0.4), u)["verdict"] == "INCERTAIN"
    assert m.verdict70(_st(0.9, -1900, 0.6), u)["verdict"] == "INCERTAIN"
    assert m.verdict70(_st(0.9, -1900, None), u)["verdict"] == "INCERTAIN"  # non-positive net
    assert m.verdict70(_st(0.9, -2000, 0.5), u)["verdict"] == "PASS"        # boundaries inclusive


def test_top5_share():
    assert m.top5_share(pd.Series([10.0, 1, 1, 1, 1, 1, -5])) == 14 / 10
    assert m.top5_share(pd.Series([-1.0, 0.0])) is None


def test_end_to_end_tmp(tmp_path):
    rng = np.random.default_rng(1)
    ses = _sessions(dt.date(2023, 1, 3), 400)
    dix = pd.DataFrame({"date": ses, "price": 1.0, "dix": 0.4, "gex": rng.normal(size=400)})
    dix.to_csv(tmp_path / "dix.csv", index=False)
    gexp = m.gex_percentile(m.load_gex(tmp_path / "dix.csv", expected_sha=None))
    days = pd.DataFrame({"date": ses[300:], "n_trades": 1, "gross_usd": rng.normal(10, 50, 100)})
    days["cost_usd"] = 2.22
    days["net_usd"] = days["gross_usd"] - 2.22
    days["gross_pct"] = 0.0
    days["net_pct"] = 0.0
    blk, out = m.evaluate(days, gexp)
    assert blk["alignment"]["pct_undefined_days_traded_unchanged"] == 0
    assert blk["alignment"]["max_gex_prev_date_lt_date"]
    assert blk["flat_days_2_3"] == int((out["pct_prev"] > 2 / 3).sum())
    assert np.isclose(out["net_usd_filtered_2_3"].sum(), days["net_usd"].sum() - blk["net_removed_by_2_3_usd"])
    assert np.isclose(blk["unfiltered"]["total_net_usd"], days["net_usd"].sum())
