"""Fail closed if any frozen FIXED9 control artifact changed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "docs/strategy_a/universe_expansion/baseline_snapshot.json"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def verify() -> list[str]:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["sha256"]
    errors = []
    for relative, wanted in expected.items():
        path = ROOT / relative
        observed = digest(path) if path.is_file() else "MISSING"
        if observed != wanted:
            errors.append(f"{relative}: expected {wanted}, observed {observed}")
    return errors


if __name__ == "__main__":
    failures = verify()
    if failures:
        raise SystemExit("CONTROL REGRESSION\n" + "\n".join(failures))
    print("CONTROL PASS: all frozen FIXED9 SHA-256 values match")

