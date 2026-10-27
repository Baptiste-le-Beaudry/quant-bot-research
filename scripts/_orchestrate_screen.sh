#!/bin/bash
# Waits for each new-crypto symbol's download to finish (final CSV appears, partial/resume gone),
# then immediately runs both screen modes (Test A transfer, Test B own-recalibration) for it,
# before moving to the next symbol. Runs concurrently with scripts/download_multi_crypto.py
# (already running as a separate background process) so screening happens as soon as each
# symbol's data is ready instead of waiting for all 8 downloads to finish first.
cd "$(dirname "$0")/.." || exit 1

# Lock file so an accidental double-launch (e.g. a retry after a process-tree kill that didn't
# cascade to a still-alive child, as happened once on 2026-08-20 and produced THREE concurrent
# orchestrator instances all racing to screen the same symbol) exits immediately instead of
# silently duplicating work / risking a lost-update race on the shared raw-results CSV.
LOCK=/tmp/multi_crypto_orchestrate.lock
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
  echo "Another orchestrator instance (PID $(cat "$LOCK")) is already running -- exiting."
  exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

declare -A FINALS=(
  [SOLUSDT]="data/SOLUSDT_1m_20200914_20260820.csv"
  [BNBUSDT]="data/BNBUSDT_1m_20200210_20260820.csv"
  [XRPUSDT]="data/XRPUSDT_1m_20200106_20260820.csv"
  [DOGEUSDT]="data/DOGEUSDT_1m_20200710_20260820.csv"
  [ADAUSDT]="data/ADAUSDT_1m_20200131_20260820.csv"
  [LINKUSDT]="data/LINKUSDT_1m_20200117_20260820.csv"
  [AVAXUSDT]="data/AVAXUSDT_1m_20200923_20260820.csv"
  [LTCUSDT]="data/LTCUSDT_1m_20200109_20260820.csv"
)
ORDER=(SOLUSDT BNBUSDT XRPUSDT DOGEUSDT ADAUSDT LINKUSDT AVAXUSDT LTCUSDT)

for SYM in "${ORDER[@]}"; do
  FINAL="${FINALS[$SYM]}"
  PARTIAL="${FINAL}.partial.raw.csv"
  echo "=== waiting for ${SYM} download (${FINAL}) ==="
  i=0
  until [ -f "$FINAL" ] && [ ! -f "$PARTIAL" ]; do
    sleep 20
    i=$((i+1))
    if [ $i -ge 600 ]; then
      echo "TIMEOUT waiting for ${SYM} after $((i*20/60)) min -- skipping to next symbol"
      break
    fi
  done
  if [ -f "$FINAL" ] && [ ! -f "$PARTIAL" ]; then
    echo "=== ${SYM} download DONE (${i}x20s checks). Running screen ==="
    if grep -q ",${SYM},own," docs/multi_crypto_screen_raw.csv 2>/dev/null; then
      echo "  [own] already screened, skipping"
    else
      python scripts/multi_crypto_screen.py --symbol "$SYM" --mode own 2>&1
    fi
    if grep -q ",${SYM},transfer," docs/multi_crypto_screen_raw.csv 2>/dev/null; then
      echo "  [transfer] already screened, skipping"
    else
      python scripts/multi_crypto_screen.py --symbol "$SYM" --mode transfer 2>&1
    fi
    echo "=== ${SYM} screen COMPLETE ==="
  fi
done
echo "=== ALL SYMBOLS PROCESSED ==="
