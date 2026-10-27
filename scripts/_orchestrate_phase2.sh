#!/bin/bash
# Phase 2 of the multi-crypto expansion master pipeline: runs AFTER all six survivor symbols'
# walk-forward (scripts/_orchestrate_walkforward.sh) finishes. Etape 8 (stability decision) ->
# Etape 11 (correlation) -> Etape 12 (portfolio build) -> Etape 13 (risk sweep). Each stage
# writes/appends its own checkpoint file, same discipline as every prior stage.
cd "$(dirname "$0")/.." || exit 1

LOCK=/tmp/multi_crypto_orchestrate_phase2.lock
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "Another phase2 orchestrator instance (PID $(cat "$LOCK")) is already running -- exiting."
  exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

SYMBOLS="BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,LINKUSDT,LTCUSDT"

echo "=== PHASE 2: waiting for walk-forward orchestrator to finish all six symbols ==="
i=0
until grep -q "ALL SIX SYMBOLS' WALK-FORWARD COMPLETE" scratchpad_orchestrate_wf.log 2>/dev/null; do
  sleep 60
  i=$((i+1))
  if [ $i -ge 1440 ]; then  # 24h safety cap
    echo "TIMEOUT waiting for walk-forward orchestrator after 24h -- proceeding anyway with whatever completed"
    break
  fi
done
echo "=== PHASE 2: walk-forward orchestrator done (or timeout), proceeding ==="

echo "=== Etape 8: walk-forward stability decision ==="
python scripts/multi_crypto_wf_decide.py --symbols "$SYMBOLS" 2>&1

CONFIRMED=$(cat docs/multi_crypto_wf_confirmed_symbols.txt 2>/dev/null)
if [ -z "$CONFIRMED" ]; then
  echo "=== PHASE 2: no symbols confirmed at walk-forward -- nothing to build a portfolio from, stopping here ==="
  exit 0
fi
echo "=== CONFIRMED symbols for portfolio: ${CONFIRMED} ==="

echo "=== Etape 11: correlation analysis ==="
python scripts/multi_crypto_correlation.py --symbols "$CONFIRMED" 2>&1

echo "=== Etape 12: build combined portfolio ==="
python scripts/multi_crypto_build_portfolio.py --symbols "$CONFIRMED" --out docs/multi_crypto_portfolio_trades.csv 2>&1

echo "=== Etape 13: risk sweep on combined portfolio ==="
python scripts/multi_crypto_risk_sweep.py --data docs/multi_crypto_portfolio_trades.csv --symbols "BTCUSDT,ETHUSDT,${CONFIRMED}" 2>&1

echo "=== PHASE 2 COMPLETE ==="
