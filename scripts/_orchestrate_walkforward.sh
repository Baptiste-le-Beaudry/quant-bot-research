#!/bin/bash
# Runs scripts/multi_crypto_walkforward.py to completion (all folds) for each of the six
# Etape-6 screen survivors, ONE AT A TIME (this environment has only ~10GB total RAM and was
# observed with as little as ~2GB free -- each RF-fit-heavy fold can use 1-2GB, so no parallelism
# here, unlike the download/screen orchestrator which was I/O-bound not memory-bound).
# --max-folds is set high enough that one invocation per symbol covers every fold in one
# continuous run (all 8 new symbols have 56.7-63.5mo of pre-HOLDOUT history -> standard BTC/ETH-
# shape 24mo-initial/3mo-test/3mo-step folds -> well under 20 folds each).
cd "$(dirname "$0")/.." || exit 1

LOCK=/tmp/multi_crypto_orchestrate_wf.lock
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "Another walk-forward orchestrator instance (PID $(cat "$LOCK")) is already running -- exiting."
  exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

SYMBOLS=(BNBUSDT XRPUSDT DOGEUSDT ADAUSDT LINKUSDT LTCUSDT)

for SYM in "${SYMBOLS[@]}"; do
  echo "=== ${SYM}: starting walk-forward (all folds, sequential, memory-constrained env) ==="
  python scripts/multi_crypto_walkforward.py --symbol "$SYM" --max-folds 20 2>&1
  echo "=== ${SYM}: walk-forward invocation exited ==="
done
echo "=== ALL SIX SYMBOLS' WALK-FORWARD COMPLETE ==="
