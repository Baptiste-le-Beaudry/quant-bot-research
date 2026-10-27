"""scripts/strategy_a_equity/run_task_e.py -- Task E independent
confirmation batch (docs/strategy_a_equity/STRATEGY_A_EQUITY_TASKS_A_E.md).
Runs configuration D (frozen: TRAIN top-decile gate, 0.02% equity cost,
unchanged features/filters/model specs/walk-forward/cost model) on the 16
never-before-used confirmation symbols x 2 models. Zero tuning -- no
--gate/--cost/--filter-mode override, no --tag (these are new symbols,
no collision with the discovery-sample output files).

Usage:
    python scripts/strategy_a_equity/run_task_e.py
"""
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

CONFIRMATION = ["AMZN", "BA", "BABA", "MU", "C", "CRM", "ADBE", "QCOM",
                 "TXN", "AVGO", "CSCO", "V", "MA", "PEP", "MCD", "COST"]
MODELS = ["rf", "logistic"]
MAX_FOLDS = 40


def main():
    script = os.path.join(REPO_ROOT, "scripts", "strategy_a_equity", "own_asset_walkforward.py")
    total = len(CONFIRMATION) * len(MODELS)
    done = 0
    for symbol in CONFIRMATION:
        for model in MODELS:
            done += 1
            t0 = time.time()
            print(f"\n{'='*80}\n[{done}/{total}] TASK E {symbol}/{model}\n{'='*80}", flush=True)
            result = subprocess.run(
                [sys.executable, script, "--symbol", symbol, "--model", model,
                 "--max-folds", str(MAX_FOLDS)],
                cwd=REPO_ROOT, capture_output=False,
            )
            elapsed = time.time() - t0
            status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
            print(f"[{done}/{total}] TASK E {symbol}/{model}: {status} in {elapsed:.0f}s", flush=True)
    print("\nTASK E ALL SYMBOL/MODEL COMBINATIONS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
