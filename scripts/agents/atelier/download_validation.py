"""T-074 -- download, WITHOUT end bound, the series listed in the common part of
docs/agents/research/atelier/candidats.md into data/atelier_validation/ (+ meta.json: url, date, sha256).

Raw bytes are saved without being parsed (only size + sha256 recorded).  Reading is done only by
loader_validation.py (pandas).  Extra series used only for "reported without effect" items:
FRED DEXCAUS (USD/CAD) and real-instrument ETFs (SPY, SSO, IEF, UST, sector SPDRs, IYZ).

Usage: py -3 scripts/agents/atelier/download_validation.py [fred kf yahoo etf]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("C:/AAProjet/quant_bot_v1/data/atelier_validation")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

FRED_IDS = ["DGS10", "BAA10Y", "IRLTLT01DEM156N", "IRLTLT01GBM156N", "IRLTLT01JPM156N",
            "IR3TIB01DEM156N", "IR3TIB01GBM156N", "IRSTCI01JPM156N",
            "DEXCAUS"]  # DEXCAUS: reported-only CAD conversion
KF_FILES = ["12_Industry_Portfolios_daily_CSV.zip", "30_Industry_Portfolios_daily_CSV.zip",
            "49_Industry_Portfolios_daily_CSV.zip", "F-F_Research_Data_Factors_daily_CSV.zip",
            "Developed_ex_US_3_Factors_Daily_CSV.zip"]
# file names = those the discovery code expects (exp74 cache names / atelier YH_ names)
YAHOO = {"^SP500TR": "IDX_SP500TR", "^GSPC": "IDX_GSPC", "^IRX": "IDX_IRX", "^NDX": "IDX_NDX",
         "^RUT": "IDX_RUT", "^GDAXI": "IDX_GDAXI", "^FTSE": "YH_IDX_FTSE", "^N225": "YH_IDX_N225"}
ETF = ["SPY", "SSO", "IEF", "UST", "XLP", "XLY", "XLI", "XLE", "XLB", "XLK", "IYZ", "XLU", "XLV", "XLF"]


def _get(url: str, ua: bool = True) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA} if ua else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _save(name: str, data: bytes, src: str, meta: dict):
    (OUT / name).write_bytes(data)
    meta[name] = {"source": src, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "downloaded_utc": datetime.now(timezone.utc).isoformat()}


def _yahoo(tickers: dict, meta: dict):
    import yfinance as yf
    for t, fn in tickers.items():
        df = yf.download(t, start="1980-01-01", auto_adjust=True, progress=False)
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)
        data = df[["Close"]].dropna().rename_axis("Date").to_csv().encode()
        _save(fn + ".csv", data, f"yfinance {t} start=1980-01-01 auto_adjust=True (no end)", meta)
        time.sleep(0.5)


def main(which: list[str]):
    OUT.mkdir(parents=True, exist_ok=True)
    mp = OUT / "meta.json"
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    if "fred" in which:
        for sid in FRED_IDS:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1900-01-01"
            try:
                _save(f"FRED_{sid}.csv", _get(url, ua=False), url, meta)
            except Exception as e:  # noqa: BLE001
                print("FRED fail", sid, e)
            time.sleep(0.5)
    if "kf" in which:
        base = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
        for fn in KF_FILES:
            try:
                _save(fn, _get(base + fn), base + fn, meta)
            except Exception as e:  # noqa: BLE001
                print("KF fail", fn, e)
    if "yahoo" in which:
        _yahoo(YAHOO, meta)
    if "etf" in which:
        _yahoo({t: "ETF_" + t for t in ETF}, meta)
    mp.write_text(json.dumps(meta, indent=1))
    for k, v in meta.items():
        print(k, v["bytes"])


if __name__ == "__main__":
    main(sys.argv[1:] or ["fred", "kf", "yahoo", "etf"])
