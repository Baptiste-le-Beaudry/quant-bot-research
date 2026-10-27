from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant_bot.forward.monitor import write_report
from quant_bot.forward.store import ForwardStateStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="docs/forward_paper/forward_state.sqlite3")
    parser.add_argument("--output", default="docs/forward_paper/status.csv")
    args = parser.parse_args()
    store = ForwardStateStore(args.state)
    try:
        print(write_report(store, args.output).to_string(index=False))
    finally:
        store.close()


if __name__ == "__main__":
    main()
