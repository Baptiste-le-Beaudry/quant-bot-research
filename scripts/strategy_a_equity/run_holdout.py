"""Run the preregistered Equity HOLDOUT test sequentially (1 worker, RAM-limited
PC), resumable, then aggregate and write RUN_COMPLETE.txt.

Usage:
    python scripts/strategy_a_equity/run_holdout.py
"""
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.strategy_a_equity.holdout_walkforward import MODELS, OUT_DIR, UNIVERSE

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "strategy_a_equity", "holdout_walkforward.py")


def main():
    failed = []
    for symbol in UNIVERSE:
        for model in MODELS:
            print(f"=== {symbol}/{model} {datetime.now():%Y-%m-%d %H:%M:%S} ===", flush=True)
            rc = subprocess.run([sys.executable, SCRIPT, "--symbol", symbol, "--model", model],
                                cwd=REPO_ROOT).returncode
            if rc != 0:
                print(f"FAILED {symbol}/{model} (exit {rc})", flush=True)
                failed.append(f"{symbol}/{model}")
    if failed:
        print(f"NOT AGGREGATING, failures: {failed} -- rerun to resume", flush=True)
        return 1
    subprocess.run([sys.executable, SCRIPT, "--aggregate"], cwd=REPO_ROOT, check=True)
    with open(os.path.join(OUT_DIR, "RUN_COMPLETE.txt"), "w") as f:
        f.write(f"{datetime.now().isoformat()}\n")
    print("HOLDOUT RUN COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
