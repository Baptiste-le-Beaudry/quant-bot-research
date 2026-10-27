"""Audit frozen candidate OHLCV and preregister positional HOLDOUT boundaries.

RESEARCH_ONLY / NOT_ADOPTED / NOT_FORWARD_PAPER. Run before any feature,
label, model, trade or profitability calculation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "outputs/strategy_a/universe_expansion/data"
OUT = ROOT / "outputs/strategy_a/universe_expansion"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def audit(path: Path) -> tuple[dict, dict]:
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    idx = pd.to_datetime(frame.index, utc=True, errors="coerce")
    numeric = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    duplicate_count = int(idx.duplicated().sum())
    invalid_ts = int(idx.isna().sum())
    ordered = pd.DatetimeIndex(idx.dropna()).sort_values().drop_duplicates()
    delta = ordered.to_series().diff().dropna()
    missing_minutes = int(np.maximum(delta.dt.total_seconds().to_numpy() // 60 - 1, 0).sum())
    large_gaps = int((delta > pd.Timedelta(minutes=5)).sum())
    ohlc_bad = int(((numeric.low > numeric[["open", "close", "high"]].min(axis=1)) |
                    (numeric.high < numeric[["open", "close", "low"]].max(axis=1))).sum())
    nonfinite = int((~np.isfinite(numeric.to_numpy())).sum())
    nonpositive_price = int((numeric[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    negative_volume = int((numeric.volume < 0).sum())
    n = len(ordered)
    split = int(np.floor(0.80 * n))
    enough = split > 24 * 30 * 24 * 60 and n - split > 3 * 30 * 24 * 60
    hard_ok = not any((invalid_ts, duplicate_count, ohlc_bad, nonfinite,
                       nonpositive_price, negative_volume)) and enough
    report = {
        "symbol": path.name.split("_", 1)[0], "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path), "bars": n,
        "first_available_timestamp": ordered[0].isoformat() if n else None,
        "last_available_timestamp": ordered[-1].isoformat() if n else None,
        "duplicates": duplicate_count, "invalid_timestamps": invalid_ts,
        "missing_minutes": missing_minutes, "large_gaps_gt_5m": large_gaps,
        "ohlc_inconsistencies": ohlc_bad, "nonfinite_values": nonfinite,
        "nonpositive_price_rows": nonpositive_price, "negative_volume_rows": negative_volume,
        "pre_holdout_bars": split, "data_completeness_pct": 100 * n / (n + missing_minutes) if n else 0,
        "funding_status": "FUNDING_NOT_MODELED", "decision": "DATA_PASS" if hard_ok else "DATA_REJECT",
    }
    holdout = {
        "symbol": report["symbol"], "n_bars": n, "pre_holdout_bars": split,
        "safe_end": ordered[split - 1].isoformat() if hard_ok else None,
        "holdout_start": ordered[split].isoformat() if hard_ok else None,
    }
    return report, holdout


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA.glob("*USDT_1m_*.csv"))
    if not files:
        raise SystemExit("No frozen-batch data found; run download_candidates.py first")
    reports, registry = zip(*(audit(path) for path in files))
    envelope = {"research_status": ["RESEARCH_ONLY", "NOT_ADOPTED", "NOT_FORWARD_PAPER"],
                "batch_id": "UE-20260825-01", "symbols": list(reports)}
    holdouts = {"research_status": ["RESEARCH_ONLY", "NOT_ADOPTED", "NOT_FORWARD_PAPER"],
                "method": "floor(0.80*n_bars), positional, timestamp UTC", "symbols": list(registry)}
    (OUT / "data_audit.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    (OUT / "holdout_registry.json").write_text(json.dumps(holdouts, indent=2), encoding="utf-8")
    return int(any(x["decision"] != "DATA_PASS" for x in reports))


if __name__ == "__main__":
    raise SystemExit(main())

