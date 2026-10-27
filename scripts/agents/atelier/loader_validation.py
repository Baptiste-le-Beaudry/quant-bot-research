"""T-074 / D-09 -- data entry point for the ONE-SHOT validation (2010-01-04 -> end) of Exp 77-80.

Design (kept deliberately minimal so that the discovery parsing is reused unchanged):
  * `loader.py` (discovery, hard cut at 2009-12-31) is NOT modified and keeps its cut.
  * This module loads a SEPARATE module instance of loader.py (importlib, private name
    `atelier_loader_validation_impl`) and lifts the cut on that instance only (_END / CUTOFF_MONTH
    set far in the future).  Every parser (Yahoo cache, FRED csv, Ken French zip) is therefore
    byte-for-byte the discovery code; only the end bound differs.
  * Default directory: data/atelier_validation (fresh downloads without end bound, see
    download_validation.py).  Both EXP74_DIR and ATELIER_DIR point there, so the discovery code's
    file names (IDX_SP500TR.csv, YH_IDX_FTSE.csv, FRED_<ID>.csv, Ken French zips) resolve to it.
  * Pre-2010 history is returned too: it is the warm-up allowed by the preregistration (MM200,
    252-day spread mean, 12-1 momentum, 63-day vol).  Metrics are computed by the caller on
    VAL_START -> end only.

Files are untrusted downloads: parsed as data only (pandas / csv text / zip), never executed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA_ROOT = Path("C:/AAProjet/quant_bot_v1/data")
VALIDATION_DIR = DATA_ROOT / "atelier_validation"

VAL_START = pd.Timestamp("2010-01-04")       # first metric date (daily)
VAL_START_MONTH = pd.Period("2010-01", "M")  # first metric month (monthly controls)
_FAR = pd.Timestamp("2200-01-01")


def _load_impl():
    name = "atelier_loader_validation_impl"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HERE / "loader.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # lift the cut on THIS instance only (the discovery module object `loader` is untouched)
    mod.CUTOFF = _FAR
    mod.CUTOFF_MONTH = pd.Period("2199-12", "M")
    mod._END = _FAR
    mod.EXP74_DIR = VALIDATION_DIR
    mod.EXP76_DIR = VALIDATION_DIR
    mod.ATELIER_DIR = VALIDATION_DIR
    sys.modules[name] = mod
    return mod


_IMPL = _load_impl()

# Same API as loader.py (so discovery.py / controls.py can use this module as their `L`).
EXP74_DIR = VALIDATION_DIR
EXP76_DIR = VALIDATION_DIR
ATELIER_DIR = VALIDATION_DIR


def set_dir(directory: Path):
    """Point every reader at `directory` (tests use tmp_path; never a real data path in tests)."""
    global EXP74_DIR, EXP76_DIR, ATELIER_DIR
    EXP74_DIR = EXP76_DIR = ATELIER_DIR = Path(directory)
    _IMPL.EXP74_DIR = _IMPL.EXP76_DIR = _IMPL.ATELIER_DIR = Path(directory)


def read_dated_csv(path, date_col=0, na_values=(".", "", "NA", "null")) -> pd.DataFrame:
    return _IMPL.read_dated_csv(Path(path), date_col, na_values)


def yahoo_close(name: str, directory: Path | None = None) -> pd.Series:
    return _IMPL.yahoo_close(name, ATELIER_DIR if directory is None else directory)


def fred(series_id: str, directory: Path | None = None) -> pd.Series:
    return _IMPL.fred(series_id, ATELIER_DIR if directory is None else directory)


def parse_kf_text(text: str, block: int = 0) -> pd.DataFrame:
    return _IMPL.parse_kf_text(text, block)


def kf_zip(path, block: int = 0) -> pd.DataFrame:
    return _IMPL.kf_zip(Path(path), block)


def kf(name: str, block: int = 0) -> pd.DataFrame:
    p = Path(ATELIER_DIR) / name
    if not p.exists():
        raise FileNotFoundError(name)
    return _IMPL.kf_zip(p, block)


def last_complete_month(last_date) -> pd.Period:
    """Last calendar month that is complete given the last available session `last_date`: the
    month of last_date if last_date is on/after that month's last weekday (Mon-Fri), else the
    previous month (holidays ignored: conservative, a month may be dropped, never added)."""
    ts = pd.Timestamp(last_date).normalize()
    per = ts.to_period("M")
    last_wd = pd.bdate_range(per.start_time, per.end_time)[-1]
    return per if ts >= last_wd else per - 1
