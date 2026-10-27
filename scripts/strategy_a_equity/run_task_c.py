"""scripts/strategy_a_equity/run_task_c.py -- Task C filter ablation
(docs/strategy_a_equity/STRATEGY_A_EQUITY_TASKS_A_E.md). Runs conditions
1 (generic dips), 2 (filters only), 3 (model only) on the 15 discovery-
sample symbols x 2 models, using configuration D's frozen gate/cost.
Condition 4 (model+filters = D) is already computed -- not rerun.

Usage:
    python scripts/strategy_a_equity/run_task_c.py
"""
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

PRIMARY = ["AMD", "PLTR", "UBER", "INTC", "BAC", "FB", "NFLX", "GOOGL",
           "PYPL", "DIS", "JNJ", "PG", "KO", "XOM", "WMT"]
MODELS = ["rf", "logistic"]
CONDITIONS = [
    ("1generic", "generic"),
    ("2filtersonly", "filters_only"),
    ("3modelonly", "model_only"),
]
MAX_FOLDS = 40


def main():
    script = os.path.join(REPO_ROOT, "scripts", "strategy_a_equity", "own_asset_walkforward.py")
    total = len(PRIMARY) * len(MODELS) * len(CONDITIONS)
    done = 0
    for tag_suffix, filter_mode in CONDITIONS:
        for symbol in PRIMARY:
            for model in MODELS:
                done += 1
                t0 = time.time()
                print(f"\n{'='*80}\n[{done}/{total}] {tag_suffix} {symbol}/{model} "
                      f"(filter_mode={filter_mode})\n{'='*80}", flush=True)
                result = subprocess.run(
                    [sys.executable, script, "--symbol", symbol, "--model", model,
                     "--filter-mode", filter_mode, "--tag", f"_{tag_suffix}",
                     "--max-folds", str(MAX_FOLDS)],
                    cwd=REPO_ROOT, capture_output=False,
                )
                elapsed = time.time() - t0
                status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
                print(f"[{done}/{total}] {tag_suffix} {symbol}/{model}: {status} in {elapsed:.0f}s", flush=True)
    print("\nTASK C ALL CONDITIONS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
