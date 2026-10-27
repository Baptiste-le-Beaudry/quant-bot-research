"""T-073 -- download free series for the atelier into data/atelier/.

Raw bytes are saved without being parsed or inspected (only size + sha256 are recorded).
Wherever the source supports it (FRED, Yahoo), the request itself stops at 2009-12-31.
Ken French zips and the Shiller file always contain the full history: they are only ever read
through scripts/agents/atelier/loader.py, which drops every row after 2009-12-31.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("C:/AAProjet/quant_bot_v1/data/atelier")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

FRED_IDS = [
    # daily
    "DGS10", "DGS1", "DTB3", "BAA10Y", "AAA10Y", "T10Y3M", "T10Y2Y",
    # monthly (long warm-up history)
    "GS10", "TB3MS", "BAA", "AAA",
    # control markets: long-term government yields and 3-month rates (OECD, monthly)
    "IRLTLT01DEM156N", "IRLTLT01JPM156N", "IRLTLT01GBM156N",
    "IR3TIB01DEM156N", "IR3TIB01JPM156N", "IR3TIB01GBM156N", "IRSTCI01JPM156N",
]
KF_FILES = [
    "F-F_Research_Data_Factors_daily_CSV.zip",
    "12_Industry_Portfolios_daily_CSV.zip",
    "12_Industry_Portfolios_CSV.zip",
    "Developed_ex_US_3_Factors_Daily_CSV.zip",
    "Europe_3_Factors_Daily_CSV.zip",
    "Japan_3_Factors_Daily_CSV.zip",
    "Asia_Pacific_ex_Japan_3_Factors_Daily_CSV.zip",
    "30_Industry_Portfolios_daily_CSV.zip",
    "49_Industry_Portfolios_daily_CSV.zip",
]
YAHOO = ["^FTSE", "^N225", "IEF", "TLT", "SPY"]
SHILLER_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"


def _get(url: str, ua: bool = True) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA} if ua else {})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _save(name: str, data: bytes, src: str, meta: dict):
    (OUT / name).write_bytes(data)
    meta[name] = {"source": src, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "downloaded_utc": datetime.now(timezone.utc).isoformat()}


def main(which: list[str]):
    OUT.mkdir(parents=True, exist_ok=True)
    mp = OUT / "meta.json"
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    if "fred" in which:
        for sid in FRED_IDS:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1900-01-01&coed=2009-12-31"
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
        import yfinance as yf
        for t in YAHOO:
            df = yf.download(t, start="1980-01-01", end="2010-01-01", auto_adjust=True, progress=False)
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(0)
            data = df[["Close"]].rename_axis("Date").to_csv().encode()
            _save("YH_" + t.replace("^", "IDX_").replace("=", "_") + ".csv", data, f"yfinance {t} end=2010-01-01", meta)
    if "shiller" in which:
        try:
            _save("shiller_ie_data.xls", _get(SHILLER_URL), SHILLER_URL, meta)
        except Exception as e:  # noqa: BLE001
            print("Shiller fail", e)
    mp.write_text(json.dumps(meta, indent=1))
    for k, v in meta.items():
        print(k, v["bytes"])


if __name__ == "__main__":
    main(sys.argv[1:] or ["fred", "kf", "yahoo", "shiller"])
