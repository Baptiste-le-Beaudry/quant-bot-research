"""scripts/strategy_a_equity/run_task_a.py -- Task A 2x2 recalibration
attribution (docs/strategy_a_equity/STRATEGY_A_EQUITY_TASKS_A_E.md).
Runs configs A (fixed070 gate + crypto cost), B (topdecile + crypto cost),
C (fixed070 + equity cost) on the 15 discovery-sample symbols x 2 models.
Config D (topdecile + equity cost, frozen/adopted) is already computed by
run_all_own_asset.py -- not touched or rerun here.

Usage:
    python scripts/strategy_a_equity/run_task_a.py
"""
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

PRIMARY = ["AMD", "PLTR", "UBER", "INTC", "BAC", "FB", "NFLX", "GOOGL",
           "PYPL", "DIS", "JNJ", "PG", "KO", "XOM", "WMT"]
MODELS = ["rf", "logistic"]
CONFIGS = [
    ("A", "fixed070", "crypto"),
    ("B", "topdecile", "crypto"),
    ("C", "fixed070", "equity"),
]
MAX_FOLDS = 40


def main():
    script = os.path.join(REPO_ROOT, "scripts", "strategy_a_equity", "own_asset_walkforward.py")
    total = len(PRIMARY) * len(MODELS) * len(CONFIGS)
    done = 0
    for letter, gate, cost in CONFIGS:
        for symbol in PRIMARY:
            for model in MODELS:
                done += 1
                t0 = time.time()
                print(f"\n{'='*80}\n[{done}/{total}] config{letter} {symbol}/{model} "
                      f"(gate={gate} cost={cost})\n{'='*80}", flush=True)
                result = subprocess.run(
                    [sys.executable, script, "--symbol", symbol, "--model", model,
                     "--gate", gate, "--cost", cost, "--tag", f"_config{letter}",
                     "--max-folds", str(MAX_FOLDS)],
                    cwd=REPO_ROOT, capture_output=False,
                )
                elapsed = time.time() - t0
                status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
                print(f"[{done}/{total}] config{letter} {symbol}/{model}: {status} in {elapsed:.0f}s", flush=True)
    print("\nTASK A ALL CONFIGS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
