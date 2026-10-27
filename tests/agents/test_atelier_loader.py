"""T-073: the atelier loader must never return anything dated after 2009-12-31.
Synthetic fixtures only, all under tmp_path (never a real data path)."""
import importlib.util
import inspect
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("atelier_loader", ROOT / "scripts" / "agents" / "atelier" / "loader.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

CUT = pd.Timestamp("2009-12-31")


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    d74, d76, dat = tmp_path / "e74", tmp_path / "e76", tmp_path / "at"
    for d in (d74, d76, dat):
        d.mkdir()
    monkeypatch.setattr(L, "EXP74_DIR", d74)
    monkeypatch.setattr(L, "EXP76_DIR", d76)
    monkeypatch.setattr(L, "ATELIER_DIR", dat)
    return d74, d76, dat


def _dates():
    return ["2009-12-30", "2009-12-31", "2010-01-01", "2010-01-04", "2015-06-01", "2026-10-09"]


def test_yahoo_cache_cut(dirs):
    d74, _, _ = dirs
    pd.DataFrame({"Date": _dates(), "Close": [1, 2, 3, 4, 5, 6]}).to_csv(d74 / "IDX_TEST.csv", index=False)
    s = L.yahoo_close("IDX_TEST")
    assert s.index.max() == CUT
    assert list(s.values) == [1, 2]
    assert (s.index <= CUT).all()


def test_yahoo_with_timestamp_strings_cut(dirs):
    d74, _, _ = dirs
    pd.DataFrame({"Date": [d + " 00:00:00-05:00" for d in _dates()], "Close": range(6)}).to_csv(
        d74 / "IDX_TZ.csv", index=False)
    s = L.yahoo_close("IDX_TZ")
    assert s.index.max() == CUT and len(s) == 2


def test_fred_cut_and_missing(dirs):
    _, _, dat = dirs
    pd.DataFrame({"observation_date": _dates(), "DGS10": ["3.8", ".", "3.9", "4.0", "2.0", "4.1"]}).to_csv(
        dat / "FRED_DGS10.csv", index=False)
    s = L.fred("DGS10")
    assert list(s.index) == [pd.Timestamp("2009-12-30")]  # 12-31 is '.', dropped as missing
    assert s.iloc[0] == pytest.approx(3.8)


def _kf_text(daily=True):
    head = "This file was created by ...\n\n"
    if daily:
        codes = ["20091230", "20091231", "20100104", "20201231"]
    else:
        codes = ["200911", "200912", "201001", "202605"]
    body = ",Mkt-RF,SMB,HML,RF\n" + "\n".join(f"{c},  1.00,  0.50, -99.99,  0.01" for c in codes)
    annual = "\n\n Annual Factors: January-December \n,Mkt-RF,SMB,HML,RF\n  2009,  25.0, 1.0, 1.0, 0.1\n  2010, 15.0, 1, 1, 0.1\n"
    return head + body + annual


def _zip(path, text):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("X.csv", text)


def test_kf_daily_zip_cut(dirs):
    _, d76, _ = dirs
    _zip(d76 / "K_daily.zip", _kf_text(True))
    df = L.kf("K_daily.zip")
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.max() == CUT and len(df) == 2
    assert df["Mkt-RF"].iloc[0] == pytest.approx(0.01)
    assert df["HML"].isna().all()  # missing code


def test_kf_monthly_zip_cut(dirs):
    _, _, dat = dirs
    _zip(dat / "K_m.zip", _kf_text(False))
    df = L.kf("K_m.zip")
    assert isinstance(df.index, pd.PeriodIndex)
    assert df.index.max() == pd.Period("2009-12", "M") and len(df) == 2


def test_kf_second_block_is_also_cut(dirs):
    _, _, dat = dirs
    text = _kf_text(False) + "\n\n Second block\n,A,B\n200912, 1, 2\n201001, 3, 4\n"
    _zip(dat / "K2.zip", text)
    df = L.kf("K2.zip", block=1)
    assert len(df) == 1 and df.index.max() == pd.Period("2009-12", "M")


def test_aqr_xlsx_cut(dirs, tmp_path):
    _, d76, _ = dirs
    rows = [["AQR header", None], [None, None], ["Date", "TSMOM"]]
    for d, v in [("2009-11-30", 0.01), ("2009-12-31", 0.02), ("2010-01-31", 0.03), ("2026-05-31", 0.04)]:
        rows.append([pd.Timestamp(d), v])
    with pd.ExcelWriter(d76 / "aqr_tsmom_monthly.xlsx", engine="openpyxl") as w:
        pd.DataFrame(rows).to_excel(w, sheet_name="TSMOM Factors", header=False, index=False)
    s = L.aqr_tsmom()
    assert list(s.values) == [0.01, 0.02]
    assert s.index.max() == pd.Period("2009-12", "M")


def test_shiller_csv_cut_and_october_format(dirs):
    _, _, dat = dirs
    pd.DataFrame({"Date": ["2009.09", "2009.1", "2009.12", "2010.01", "2015.1"],
                  "P": [1, 2, 3, 4, 5], "CAPE": [20, 21, 22, 23, 24]}).to_csv(dat / "shiller_monthly.csv", index=False)
    df = L.shiller_csv()
    assert list(df.index.astype(str)) == ["2009-09", "2009-10", "2009-12"]
    assert list(df["P"]) == [1, 2, 3]


def test_cut_and_assert_cut_generic():
    s = pd.Series(range(4), index=pd.to_datetime(["2009-12-31", "2009-12-31 23:00", "2010-01-01", "2012-01-01"], format="mixed"))
    out = L.cut(s)
    assert len(out) == 2
    with pytest.raises(L.PostCutoffError):
        L.assert_cut(s)
    m = pd.Series(range(3), index=pd.period_range("2009-11", periods=3, freq="M"))
    assert len(L.cut(m)) == 2
    with pytest.raises(L.PostCutoffError):
        L.assert_cut(m)


def test_every_public_reader_is_covered_by_a_test():
    """Any new reader added to the loader must get a cutoff test here."""
    readers = {n for n, f in inspect.getmembers(L, inspect.isfunction)
               if f.__module__ == L.__name__ and not n.startswith("_")}
    covered = {"yahoo_close", "fred", "kf", "kf_zip", "parse_kf_text", "aqr_tsmom", "shiller_csv",
               "read_dated_csv", "cut", "assert_cut", "shiller_xls"}
    assert readers <= covered, f"untested readers: {readers - covered}"


def test_cutoff_constant_is_2009():
    assert L.CUTOFF == CUT
    assert L.CUTOFF_MONTH == pd.Period("2009-12", "M")


def test_shiller_xls_path_uses_same_cut(dirs, monkeypatch):
    """shiller_xls formats float dates then goes through _shiller_frame (xls writing is not available,
    so read_excel is replaced by a synthetic frame)."""
    raw = pd.DataFrame([["title", None, None], ["Date", "P", "CAPE"], [2009.09, 1.0, 20.0], [2009.1, 2.0, 21.0],
                        [2009.12, 3.0, 22.0], [2010.01, 4.0, 23.0], [2020.1, 5.0, 30.0]], dtype=object)
    monkeypatch.setattr(L.pd, "read_excel", lambda *a, **k: raw)
    df = L.shiller_xls(Path("unused.xls"))
    assert list(df.index.astype(str)) == ["2009-09", "2009-10", "2009-12"]
    assert list(df["CAPE"]) == [20.0, 21.0, 22.0]
