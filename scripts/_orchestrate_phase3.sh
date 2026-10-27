#!/bin/bash
# Phase 3 of the multi-crypto expansion master pipeline: runs AFTER phase 2 (correlation/
# portfolio/risk-sweep) finishes. Per-symbol optimization pass (threshold/stop-pct/horizon
# sweeps, cheap-screen-then-walk-forward-confirm) for each walk-forward-CONFIRMED symbol,
# processed in order of walk-forward quality (best median PF first) so if the 24h window runs
# out, the most valuable symbols get optimized first.
cd "$(dirname "$0")/.." || exit 1

LOCK=/tmp/multi_crypto_orchestrate_phase3.lock
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "Another phase3 orchestrator instance (PID $(cat "$LOCK")) is already running -- exiting."
  exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

echo "=== PHASE 3: waiting for phase2 orchestrator to finish ==="
i=0
until grep -q "PHASE 2 COMPLETE" scratchpad_orchestrate_phase2.log 2>/dev/null; do
  sleep 60
  i=$((i+1))
  if [ $i -ge 1440 ]; then
    echo "TIMEOUT waiting for phase2 after 24h -- proceeding anyway"
    break
  fi
done
echo "=== PHASE 3: phase2 done (or timeout), proceeding ==="

if [ ! -f docs/multi_crypto_wf_decision.csv ]; then
  echo "=== PHASE 3: no walk-forward decision file -- nothing to optimize, stopping ==="
  exit 0
fi

# Order confirmed symbols by walk-forward median_pf descending (best first).
ORDERED=$(python -c "
import pandas as pd
df = pd.read_csv('docs/multi_crypto_wf_decision.csv')
df = df[df['verdict'] == 'CONFIRMED'].sort_values('median_pf', ascending=False)
print(','.join(df['symbol'].tolist()))
")
echo "=== PHASE 3: optimization order (best walk-forward PF first): ${ORDERED} ==="

IFS=',' read -ra SYMS <<< "$ORDERED"
for SYM in "${SYMS[@]}"; do
  [ -z "$SYM" ] && continue
  echo "=== PHASE 3: optimizing ${SYM} ==="
  python scripts/multi_crypto_optimize_symbol.py --symbol "$SYM" 2>&1
  echo "=== PHASE 3: ${SYM} optimization pass done ==="
done

echo "=== PHASE 3 COMPLETE -- ALL CONFIRMED SYMBOLS OPTIMIZED ==="
