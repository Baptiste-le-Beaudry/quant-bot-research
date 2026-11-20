# Strategy B_ROTATION — Research Log

**STRATEGY_ID = B_ROTATION**

Experiment cards for the cross-sectional rotation sub-family only. See
`docs/strategy_b/rotation/STRATEGY_B_ROTATION_SPEC.md` for the frozen
pre-registration. Never written to from Strategy A's, the
momentum/breakout Strategy B's, or B_FUNDING's logs.

---

## Experiment BR1 — cross-sectional momentum rotation, cheap screen —
IN PROGRESS

**STRATEGY_ID = B_ROTATION**
**Date**: 2026-08-24
**Script**: `scripts/strategy_b/rotation/cheap_screen_brotation1.py`
**Pre-registered BEFORE running** in `STRATEGY_B_ROTATION_SPEC.md`.

**Design**: 9-symbol fixed universe (BTC/ETH/XRP/TRX/LTC/ETC/LINK/ADA/
BNB), daily bars, top-2 by trailing-7-day return, long-only, daily
rebalance, no leverage. K=2/lookback=7 fixed a priori.

**Rejection criterion (fixed before running)**: REJECT if VALIDATION-
period total return is negative, or PF <= 1.

**Results (VALIDATION 2023-09-13 -> 2025-03-28, 563 daily observations)**:

| | Total return | PF | Win rate | MaxDD |
|---|---|---|---|---|
| BR1 top-2 rotation | +22.63% | 1.088 | 52.9% | **-74.58%** |
| Equal-weight all-9 basket (null baseline, added post-hoc) | +178.42% | 1.240 | — | -37.84% |
| BTC solo buy-and-hold (reference) | +226.73% | — | — | -26.26% |

Sanity check: LOGIC AUDIT independent manual recompute of trailing-7-day
return MATCHES the vectorized version. No single-day return exceeds
±22% (BUG CHECK: PASS — the -74.58% drawdown accumulates gradually over
a genuine Dec 2024 -> Mar 2025 losing stretch, not a data glitch or
divide-by-zero artifact).

**The pre-registered binary criterion (`return<0 or PF<=1`) technically
does NOT trigger** (return is positive, PF=1.088>1) — but this is a
material gap in that pre-registration, caught here via VERIFY BEFORE
BELIEVE rather than mechanically accepted: PF=1.088 is barely above 1,
and MaxDD=-74.58% is catastrophic for an unleveraged long-only design.
**Adding the null-baseline comparison (not itself a new hypothesis, a
required control condition) makes the verdict unambiguous**: the
top-2-momentum rotation is STRICTLY DOMINATED by both simpler
alternatives on every metric — far lower return, far worse drawdown,
even worse PF than just equal-weighting the whole 9-symbol basket. The
ranking mechanism (chase the best 7-day performers, concentrate in only
2 of 9 assets) is actively destroying value relative to naive
diversification, not merely under-diversified.

**VERDICT: REJECT**, overriding the narrow binary pass on the strength
of the baseline comparison — consistent with the project's core
directive not to force a positive result by applying a criterion too
literally when it clearly doesn't capture the intent. **Lesson for
future pre-registrations**: a binary PF/return threshold alone is
insufficient for a strategy with meaningful concentration risk — a
null-baseline (equal-weight or buy-and-hold) comparison should be a
standard, pre-registered part of any future cross-sectional design's
rejection criteria, not an ad hoc addition.

Per the mandate's "at most a couple of economically distinct
hypotheses" discipline, testing ONE more genuinely different angle
before closing the family — see Experiment BR2 below: this project's
own consistent pattern (Strategy A's mean-reversion works; every
momentum-continuation variant tested in Strategy B, including this
top-2 rotation, has failed) motivates testing the OPPOSITE selection
rule (bottom-ranked laggards, betting on reversion) rather than a
parameter tweak on the same momentum-continuation idea.

---

## Experiment BR2 — cross-sectional mean-reversion (bottom-2 laggards)
— COMPLETE, REJECT

**STRATEGY_ID = B_ROTATION**
**Date**: 2026-08-24
**Script**: `scripts/strategy_b/rotation/cheap_screen_brotation2_laggard.py`
**Pre-registered BEFORE running** in `STRATEGY_B_ROTATION_SPEC.md`
REVISION 1.

**Design**: identical to BR1 (same universe, lookback=7, K=2, costs)
except selection direction flips — holds the bottom-2 trailing-7-day
performers (laggards) instead of the top-2, betting on cross-sectional
reversion rather than continuation.

**Results (VALIDATION 2023-09-13 -> 2025-03-28, 563 daily observations)**:

| | Total return | PF | Win rate | MaxDD |
|---|---|---|---|---|
| BR2 bottom-2 (laggard) rotation | +84.65% | 1.151 | 54.9% | -51.95% |
| Equal-weight all-9 basket (baseline) | +178.42% | 1.240 | — | -37.84% |
| BR1 top-2 (momentum) rotation, for reference | +22.63% | 1.088 | 52.9% | -74.58% |

**VERDICT: REJECT** — per the REVISED pre-registered criterion (fixed
before this ran), BR2 is dominated by the equal-weight baseline on BOTH
return (+84.65% < +178.42%) AND MaxDD (-51.95% < -37.84%). Notably, the
mean-reversion direction (BR2) is clearly BETTER than the momentum
direction (BR1) on every metric — consistent with this project's
overall pattern that mean-reversion outperforms momentum-continuation
in this market — but still not good enough to beat simply holding the
whole basket. No bugs found; this is a genuine result.

## Family-level conclusion — B_ROTATION: REJECT

Two structurally opposite selection rules tested (top-2 momentum
continuation, bottom-2 mean-reversion), both dominated by the trivial
equal-weight-9-basket null baseline on both return and drawdown. The
core issue is concentration risk: holding only 2 of 9 correlated
crypto assets at a time, rebalanced daily based on recent relative
performance, adds risk (both directions show materially worse MaxDD
than the diversified baseline) without adding compensating return. This
is a genuine, well-supported REJECT of the cross-sectional rotation
family AS DESIGNED (naive top/bottom-K selection, no risk management,
no volatility-adjusted sizing) — it does not rule out a more
risk-managed version of cross-sectional rotation, but per the user's
explicit instruction not to keep iterating to rescue a family that
failed twice, this is closed here.

**This was the last of the three pre-identified major alternative
directions for Phase B** (momentum/breakout B1-B8, funding-rate
BF1-BF2, cross-sectional rotation BR1-BR2), all REJECT. See the overall
Phase B summary in `docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md` for the
consolidated conclusion across all three sub-families.
