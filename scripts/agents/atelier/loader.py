"""T-073 / D-09 -- the ONLY data entry point of the strategy workshop ("atelier").

Hard rule (D-09 sec. 1): discovery data stop at 2009-12-31.  Every reader in this module drops,
row by row and before returning anything, every observation dated after CUTOFF.  The validation
period (2010-01-01 -> end) is locked; nothing in the atelier may read a data file except through
these functions.

Files read here are untrusted downloads: they are parsed as data only (pandas / csv text / zip /
openpyxl), never executed.

Default directories (overridable for tests by monkeypatching the module-level constants):
  EXP74_DIR    data/exp74_yahoo   (Yahoo: ^GSPC, ^SP500TR, ^IRX, ^NDX, ^RUT, ^GDAXI ... ; contains post-2009 rows)
  EXP76_DIR    data/exp76         (Ken French zips, AQR TSMOM xlsx ; contains post-2009 rows)
  ATELIER_DIR  data/atelier       (new downloads for T-073)
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

CUTOFF = pd.Timestamp("2009-12-31")
CUTOFF_MONTH = pd.Period("2009-12", "M")
_END = CUTOFF + pd.Timedelta(days=1)  # strict upper bound: anything at or after 2010-01-01 00:00 is dropped

DATA_ROOT = Path("C:/AAProjet/quant_bot_v1/data")
EXP74_DIR = DATA_ROOT / "exp74_yahoo"
EXP76_DIR = DATA_ROOT / "exp76"
ATELIER_DIR = DATA_ROOT / "atelier"


class PostCutoffError(AssertionError):
    """Raised if anything dated after the discovery cutoff would leave this module."""


# ---------------------------------------------------------------------------------------- guards
def _keep_date(ts) -> bool:
    return pd.Timestamp(ts) < _END


def _period_ok(idx: pd.PeriodIndex) -> np.ndarray:
    return np.asarray(idx.end_time < _END)


def assert_cut(obj):
    """Final guard on every returned object: index must be <= cutoff (dates) or <= 2009-12 (months)."""
    idx = obj.index
    if len(idx) == 0:
        return obj
    if isinstance(idx, pd.PeriodIndex):
        bad = ~_period_ok(idx)
    else:
        di = pd.DatetimeIndex(idx)
        if di.tz is not None:
            di = di.tz_convert(None)
        bad = di >= _END
    if np.asarray(bad).any():
        raise PostCutoffError(f"post-2009 observation leaked: max index {idx.max()}")
    return obj


def cut(obj):
    """Drop every row after the cutoff (DatetimeIndex or monthly/annual PeriodIndex)."""
    idx = obj.index
    if isinstance(idx, pd.PeriodIndex):
        keep = _period_ok(idx)
    else:
        di = pd.DatetimeIndex(idx)
        if di.tz is not None:
            di = di.tz_convert(None)
        keep = di < _END
    return assert_cut(obj[np.asarray(keep)])


# ---------------------------------------------------------------------------------------- csv
def read_dated_csv(path: Path, date_col: str | int = 0, na_values=(".", "", "NA", "null")) -> pd.DataFrame:
    """Generic dated CSV (Yahoo cache 'Date,Close', FRED 'observation_date,ID').  Rows after the
    cutoff are dropped immediately after the text is parsed, before any conversion/derivation."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    dcol = raw.columns[date_col] if isinstance(date_col, int) else date_col
    dates = pd.to_datetime(raw[dcol].str.slice(0, 10), errors="coerce")
    keep = dates.notna() & (dates < _END)
    raw = raw.loc[keep.values]
    dates = dates[keep.values]
    out = raw.drop(columns=[dcol]).replace(list(na_values), np.nan).apply(pd.to_numeric, errors="coerce")
    out.index = pd.DatetimeIndex(dates.values, name="date")
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return assert_cut(out)


def yahoo_close(name: str, directory: Path | None = None) -> pd.Series:
    """Close series from a Yahoo cache file, e.g. yahoo_close('IDX_SP500TR') (exp74 cache) or
    yahoo_close('YH_X', ATELIER_DIR)."""
    d = EXP74_DIR if directory is None else directory
    df = read_dated_csv(Path(d) / f"{name}.csv")
    s = df["Close"].dropna().astype(float)
    s.name = name
    return assert_cut(s)


def fred(series_id: str, directory: Path | None = None) -> pd.Series:
    """FRED series saved as FRED_<ID>.csv (fredgraph.csv format: observation_date,<ID>; '.' = missing)."""
    d = ATELIER_DIR if directory is None else directory
    df = read_dated_csv(Path(d) / f"FRED_{series_id}.csv")
    s = df.iloc[:, 0].dropna().astype(float)
    s.name = series_id
    return assert_cut(s)


# ---------------------------------------------------------------------------------------- Ken French
_DATE_RE = re.compile(r"^\s*(\d{8}|\d{6})\s*$")


def parse_kf_text(text: str, block: int = 0) -> pd.DataFrame:
    """Parse the `block`-th data block of a Ken French CSV (daily YYYYMMDD or monthly YYYYMM rows).
    Returns decimals (file values are percent).  Missing codes (-99.99, -999) -> NaN.  Each row is
    dropped as soon as its date is read if it is after the cutoff."""
    lines = text.splitlines()
    starts = []
    for i in range(len(lines) - 1):
        first = lines[i + 1].split(",")[0]
        if lines[i].lstrip().startswith(",") and _DATE_RE.match(first):
            starts.append(i)
    if block >= len(starts):
        raise ValueError(f"block {block} not found ({len(starts)} blocks)")
    h = starts[block]
    cols = [c.strip() for c in lines[h].split(",")[1:]]
    cols = [c for c in cols if c != ""]
    rows, idx, kind = [], [], None
    for ln in lines[h + 1:]:
        parts = [p.strip() for p in ln.split(",")]
        if not parts or not _DATE_RE.match(parts[0]):
            break
        code = parts[0]
        if len(code) == 8:
            kind = kind or "D"
            ts = pd.Timestamp(f"{code[:4]}-{code[4:6]}-{code[6:]}")
            if not _keep_date(ts):
                continue
            idx.append(ts)
        else:
            kind = kind or "M"
            per = pd.Period(f"{code[:4]}-{code[4:]}", "M")
            if per > CUTOFF_MONTH:
                continue
            idx.append(per)
        rows.append([float(p) for p in parts[1:len(cols) + 1]])
    df = pd.DataFrame(rows, columns=cols, dtype=float)
    df[(df <= -99.99) | (df >= 999)] = np.nan
    df = df / 100.0
    if kind == "M":
        df.index = pd.PeriodIndex(idx, freq="M")
    else:
        df.index = pd.DatetimeIndex(idx, name="date")
    return assert_cut(df)


def kf_zip(path: Path, block: int = 0) -> pd.DataFrame:
    """Ken French zip (one CSV inside).  Daily or monthly, decided by the file's date codes."""
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        text = z.read(name).decode("latin1")
    return parse_kf_text(text, block=block)


def kf(name: str, block: int = 0) -> pd.DataFrame:
    """Look a Ken French zip up by file name in EXP76_DIR then ATELIER_DIR."""
    for d in (EXP76_DIR, ATELIER_DIR):
        p = Path(d) / name
        if p.exists():
            return kf_zip(p, block=block)
    raise FileNotFoundError(name)


# ---------------------------------------------------------------------------------------- AQR
def aqr_tsmom(path: Path | None = None) -> pd.Series:
    """AQR 'Time Series Momentum: Factors, Monthly', column TSMOM (decimal excess return)."""
    p = (EXP76_DIR / "aqr_tsmom_monthly.xlsx") if path is None else Path(path)
    raw = pd.read_excel(p, sheet_name="TSMOM Factors", header=None, engine="openpyxl")
    h = next(i for i in range(len(raw)) if str(raw.iloc[i, 1]).strip() == "TSMOM")
    body = raw.iloc[h + 1:, [0, 1]].dropna()
    dates = pd.to_datetime(body[0])
    keep = (dates < _END).values
    body, dates = body.loc[keep], dates[keep]
    s = pd.Series(pd.to_numeric(body[1]).values, index=dates.dt.to_period("M"), name="TSMOM").astype(float)
    return assert_cut(s)


# ---------------------------------------------------------------------------------------- Shiller
def _shiller_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """raw: string DataFrame with a 'Date' column in Shiller's YYYY.MM format (1990.1 = October).
    Rows after 2009-12 are dropped before numeric conversion."""
    pers = []
    for v in raw["Date"].astype(str):
        m = re.match(r"^\s*(\d{4})\.(\d{1,2})\s*$", v)
        if not m:
            pers.append(None)
            continue
        mm = m.group(2)
        month = int(mm) * 10 if len(mm) == 1 else int(mm)  # 1990.1 means October
        pers.append(pd.Period(f"{m.group(1)}-{month:02d}", "M") if 1 <= month <= 12 else None)
    keep = np.array([q is not None and q <= CUTOFF_MONTH for q in pers], dtype=bool)
    raw = raw.loc[keep]
    out = raw.drop(columns=["Date"]).replace(["", "NA", ".", "nan"], np.nan).apply(pd.to_numeric, errors="coerce")
    out.index = pd.PeriodIndex([q for q in pers if q is not None and q <= CUTOFF_MONTH], freq="M")
    return assert_cut(out)


def shiller_csv(path: Path | None = None) -> pd.DataFrame:
    """Shiller monthly data as CSV with a 'Date' column (YYYY.MM)."""
    p = (ATELIER_DIR / "shiller_monthly.csv") if path is None else Path(path)
    return _shiller_frame(pd.read_csv(p, dtype=str, keep_default_na=False))


def shiller_xls(path: Path | None = None) -> pd.DataFrame:
    """Shiller ie_data.xls, sheet 'Data' (header row whose first cell is 'Date').  Dates are floats
    YYYY.MM; they are formatted with 2 decimals (1990.1 -> '1990.10' = October) then cut."""
    p = (ATELIER_DIR / "shiller_ie_data.xls") if path is None else Path(path)
    raw = pd.read_excel(p, sheet_name="Data", header=None, engine="xlrd", dtype=object)
    h = next(i for i in range(len(raw)) if str(raw.iloc[i, 0]).strip() == "Date")
    cols, seen = [], {}
    for j, c in enumerate(raw.iloc[h].tolist()):
        name = str(c).strip() if c is not None and str(c) != "nan" else f"col{j}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        cols.append(name)
    body = raw.iloc[h + 1:].copy()
    body.columns = cols
    def fmt(v):
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return ""
    body["Date"] = body["Date"].map(fmt)
    body = body.astype(str)
    return _shiller_frame(body)
