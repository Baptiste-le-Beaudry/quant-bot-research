"""Audit and enrich frozen Strategy A-Equity OOS trades for portfolio use."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "outputs" / "strategy_a_equity"
CACHE = ROOT / "docs" / "_full_data_cache_a_equity"
DEST = SRC / "portfolio"
DISCOVERY = ["AMD","PLTR","UBER","INTC","BAC","FB","NFLX","GOOGL","PYPL","DIS","JNJ","PG","KO","XOM","WMT"]
CONFIRMATION = ["AMZN","BA","BABA","MU","C","CRM","ADBE","QCOM","TXN","AVGO","CSCO","V","MA","PEP","MCD","COST"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    report = {"discovery": DISCOVERY, "confirmation": CONFIRMATION,
              "cost_expected": 0.0002, "models": {}}
    for model in ("rf", "logistic"):
        parts, sources = [], []
        for universe, symbols in (("discovery", DISCOVERY), ("confirmation", CONFIRMATION)):
            for symbol in symbols:
                path = SRC / f"own_asset_{symbol}_{model}_trades.csv"
                cache_path = CACHE / f"{symbol}_full.pkl"
                trades = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])
                bars = pd.read_pickle(cache_path).sort_index()
                bars.index = pd.to_datetime(bars.index, utc=True)
                safe_end = bars.index[int(len(bars) * 0.8)]
                if not (trades.exit_time < safe_end).all():
                    raise RuntimeError(f"HOLDOUT violation: {symbol}/{model}")
                prices = bars.close.reindex(pd.DatetimeIndex(trades.entry_time))
                if prices.isna().any():
                    raise RuntimeError(f"missing entry prices: {symbol}/{model}")
                trades["entry_price"] = prices.to_numpy()
                trades["universe"] = universe
                parts.append(trades)
                sources.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path),
                                "rows": len(trades), "safe_end": str(safe_end),
                                "max_exit": str(trades.exit_time.max())})
        data = pd.concat(parts, ignore_index=True).sort_values(
            ["entry_time", "symbol", "fold", "exit_time"], kind="mergesort")
        identities = ["symbol", "fold", "entry_time", "exit_time"]
        costs = (data.raw_return - data.exec_return).round(12)
        overlap = 0
        for _, group in data.groupby("symbol"):
            end = pd.Timestamp.min.tz_localize("UTC")
            for row in group.sort_values("entry_time").itertuples():
                overlap += int(row.entry_time < end)
                end = max(end, row.exit_time)
        same_minute = int(data.duplicated("entry_time", keep=False).sum())
        audit = {"rows": len(data), "duplicate_identities": int(data.duplicated(identities).sum()),
                 "exit_before_entry": int((data.exit_time < data.entry_time).sum()),
                 "same_symbol_overlap_candidates": overlap,
                 "rows_in_same_minute_collision_groups": same_minute,
                 "cost_values": sorted(costs.unique().tolist()), "sources": sources}
        if audit["duplicate_identities"] or audit["exit_before_entry"] or audit["cost_values"] != [0.0002]:
            raise RuntimeError(f"fatal artifact audit: {model}: {audit}")
        out = DEST / f"audited_candidates_{model}.pkl"
        data.to_pickle(out)
        audit["enriched_sha256"] = sha(out)
        report["models"][model] = audit
    path = DEST / "takeover_audit.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({m: {k:v for k,v in a.items() if k != "sources"}
                      for m,a in report["models"].items()}, indent=2))


if __name__ == "__main__":
    main()
