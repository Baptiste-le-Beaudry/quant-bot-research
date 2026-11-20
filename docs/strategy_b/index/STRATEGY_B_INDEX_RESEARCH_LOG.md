# Strategy B_INDEX — Research Log

**STRATEGY_ID = B_INDEX**

Experiment cards for the Nasdaq 100 / S&P 500 momentum/breakout
sub-family only. See `docs/strategy_b/index/STRATEGY_B_INDEX_SPEC.md`
for the frozen pre-registration. Never written to from Strategy A's or
any crypto Strategy B sub-family's logs.

---

## Experiment BI1 — Nasdaq 100 MFE/MAE forward-drift diagnostic — IN
PROGRESS

**STRATEGY_ID = B_INDEX**
**Date**: 2026-08-24
**Script**: `scripts/strategy_b/index/diagnostic_bi1_drift.py`
**Pre-registered BEFORE running** in `STRATEGY_B_INDEX_SPEC.md`.

**Design**: entry = `dist_ema200_atr>0` (trend regime) AND
`close>rolling_max(high,60).shift(1)` (breakout) AND
`realized_vol_ratio>1.5` (vol confirmation), excluding bars within 60
bars of a >10min session gap. VALIDATION-split Nasdaq 100. Raw forward
path (no exit rule) measured at 15/30/60min horizons.

**Rejection criterion (fixed before running)**: REJECT immediately if
drift is approximately zero or negative at ALL three horizons — no
walk-forward, no exit engineering.

**Results (Nasdaq 100 VALIDATION, 837,517 bars, 2021-09-23 -> 2024-03-05,
n=3468 usable entries)**:

| Horizon | drift mean | drift median | MFE mean | MAE mean | %positive | %>cost |
|---|---|---|---|---|---|---|
| 15min | -0.0113% | +0.0018% | +0.1348% | -0.1513% | 50.5% | 23.3% |
| 30min | -0.0154% | +0.0002% | +0.1986% | -0.2212% | 50.1% | 28.9% |
| 60min | -0.0124% | +0.0008% | +0.2875% | -0.3158% | 50.1% | 33.2% |

DATA AUDIT: PASS (0 NaN, 0 bad ranges, 0 duplicate timestamps). LOGIC
AUDIT: all 5 inspected signals MATCH on independent breakout-level
recheck. 37,980 gap-contaminated bars correctly excluded before entry
evaluation.

**VERDICT: REJECT.** Mean drift is essentially zero to slightly
negative at all three horizons; median drift is negligible (+0.0002% to
+0.0018%, far below any tradeable margin); MFE and MAE are roughly
symmetric; win rate is ~50% at every horizon (a coin flip, not an edge).
This is the same near-zero-net-drift pattern found in the (also
rejected) crypto breakout family's own diagnostic — the general
"any-time breakout + trend + volatility" concept shows no exploitable
edge on Nasdaq 100 either, at any of the three tested horizons.

Per the pre-registered protocol, no walk-forward or exit-mechanics
engineering was built for this design (correctly avoided per the user's
own sequencing — build the cheap diagnostic first, don't engineer exits
for a signal with no measured drift). Testing one genuinely distinct
follow-up before closing B_INDEX's Nasdaq leg — see Experiment BI2
below: a SESSION-FILTERED opening-range breakout, targeting the
specific "US market open" institutional-flow mechanism the user
identified, rather than a parameter tweak of the any-time version just
rejected.

---

## Experiment BI2 — opening-range breakout (session marker BUG) —
COMPLETE, REJECT but see BI3 for the corrected retest

**STRATEGY_ID = B_INDEX**
**Date**: 2026-08-24
**Script**: `scripts/strategy_b/index/diagnostic_bi2_orb.py`

**Design**: session start = bar after any >10min gap; opening range =
first 30min high/low; entry = first breakout of that range within the
following 2h, trend-gated. One entry per session.

**Results**: 633 sessions detected, 328 ORB entries (51.8%). Drift
~zero to slightly negative at all 3 horizons (15min +0.0004%/30min
-0.0021%/60min -0.0099% mean), ~50% win rate, symmetric MFE/MAE.

**LOGIC AUDIT catch (important)**: the sanity check showed the detected
"session start" for the first 5 signals was consistently ~22:00 UTC —
this is Dukascopy's daily ~112min TECHNICAL closure reopen (22:07-00:00
UTC, documented in Experiment 32), NOT the NY equity market open
(13:30/14:30 UTC depending on DST) the ORB hypothesis was meant to
target. The `find_session_starts` function only detects gaps in the
data (any gap qualifies, and the technical closure is the only
`>10min` gap most days), so it silently tested the wrong session
marker. **This is a genuine design bug caught by the mandated sanity
check, not a rescue attempt** — before this result can be trusted as a
test of the ORB/NY-open hypothesis, it needs to be re-run against the
actual NY open. See Experiment BI3.

---

## Experiment BI3 — opening-range breakout, CORRECTED (NY-open-anchored,
DST-aware) — COMPLETE, REJECT

**STRATEGY_ID = B_INDEX**
**Date**: 2026-08-24
**Script**: `scripts/strategy_b/index/diagnostic_bi3_orb_nyopen.py`

**Design**: identical to BI2 except session start is now the first bar
at/after 09:30 America/New_York LOCAL time each day (via
`tz_convert`, correctly DST-aware — verified in the sanity check that
weekday sessions land on 09:30 EDT/EST as intended).

**Results**: 759 sessions detected, 417 ORB entries (54.9%). Drift
still ~zero to negative at all 3 horizons (15min -0.0088%/30min
-0.0314%/60min -0.0188% mean), win rate 51.3-52.5% (still
statistically a coin flip), symmetric MFE/MAE (~0.14-0.27% each side).

**Known limitation (documented honestly, not silently absorbed)**: the
sanity check also revealed that a subset of the 759 detected "sessions"
are weekend/gap-boundary artifacts (e.g., a Sunday evening session open
at 18:00 EDT, correctly the first bar >= 09:30 for that NY calendar
date but not a genuine "NY equity market open" event) — the
`find_ny_open_session_starts` logic picks the first available bar on or
after 09:30 per calendar day, which is contaminated by non-trading-day
edge cases. This dilutes the sample with some non-representative
sessions rather than pure 09:30-anchored opens. **This was not fixed
with a further iteration** because the result is decisively flat (not a
borderline case where session purity would plausibly change the
conclusion) — mean/median drift near zero, MFE/MAE symmetric, win rate
at chance level, consistent across all 3 horizons and consistent with
both BI1's and BI2's independent tests. A future, more precise version
would filter session starts to within a few minutes of exactly 09:30,
but this is not expected to change the qualitative conclusion.

**VERDICT: REJECT.** Three independently-designed Nasdaq 100 tests
(BI1 any-time breakout, BI2 mis-specified-session ORB, BI3
correctly-NY-open-anchored ORB) all show the same near-zero-drift,
~50%-win-rate pattern. No walk-forward was built for any of them
(correctly avoided per the pre-registered protocol — the diagnostic
gate exists precisely to prevent wasted exit-mechanics engineering on a
dead signal).

## Nasdaq leg conclusion — B_INDEX: REJECT (S&P 500 not tested)

Per `STRATEGY_B_INDEX_SPEC.md`'s explicit interaction rule: S&P 500
testing was conditioned on a Nasdaq-CONFIRMED edge (an independent
generalization test of a frozen, already-working rule) — since neither
Nasdaq hypothesis (any-time breakout, NY-open ORB) showed any drift,
testing the same rejected rules on S&P 500 would not be informative
either way and was correctly skipped, per the user's own stated
sequencing. This closes B_INDEX for this cycle: the specific
breakout/trend-continuation concept tested does not show an exploitable
edge on Nasdaq 100 at 15/30/60-minute horizons, whether triggered at any
time or specifically anchored to the NY market open.
