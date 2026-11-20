# Strategy B_FUNDING — Pre-Registration Spec

**STRATEGY_ID = B_FUNDING**

A structurally distinct sub-family of Strategy B, kept separate from the
momentum/breakout family (B1-B8, all REJECT — see
`docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md`) at every level: own spec
file, own research log, own scripts directory
(`scripts/strategy_b/funding/`), own data directory convention. Never
confused with Strategy A (mean-reversion price/volume) or the rejected
Strategy B momentum/breakout family. User-directed 2026-08-24.

## DATA AUDIT (completed BEFORE any strategy logic, per mandate)

**Script**: `scripts/strategy_b/funding/data_audit_funding.py`.
**Data**: Binance USDT-M Futures funding rate history, BTCUSDT/ETHUSDT,
via `/fapi/v1/fundingRate` (free, no auth), downloaded through
`quant_bot/data/download_funding_oi.py`.

### Binance convention (documented precisely, per mandate)

- Each row's `fundingTime` is the moment the funding payment is
  **settled/exchanged** between longs and shorts — a historical,
  already-realized value, never a forward-looking prediction. The
  `fundingRate` value for a given `fundingTime` is fully known and fixed
  at that exact instant.
- This project's own price bars are indexed by Binance kline **open
  time** (verified via `quant_bot/data/download_klines.py`'s
  `RAW_COLUMNS` ordering — first field is kline openTime). A price bar
  timestamped `T` covers `[T, T+1min)`; its own close price (used for
  every entry/exit throughout this project) is only actually finalized
  at `T+1min` — every existing feature/signal in this codebase already
  treats bar `T`'s close as "known at `T`," a one-minute-conservative
  simplification used consistently project-wide.
- **Consequence for the funding merge**: attaching funding event
  (`fundingTime=T_f`) to price bar `T` via
  `merge_asof(direction='backward', allow_exact_matches=True)` on `T` is
  safe even when `T == T_f` exactly, because funding is settled/known at
  `T_f`, while the price bar's own decision point (its close) is only
  actually available at `T+1min >= T_f` — at least as conservative as
  every other feature in this codebase, not a looser assumption.
- Funding settles every 8h for BTCUSDT/ETHUSDT (00:00/08:00/16:00 UTC)
  — confirmed empirically below, not merely assumed.

### BUG FOUND AND FIXED (2026-08-24) — two independent data-integrity
bugs in `quant_bot/data/download_funding_oi.py`, found by this audit
before any strategy logic was built on top of the data

1. **Pagination skip bug**: `download_funding_history`'s loop advanced
   `current = data[-1]["fundingTime"] + FUNDING_INTERVAL_MS` (a fixed
   +8h) after each page. Verified directly against the live API
   (querying narrow windows around observed gaps) that this silently
   skipped real settlement events whenever the pagination boundary
   didn't line up exactly with the assumed 8h grid — e.g., the
   2025-01-04 08:00:00 UTC BTCUSDT settlement (rate +0.0001) existed on
   the API but was absent from the bulk-downloaded file. **Fix**:
   advance by `+1` millisecond instead of a fixed interval — always
   correct regardless of the true interval structure for any period.
2. **Value-based deduplication bug** (more severe): after fetching,
   `.set_index("timestamp")[["fundingRate"]].sort_index().drop_duplicates()`
   — with only `fundingRate` left as a column, plain `.drop_duplicates()`
   dedupes by **value**, not by timestamp (pandas ignores the index by
   default). Any two genuinely distinct settlement events that happened
   to share the same rate (very common near zero) were being collapsed
   into one. Verified directly: a corrected raw fetch returned 7619
   distinct BTCUSDT timestamps, all of which collapsed to only 4512
   unique VALUES under the old `.drop_duplicates()` call — silently
   destroying **~41% of real historical events**. **Fix**: dedupe on the
   index (`df[~df.index.duplicated()]`), which only removes true
   re-fetched duplicates from overlapping pagination windows.

**Before fix**: BTCUSDT 4506 rows, only 80.2% of intervals exactly 8h,
10.8% showing a "16h gap" (1 missing settlement), long tail up to 672h
gaps. **After fix**: BTCUSDT 7621 rows, ETHUSDT 7387 rows, **100.0% of
intervals exactly 8h, zero gaps**, for both symbols. Files:
`data/BTCUSDT_funding_20190712_20260824.csv`,
`data/ETHUSDT_funding_20190712_20260824.csv`.

**Scope note**: this bugfix was applied to shared infrastructure
(`quant_bot/data/download_funding_oi.py`, not Codex-owned, not
Strategy-A-specific) because it's a genuine data-integrity defect
affecting anyone who uses this downloader. The historical
`docs/step27_funding_feature.md`-era experiment (Strategy A, frozen,
already-concluded) used the OLD gapped file and is left untouched as
historical record, per this project's standing rule of never silently
rewriting old conclusions — noted here for transparency, not corrected
retroactively, since it predates this mandate and Strategy A stays
frozen regardless.

### DATA AUDIT checkpoint

```
STATUS: FAIL (initial) -> FIXED -> PASS (after re-download)
EXPECTED: ~3 settlements/day, consistent 8h cadence, full coverage back
          to project's data_start, no duplicates/NaN/inf.
OBSERVED (before fix): 4506/4459 rows (BTC/ETH), only 80.2% exact-8h
          intervals, systematic n x 8h gaps up to 672h.
OBSERVED (after fix): 7621/7387 rows, 100.0% exact-8h intervals, zero
          gaps, zero duplicate timestamps, zero NaN/inf, coverage
          2019-09-10/2019-11-27 -> 2026-08-24 (covers SAFE_END).
BUG CHECK: 2 bugs found (pagination skip, value-based dedup) -- FIXED
          in quant_bot/data/download_funding_oi.py, re-downloaded, PASS
          verified via scripts/strategy_b/funding/data_audit_funding.py.
DATA CHECK: PASS after fix.
LOGIC CHECK: N/A at this stage (data-only).
REPRODUCIBILITY: PASS -- re-running the audit script reproduces the
          same PASS result deterministically.
NEXT ACTION: proceed to LOGIC AUDIT (causal merge implementation +
          automated tests).
```

## Economic hypothesis (B_FUNDING #1 — funding-extreme mean-reversion)

Funding rate reflects the cost longs pay shorts (or vice versa) to hold
perpetual futures positions, which tracks how "crowded" one side of the
market is. When funding is extremely positive, the market is crowded
long (everyone paying up to stay long) — a classic setup preceding a
short-term corrective pullback as over-extended longs get squeezed or
take profit. Symmetrically, extremely negative funding reflects a
crowded short market, historically preceding short-covering rallies.
This is a **different market mechanism** from both Strategy A
(price/volume mean-reversion) and the rejected Strategy B momentum
family (price-breakout continuation) — it's driven by derivatives-market
positioning, not spot price action directly.

## Entry conditions (simplest possible version, both legs, no ML)

Uses the corrected funding-rate files. For each REAL observed funding
event (not a synthetic grid — matches the event's actual `fundingTime`):
- Compute **TRAIN-only** extreme thresholds: `funding_p90_train` and
  `funding_p10_train` — the 90th/10th percentile of `fundingRate` over
  the TRAIN period's own funding events only (causal, fixed before
  looking at VALIDATION).
- At the entry bar (first price bar with `timestamp >= fundingTime`,
  found via search on the already-existing 1-minute price index — see
  Logic Audit for the exact lookup and its own leakage check):
  - if `fundingRate > funding_p90_train`: **SHORT** entry (crowded-long
    correction hypothesis).
  - if `fundingRate < funding_p10_train`: **LONG** entry (crowded-short
    rebound hypothesis).
  - otherwise: no entry.
- This is event-driven (at most 3 opportunities/day per symbol, one per
  real settlement), not a continuously-re-checked condition — a cleaner,
  more economically legible test of "does a fresh extreme funding print
  predict reversal" than a condition that could stay true for hours.

## Exit, risk, walk-forward, stress, HOLDOUT policy

Reused as shared infrastructure, identical discipline to the rest of
Strategy B: TRAIN-derived trailing stop (protective stop = TRAIN
`|MAE|` p90, activate at TRAIN median positive MFE, trail = stop*0.5),
same dynamic leverage formula (`min(0.75*0.5/stop_distance, 30x)`), same
expanding-TRAIN walk-forward fold construction
(`scripts/walk_forward_engine.py`'s `build_folds`), same stress battery
(`scripts/multi_crypto_walkforward.py`'s `SCENARIOS`), HOLDOUT completely
locked (never loaded, scored, or tuned against). For SHORT trades, the
trade path is the NEGATED long-side path (`-(close/entry-1)`) so that
"favorable movement" consistently means positive in the resolved path —
implemented as a thin wrapper around the existing
`build_trades_with_mae_mfe_fast`, not a modification to it.

## Validation metrics

Same conventions as every prior experiment (n_trades, PF, expectancy,
win rate, MaxDD, walk-forward median PF/%folds PF>1, Monte Carlo,
forced liquidations, stress degradation) **PLUS**, specific to this
mandate's explicit requirement: `Corr(PnL_A, PnL_B_FUNDING)` (daily and
weekly), and B_FUNDING's performance specifically during Strategy A's
historical drawdown periods.

## Rejection criteria (fixed BEFORE looking at any result)

- **Cheap screen (BTC+ETH, frozen, no tuning)**: if aggregate PF <= 1.0
  on BOTH BTC and ETH with a reasonable combined sample (n>=30), REJECT
  the initial design — no grid search to rescue it. Given the
  event-driven design naturally produces fewer trades than the
  breakout family (at most 3 opportunities/day vs. continuous), the
  n>=30 floor may take longer to clear across the VALIDATION window;
  if VALIDATION alone doesn't clear it, this is INSUFFICIENT SAMPLE, not
  a verdict either way.
- **Walk-forward**: reject if median PF <= 1, or the result depends on a
  single dominant fold.
- **Forced liquidations**: any forced liquidation under the registered
  dynamic-leverage sizing is disqualifying.
- **Stress test**: must not collapse catastrophically under the standard
  combined-worst-case scenario.
- **Correlation gate**: even a walk-forward-confirmed edge is only
  interesting for portfolio purposes if it shows low PnL correlation
  with Strategy A — a profitable-but-highly-A-correlated result is
  documented honestly as "real edge, low diversification value," not
  silently reframed as a portfolio win.

If this simplest version REJECTs clearly on both BTC and ETH: per the
user's explicit instruction, do a small number (not dozens) of
economically distinct, pre-registered follow-ups at most, and if the
whole funding-rate family shows no robust edge, REJECT the family
cleanly and move automatically to the next major direction
(cross-sectional rotation) without asking.

---

## REVISION 1 (2026-08-24) — BF2: persistent funding regime

Experiment BF1 (single-point-extreme funding, both legs) REJECTED
cleanly on both BTC and ETH (PF 0.801/0.693, n=213, 0 forced liq — see
`STRATEGY_B_FUNDING_RESEARCH_LOG.md`). Per the user's explicit
instruction, at most a couple of economically distinct follow-ups are
tested before closing the whole family, not a parameter search.

**New economic angle**: a SINGLE extreme funding print could be noise
(one anomalous settlement); a PERSISTENTLY extreme funding regime
(several consecutive extreme settlements) is a stronger, more
economically distinct signal of genuinely crowded positioning. This
reuses the `funding_ma_3` concept from this project's own prior
Strategy-A-era feature work (`scripts/step27_funding_feature.py`,
3-settlement rolling mean of funding rate, ~24h) as shared
infrastructure (a smoothing definition, not alpha), applied here as a
rule-based entry rather than an ML feature.

**Entry**: identical structure to BF1 (event-driven, TRAIN-only
percentile thresholds, SHORT on extreme-high / LONG on extreme-low),
except the value tested against the threshold is `funding.rolling(3)
.mean()` (evaluated causally — rolling window uses only settlements up
to and including the current one) instead of the single-point
`fundingRate`. Same TRAIN-only p10/p90 discipline, computed on the
ROLLING series' own TRAIN-window population (not the raw series').

**Rejection criterion (fixed before running, same standard)**: REJECT
if aggregate PF <= 1.0 on BOTH BTC and ETH with n>=30 combined.

If BF2 also REJECTs: per the user's explicit instruction, REJECT the
entire funding-rate family cleanly and move automatically to
cross-sectional rotation without further funding-rate variants and
without asking.

---

*Pre-registered 2026-08-24, before any B_FUNDING result was looked at.*
*Revision 1: 2026-08-24, after BF1's clean REJECT.*
