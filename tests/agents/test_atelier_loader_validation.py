"""T-074: validation loader of the atelier.  It must (1) return post-2009 rows, (2) parse exactly like
the discovery loader on pre-2010 rows, (3) leave the discovery loader's 2009-12-31 cut intact.
Synthetic fixtures only, all under tmp_path (never a real data path)."""
import importlib.util
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
ATELIER = ROOT / "scripts" / "agents" / "atelier"
sys.path.insert(0, str(ATELIER))


def _mod(name, file):
    spec = importlib.util.spec_from_file_location(name, ATELIER / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


LV = _mod("atelier_loader_validation_t", "loader_validation.py")
LD = _mod("atelier_loader_discovery_t", "loader.py")
CUT = pd.Timestamp("2009-12-31")
DATES = ["2009-12-30", "2009-12-31", "2010-01-01", "2010-01-04", "2015-06-01", "2026-10-09"]


@pytest.fixture
def d(tmp_path, monkeypatch):
    v = tmp_path / "val"
    v.mkdir()
    old = LV.ATELIER_DIR
    LV.set_dir(v)
    for k in ("EXP74_DIR", "EXP76_DIR", "ATELIER_DIR"):
        monkeypatch.setattr(LD, k, v)
    yield v
    LV.set_dir(old)


def _kf_text(daily=True):
    codes = ["20091230", "20091231", "20100104", "20201231"] if daily else ["200911", "200912", "201001", "202605"]
    body = ",Mkt-RF,SMB,HML,RF\n" + "\n".join(f"{c},  1.00,  0.50, -99.99,  0.01" for c in codes)
    annual = "\n\n Annual Factors: January-December \n,Mkt-RF,SMB,HML,RF\n  2009,  25.0, 1.0, 1.0, 0.1\n"
    return "This file was created by ...\n\n" + body + annual


def _zip(path, text):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("X.csv", text)


def test_default_dir_is_validation_dir_not_discovery():
    assert LV.VALIDATION_DIR.name == "atelier_validation"
    assert LV.VALIDATION_DIR != LD.ATELIER_DIR


def test_yahoo_keeps_post_2009_and_matches_discovery_before(d):
    pd.DataFrame({"Date": DATES, "Close": [1, 2, 3, 4, 5, 6]}).to_csv(d / "IDX_T.csv", index=False)
    s = LV.yahoo_close("IDX_T")
    assert s.index.max() == pd.Timestamp("2026-10-09") and len(s) == 6
    sd = LD.yahoo_close("IDX_T")
    assert sd.index.max() == CUT
    pd.testing.assert_series_equal(s.loc[:CUT], sd)


def test_yahoo_tz_strings(d):
    pd.DataFrame({"Date": [x + " 00:00:00-05:00" for x in DATES], "Close": range(6)}).to_csv(d / "YH_T.csv", index=False)
    assert len(LV.yahoo_close("YH_T")) == 6


def test_fred_missing_and_post_2009(d):
    pd.DataFrame({"observation_date": DATES, "BAA10Y": ["3.8", ".", "3.9", "4.0", "2.0", "4.1"]}).to_csv(
        d / "FRED_BAA10Y.csv", index=False)
    s = LV.fred("BAA10Y")
    assert list(s.index) == [pd.Timestamp(x) for x in DATES if x != "2009-12-31"]
    assert s.iloc[-1] == pytest.approx(4.1)
    pd.testing.assert_series_equal(s.loc[:CUT], LD.fred("BAA10Y"))


def test_kf_daily_and_monthly(d):
    _zip(d / "K_daily.zip", _kf_text(True))
    _zip(d / "K_m.zip", _kf_text(False))
    df = LV.kf("K_daily.zip")
    assert df.index.max() == pd.Timestamp("2020-12-31") and len(df) == 4
    assert df["Mkt-RF"].iloc[-1] == pytest.approx(0.01) and df["HML"].isna().all()
    pd.testing.assert_frame_equal(df.loc[:CUT], LD.kf("K_daily.zip"))
    dm = LV.kf("K_m.zip")
    assert dm.index.max() == pd.Period("2026-05", "M")


def test_discovery_loader_still_cuts_after_validation_import(d):
    pd.DataFrame({"Date": DATES, "Close": [1, 2, 3, 4, 5, 6]}).to_csv(d / "IDX_U.csv", index=False)
    assert LD._END == pd.Timestamp("2010-01-01")
    assert LD.yahoo_close("IDX_U").index.max() == CUT
    import loader as L_shared  # the module object discovery.py imports
    assert L_shared._END == pd.Timestamp("2010-01-01")
    assert L_shared.CUTOFF == CUT


def test_kf_missing_file(d):
    with pytest.raises(FileNotFoundError):
        LV.kf("nope.zip")


@pytest.mark.parametrize("last,exp", [("2026-10-09", "2026-09"), ("2026-09-30", "2026-09"),
                                      ("2026-08-31", "2026-08"), ("2026-08-28", "2026-07")])
def test_last_complete_month(last, exp):
    assert LV.last_complete_month(last) == pd.Period(exp, "M")
