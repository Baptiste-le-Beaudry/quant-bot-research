"""T-074 validation runner: verdict logic, DSR, CAD conversion, and the interception of the unchanged
discovery control code (k must NOT be re-solved).  Synthetic data only; files under tmp_path."""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "agents" / "atelier"))
import validate as V  # noqa: E402


def test_verdict_pass_reject_uncertain():
    ok = dict(cagr_=0.16, maxdd=-0.3, dsr=0.96)
    assert V.verdict(dsharpe=0.2, ctl_d=[0.1, 0.2, -0.1], **ok)["verdict"] == "PASS"
    assert V.verdict(dsharpe=0.2, ctl_d=[0.1, -0.2, -0.1], **ok)["verdict"] == "REJET"  # majority of controls <= 0
    assert V.verdict(dsharpe=0.0, ctl_d=[0.1, 0.2, 0.3], **ok)["verdict"] == "REJET"    # dSharpe <= 0
    assert V.verdict(0.149, -0.3, 0.2, [0.1, 0.2, 0.3], 0.96)["verdict"] == "INCERTAIN"
    assert V.verdict(0.16, -0.51, 0.2, [0.1, 0.2, 0.3], 0.96)["verdict"] == "INCERTAIN"
    assert V.verdict(dsharpe=0.05, ctl_d=[0.1, 0.2, 0.3], **ok)["verdict"] == "INCERTAIN"
    assert V.verdict(0.16, -0.3, 0.2, [0.1, 0.2, 0.3], 0.94)["verdict"] == "INCERTAIN"
    # 2 controls: 1 positive, 1 non-positive -> not a majority <= 0, but criterion 4 fails
    v = V.verdict(dsharpe=0.2, ctl_d=[0.1, -0.1], **ok)
    assert v["verdict"] == "INCERTAIN" and not v["c4_controls"]
    assert V.verdict(dsharpe=0.2, ctl_d=[0.1, 0.0], **ok)["n_controls_pos"] == 1  # 0 is not > 0
    assert V.verdict(dsharpe=0.2, ctl_d=[0.1, 0.2], **ok)["verdict"] == "PASS"


def test_dsr_threshold_and_formula():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2010-01-04", periods=4000)
    rf = pd.Series(0.0, index=idx)
    r = pd.Series(rng.normal(0.0004, 0.01, len(idx)), index=idx)
    out = V.deflated_sharpe(r, rf)
    sd = 0.1116 / math.sqrt(252)
    em = 0.5772156649
    from scipy.stats import norm
    sr0 = sd * ((1 - em) * norm.ppf(1 - 1 / 117) + em * norm.ppf(1 - 1 / (117 * math.e)))
    assert out["sr0_ann"] == pytest.approx(sr0 * math.sqrt(252))
    assert out["sr0_ann"] == pytest.approx(0.1116 * 2.5, rel=0.1)  # ~ 2.5 sd for N = 117
    assert out["n_trials"] == 117
    worse = V.deflated_sharpe(r - 0.0004, rf)
    assert worse["dsr"] < out["dsr"]


def test_to_cad():
    idx = pd.bdate_range("2020-01-01", periods=3)
    r = pd.Series([0.0, 0.01, 0.0], index=idx)
    fx = pd.Series([1.30, 1.313, 1.313], index=idx)  # USD up 1 % vs CAD on day 2
    c = V.to_cad(r, fx)
    assert c.iloc[1] == pytest.approx(1.01 * 1.01 - 1)
    assert c.iloc[2] == pytest.approx(0.0)


def test_top3_share():
    idx = pd.bdate_range("2010-01-01", "2014-12-31")
    r = pd.Series(0.0, index=idx)
    ref = pd.Series(0.0, index=idx)
    r[r.index.year == 2012] = 0.001
    out = V.top3_share(r, ref)
    assert out["years"][0] == 2012 and out["share"] == pytest.approx(1.0)


def _synthetic_cache(n=1500, seed=1):
    rng = np.random.default_rng(seed)
    cal = pd.bdate_range("2004-01-02", periods=n)
    eq = pd.Series(rng.normal(0.0003, 0.01, n), index=cal)
    d = {"cal": cal, "EQ": eq, "gspc": 100 * (1 + eq).cumprod(), "rf": pd.Series(0.0001, index=cal),
         "B10": pd.Series(rng.normal(0.0002, 0.004, n), index=cal),
         "baa10y": pd.Series(2 + np.cumsum(rng.normal(0, 0.02, n)), index=cal)}
    return d


def test_c09_control_is_captured_not_rescaled(tmp_path, monkeypatch):
    d = _synthetic_cache()
    monkeypatch.setattr(V.D, "_CACHE", d)
    px = 50 * (1 + pd.Series(np.random.default_rng(2).normal(0.0004, 0.012, len(d["cal"])), index=d["cal"])).cumprod()
    pd.DataFrame({"Date": d["cal"].strftime("%Y-%m-%d"), "Close": px.values}).to_csv(tmp_path / "IDX_NDX.csv", index=False)
    old = V.LV.ATELIER_DIR
    V.LV.set_dir(tmp_path)
    monkeypatch.setattr(V.C, "L", V.LV)
    called = {"n": 0}
    monkeypatch.setattr(V.E, "scale_to_vol", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    try:
        w, rets, mkt, start = V.captured_c09_control("NDX")
    finally:
        V.LV.set_dir(old)
    assert called["n"] == 0
    assert list(w.columns) == ["EQX", "B10"] and set(np.unique(w["EQX"].dropna())) <= {0.0, 1.0}
    assert (w.loc[:start] == 0).all().all()
    assert V.C._eval_daily.__name__ == "_eval_daily"  # restored


def test_end_date_uses_min_source(monkeypatch):
    cal = pd.bdate_range("2026-08-03", "2026-10-09")
    monkeypatch.setattr(V.D, "_CACHE", {"cal": cal})
    last = {"tr": pd.Timestamp("2026-10-09"), "ind12": pd.Timestamp("2026-08-31")}
    assert V.end_date(["tr"], last) == pd.Timestamp("2026-10-09")
    assert V.end_date(["tr", "ind12"], last) == pd.Timestamp("2026-08-31")
