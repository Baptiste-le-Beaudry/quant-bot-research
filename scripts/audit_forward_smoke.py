"""Read-only safety and idempotence audit for the forward-paper state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant_bot.config import RISK_PROFILES
from quant_bot.forward.signal_engine import load_bundle
from quant_bot.forward.store import ForwardStateStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("docs/forward_paper/forward_state.sqlite3"))
    parser.add_argument("--bundle", type=Path, default=Path("docs/forward_paper/strategy_a_bundle.pkl"))
    parser.add_argument("--out", type=Path, default=Path("docs/forward_paper/smoke_audit.json"))
    args = parser.parse_args()
    bundle = load_bundle(args.bundle)
    store = ForwardStateStore(args.state)
    try:
        c = store.connection
        tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        counts = {table: c.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
        duplicate_checks = {}
        keys = {
            "bars": "symbol,open_time", "signals": "signal_id",
            "signal_decisions": "profile,signal_id", "positions": "profile,symbol",
            "expected_positions": "profile,symbol", "executions": "profile,signal_id",
            "funding_events": "symbol,funding_time", "account_snapshots": "profile,timestamp",
        }
        for table, columns in keys.items():
            if table in tables:
                duplicate_checks[table] = c.execute(
                    f'SELECT COUNT(*) FROM (SELECT {columns},COUNT(*) n FROM "{table}" '
                    f'GROUP BY {columns} HAVING n>1)').fetchone()[0]
        events = [dict(row) for row in c.execute("SELECT * FROM data_events ORDER BY id DESC LIMIT 10")]
        result = {
            "bundle": {"strategy_id": bundle.strategy_id, "live_enabled": bundle.live_enabled,
                       "symbols": sorted(bundle.configs), "training_boundary": bundle.training_boundary},
            "normal_profile": RISK_PROFILES["normal"], "table_counts": counts,
            "duplicate_groups": duplicate_checks, "latest_data_events": events,
            "no_duplicates": all(value == 0 for value in duplicate_checks.values()),
            "no_virtual_trades_without_market_data": counts.get("executions", 0) == 0 if counts.get("bars", 0) == 0 else None,
            "paper_safety_pass": bundle.live_enabled is False and all(
                profile["live_enabled"] is False for profile in RISK_PROFILES.values()),
        }
    finally:
        store.close()
    args.out.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
