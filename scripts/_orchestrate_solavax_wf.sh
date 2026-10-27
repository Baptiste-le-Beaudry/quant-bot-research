#!/bin/bash
# SOL/AVAX extension to the multi-crypto expansion pipeline (Experiment 33): both symbols were
# DEFERRED at the Etape 6 screen stage (Test B own-mode n=7 each, cutoff-percentile-70 follow-up
# only got SOL to n=14) but the user asked to proceed with full walk-forward anyway -- walk-
# forward pools trades across many expanding-window folds, so total n may end up higher than the
# single 80%-of-history screen split did (this is exactly what happened for BNB: screen n=39 ->
# walk-forward n=58). Runs own-mode V3-default walk-forward for both, sequential (same ~10GB RAM
# constraint as the six-symbol run).
cd "$(dirname "$0")/.." || exit 1

LOCK=/tmp/multi_crypto_orchestrate_solavax_wf.lock
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "Another SOL/AVAX walk-forward orchestrator instance (PID $(cat "$LOCK")) is already running -- exiting."
  exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

SYMBOLS=(SOLUSDT AVAXUSDT)

for SYM in "${SYMBOLS[@]}"; do
  echo "=== ${SYM}: starting own-mode walk-forward (all folds, sequential, memory-constrained env) ==="
  python scripts/multi_crypto_walkforward.py --symbol "$SYM" --max-folds 20 2>&1
  echo "=== ${SYM}: walk-forward invocation exited ==="
done
echo "=== SOL/AVAX OWN-MODE WALK-FORWARD COMPLETE ==="
