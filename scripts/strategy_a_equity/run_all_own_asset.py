"""scripts/strategy_a_equity/run_all_own_asset.py -- batch driver: runs
own_asset_walkforward.py to completion (all folds) for every symbol in
SPEC.md Section 5 (15 primary + 2 secondary) x both models (logistic, rf).
Sequential (RF already uses n_jobs=-1 internally -- running multiple
symbol/model jobs concurrently would oversubscribe cores, not speed
things up). Resumable: own_asset_walkforward.py's own checkpointing means
a rerun of this driver skips already-completed fold work per symbol/model.

Usage:
    python scripts/strategy_a_equity/run_all_own_asset.py
"""
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

PRIMARY = ["AMD", "PLTR", "UBER", "INTC", "BAC", "FB", "NFLX", "GOOGL",
           "PYPL", "DIS", "JNJ", "PG", "KO", "XOM", "WMT"]
SECONDARY = ["TSLA", "NVDA"]
ALL_SYMBOLS = PRIMARY + SECONDARY
MODELS = ["rf", "logistic"]
MAX_FOLDS = 40  # comfortably above any symbol's real fold count (AMD=20)


def main():
    script = os.path.join(REPO_ROOT, "scripts", "strategy_a_equity", "own_asset_walkforward.py")
    total = len(ALL_SYMBOLS) * len(MODELS)
    done = 0
    for symbol in ALL_SYMBOLS:
        for model in MODELS:
            done += 1
            kind = "SECONDARY" if symbol in SECONDARY else "primary"
            t0 = time.time()
            print(f"\n{'='*80}\n[{done}/{total}] {symbol} ({kind}) / {model}\n{'='*80}", flush=True)
            result = subprocess.run(
                [sys.executable, script, "--symbol", symbol, "--model", model,
                 "--max-folds", str(MAX_FOLDS)],
                cwd=REPO_ROOT, capture_output=False,
            )
            elapsed = time.time() - t0
            status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
            print(f"[{done}/{total}] {symbol}/{model}: {status} in {elapsed:.0f}s", flush=True)
    print("\nALL SYMBOL/MODEL COMBINATIONS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
