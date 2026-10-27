#!/bin/bash
# Transfer-mode walk-forward for SOL/AVAX (scripts/multi_crypto_transfer_walkforward.py):
# BTC+ETH-fit model applied out-of-sample per fold to SOL/AVAX's TEST slice. Own-mode walk-
# forward for both was dominated by degenerate 1-3-trade folds (SOL n=34/10 folds, AVAX
# n=16/9 folds) -- this path has a much larger population per fold (sanity-checked: SOL fold 1
# alone gave n=84, PF=1.469), same rationale as the single-split Test A's huge n=5465/6185.
cd "$(dirname "$0")/.." || exit 1

LOCK=/tmp/multi_crypto_orchestrate_solavax_transfer_wf.lock
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "Another SOL/AVAX transfer walk-forward orchestrator instance (PID $(cat "$LOCK")) is already running -- exiting."
  exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

SYMBOLS=(SOLUSDT AVAXUSDT)

for SYM in "${SYMBOLS[@]}"; do
  echo "=== ${SYM}: starting transfer-mode walk-forward (all folds, sequential) ==="
  python -u scripts/multi_crypto_transfer_walkforward.py --symbol "$SYM" --max-folds 20 2>&1
  echo "=== ${SYM}: transfer walk-forward invocation exited ==="
done
echo "=== SOL/AVAX TRANSFER-MODE WALK-FORWARD COMPLETE ==="
