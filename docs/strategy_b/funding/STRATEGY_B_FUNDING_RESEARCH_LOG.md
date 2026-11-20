# Strategy B_FUNDING — Research Log

**STRATEGY_ID = B_FUNDING**

Experiment cards for the funding-rate sub-family only. See
`docs/strategy_b/funding/STRATEGY_B_FUNDING_SPEC.md` for the frozen
pre-registration this log is validated against, and
`docs/STRATEGY_INDEX.md` for the overall A/B/B_FUNDING separation
convention. Never written to from Strategy A's or the momentum/breakout
Strategy B's logs, and vice versa.

## DATA AUDIT + LOGIC AUDIT — COMPLETE, PASS (2026-08-24)

Full detail in `STRATEGY_B_FUNDING_SPEC.md`. Summary: found and fixed
two real data-integrity bugs in `quant_bot/data/download_funding_oi.py`
(a pagination skip bug and a value-based-instead-of-timestamp-based
deduplication bug) that were silently destroying ~41% of real BTCUSDT
funding settlement events. Re-downloaded corrected data: BTCUSDT 7621
rows, ETHUSDT 7387 rows, both 100.0% exact-8h cadence, zero gaps, zero
duplicates. `scripts/strategy_b/funding/funding_lib.py`'s 4 automated
invariant tests (causal entry-bar timing, independent manual
recomputation, TRAIN-only threshold leakage check, short-trade path
negation correctness) all PASS.

---

## Experiment BF1 — funding-extreme mean-reversion, cheap screen — IN
PROGRESS

**STRATEGY_ID = B_FUNDING**
**Date**: 2026-08-24
**Script**: `scripts/strategy_b/funding/cheap_screen_bfunding1.py`
**Pre-registered BEFORE running** in `STRATEGY_B_FUNDING_SPEC.md`.

**Design**: event-driven (real funding settlements only, ~3/day max per
symbol). TRAIN-only p10/p90 funding-rate thresholds (computed on
TRAIN-window funding events only). SHORT entry when funding > TRAIN p90
(crowded-long correction); LONG entry when funding < TRAIN p10
(crowded-short rebound). Exit mechanics/leverage calibrated SEPARATELY
per direction on that direction's own TRAIN trade population (long and
short are economically distinct setups). No tuning — simplest possible
first pass.

**Rejection criterion (fixed before running)**: REJECT if aggregate
PF <= 1.0 on BOTH BTC and ETH with n>=30 combined.

**Results (VALIDATION split, event-driven, frozen exit mechanics per
direction)**:

| Symbol | n_trades (long/short) | PF | Win rate | Total return | Forced liq |
|---|---|---|---|---|---|
| BTCUSDT | 116 (56/60) | 0.801 | 41.4% | -5.905% | 0 |
| ETHUSDT | 97 (61/36) | 0.693 | 38.1% | -11.35% | 0 |

n_total = 213 (floor 30, satisfied). TRAIN-only thresholds: BTC
p10=-0.000024/p90=0.000364 (from 4557 TRAIN events), ETH
p10=-0.000013/p90=0.000472 (from 4419 TRAIN events) — both computed
strictly on TRAIN-window funding events, never VALIDATION. Sanity check:
all inspected signals show `entry_bar_time >= funding_time` (causal,
no lookahead) with clean, plausible funding-rate values at the flagged
extremes.

**VERDICT: REJECT.** Both symbols PF < 1.0 with adequate sample
(n=213 total, well above the 30 floor), zero forced liquidations, no
bugs found. The simplest single-point-extreme-funding version of the
crowded-long-correction / crowded-short-rebound hypothesis does not
show positive expectancy on BTC or ETH.

Per the user's explicit instruction, this REJECT does not trigger a
parameter search — proceeding to at most a couple of economically
distinct pre-registered follow-ups (not a grid search) before deciding
the family's fate. See Experiment BF2 below.

---

## Experiment BF2 — persistent funding regime (3-settlement rolling
mean) — COMPLETE, REJECT

**STRATEGY_ID = B_FUNDING**
**Date**: 2026-08-24
**Script**: `scripts/strategy_b/funding/cheap_screen_bfunding2_persistent.py`
**Pre-registered BEFORE running** in `STRATEGY_B_FUNDING_SPEC.md`
REVISION 1.

**Design**: identical to BF1 except the value tested against the
TRAIN-only percentile thresholds is `fundingRate.rolling(3).mean()`
(causal, ~24h persistence) instead of the single-point rate — reuses the
`funding_ma_3` concept from this project's own prior Strategy-A-era
feature work (`step27_funding_feature.py`) as shared smoothing
infrastructure, not shared alpha.

**Results (VALIDATION split, event-driven, frozen exit mechanics per
direction)**:

| Symbol | n_trades (long/short) | PF | Win rate | Total return | Forced liq |
|---|---|---|---|---|---|
| BTCUSDT | 121 (55/66) | 0.895 | 43.0% | -2.888% | 0 |
| ETHUSDT | 87 (55/32) | 0.876 | 40.2% | -3.905% | 0 |

n_total = 208 (floor 30, satisfied). Sanity check: all inspected signals
causal (`entry_bar_time >= funding_time`), rolling-3 values consistent
with the underlying raw settlements. BUG CHECK / DATA CHECK / LOGIC
CHECK: PASS.

**VERDICT: REJECT.** Both symbols still PF < 1.0. The persistence
smoothing moved PF closer to breakeven than BF1's single-point version
(BTC 0.801->0.895, ETH 0.693->0.876) but did not cross 1.0 on either
symbol — a real but insufficient improvement, not a rescue.

## Family-level conclusion — B_FUNDING: REJECT

Two economically distinct, pre-registered hypotheses tested
(instantaneous extreme funding, and persistent 24h-averaged extreme
funding), both cleanly REJECT on BTC AND ETH, with adequate combined
samples (213 and 208 trades respectively), zero forced liquidations,
and no bugs found (the DATA AUDIT did find and fix two real
data-integrity bugs in the underlying downloader, but those are now
fixed and verified — the funding data itself is now clean, 100% 8h
cadence, zero gaps, for both symbols). Per the user's explicit
instruction, **the entire funding-rate family is REJECTED here** — no
further funding-rate variants will be tested. This closes B_FUNDING for
this cycle.

**Consistent direction of improvement worth noting for any future
funding-rate work** (not itself grounds to continue testing now): both
the smoothing (BF1->BF2) direction improved results modestly, suggesting
if this family were revisited later, persistence/regime-based framing
is the more promising of the two angles tested — but per the explicit
instruction not to keep iterating to rescue a family that failed twice,
this is recorded as a lead for later, not pursued further this cycle.

Proceeding automatically, per the user's explicit instruction, to the
next major direction: **cross-sectional relative-strength rotation.**
