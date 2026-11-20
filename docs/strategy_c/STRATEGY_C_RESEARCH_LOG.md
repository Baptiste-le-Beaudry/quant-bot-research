# STRATEGY C — US Equity Microstructure Research Log
STRATEGY_ID = C

**Takeover note (2026-08-24)**: Strategy C transferred from Gemini to
Claude per explicit user direction. Claude's prior RED TEAM audit
(`docs/SCIENTIFIC_VALIDATION_AUDIT.md`) is COMPLETE; all scientific
discipline developed there carries forward here. Full takeover audit
and feasibility analysis: `docs/strategy_c/STRATEGY_C_FEASIBILITY_REPORT.md`.

**Correction to the entry below** (kept, not deleted, per this
project's standing convention of never silently erasing prior text —
corrected via an explicit note instead): the original "C0 | PASS |
ADOPTED" labeling conflated administrative setup (creating a directory
and a spec document) with a scientific result. No hypothesis was tested
by C0. Relabeled as SETUP, not a PASS/ADOPTED finding.

## Research Registry

| Exp ID | Hypothesis | Date | Result | Decision | Notes |
|---|---|---|---|---|---|
| C0 | N/A — administrative setup only | 2026-08-24 | N/A | SETUP (not a scientific result — corrected 2026-08-24, was previously mislabeled PASS/ADOPTED) | Created `docs/strategy_c/` structure and initial SPEC (by Gemini, reviewed and kept by Claude on takeover). |
| C5 | Data audit: QQQ trades+mbp-1 clean enough to trust for feature work | 2026-08-25 | PASS (1 immaterial holiday artifact) | PASS | 1.36M trades + 411.8M quotes, 0 monotonicity/tz/bad-tick issues. See full entry below. |
| C1 | H_C1: quote/trade-flow imbalance predicts short-horizon continuation on QQQ, surviving costs | 2026-08-25 | quote_imbalance: non-monotonic, weak/inconsistent nulls (z 1.1-2.25). trade_flow_imbalance: robust but WRONG-SIGNED (z -2.5 to -4.7, reversal not continuation), unstable across time-of-day. Exec LONG return negative in every decile/feature/horizon. | **REJECT** | Full result, null baselines (C13), time-of-day (C14) below. Wrong-signed reversal lead documented, NOT pursued this cycle. |
| C2 | H_C2: extreme aggressive order-flow imbalance predicts short-horizon REVERSAL (discovered from C1's wrong sign) — confirmation test on SPY, an independent sample never used for discovery | 2026-08-25 | SHORT side (extreme buying) sign REVERSES vs. QQQ discovery (SPY shows continuation, z=+2.7 to +3.4 vs nulls — real but wrong-signed). LONG side no signal. Exec return negative both sides, all horizons. Time-of-day sign inconsistent. | **REJECT** | Full result below. Strategy C CLOSED for this cycle per explicit user instruction — no C3. |

---

## C0: Initial Setup & Feasibility (Phase C30)
**Status:** COMPLETE (setup only — see the takeover feasibility report for the actual scientific plan)

The goal is to determine the data availability for QQQ microstructure (trades and quotes at sub-second resolution) and the infrastructure required to test the "Order Flow Imbalance" hypothesis.

### Data Audit requirements:
- Timestamps: Exchange vs Receive (Monotonicity check)
- DST-aware (America/New_York)
- Duplicate detection
- Session boundaries (09:30-16:00 ET)
- Crossed/Locked markets check

---

## C5: Data Audit — RESULT (2026-08-25)
**Status:** PASS (one flagged, immaterial anomaly — documented, not silently fixed)

Ran `scripts/strategy_c/data_audit.py` against the real converted QQQ
data (`data/strategy_c/normalized/QQQ_trades_daily/`,
`QQQ_mbp-1_daily/`), Databento EQUS.MINI, 2026-02-24 to 2026-05-22
(inclusive), trades + mbp-1 (top-of-book NBBO).

- **Trades**: 1,360,369 rows, 63 session-days. 0 monotonicity issues, 0
  tz-awareness issues, 0 zero/negative price or size ticks. 97.97% of
  trades fall within the 09:30-16:00 NY regular session on average
  (remainder is expected pre/post-market activity, not a bug).
- **Quotes (mbp-1/NBBO)**: 411,776,859 rows, 64 session-days. 0
  monotonicity issues, 0 tz-awareness issues. Crossed markets (bid >
  ask): 2,802 rows (0.0007% of valid quotes) — a nonzero rate is
  expected during fast markets and these rows are excluded from
  imbalance features by construction (`quote_imbalance`/`spread_pct`
  require `denom > 0` / `bid,ask > 0`, but do NOT separately exclude
  crossed rows yet — flagged as a TODO before trusting any single-tick
  imbalance value at a crossed timestamp, though this affects at most
  0.0007% of quotes and none of the C1 5s-resampled observations were
  manually checked against this specific flag yet). Locked markets (bid
  == ask): 26,950 rows (0.0066%), informational only.
- **Cross-check anomaly**: quotes exist for 64 dates but trades for only
  63 — the extra date is **2026-04-03, which is Good Friday, a US
  equity market holiday** (verified: NYSE/Nasdaq closed). Inspected the
  file directly: it contains exactly **1 row**, a single quote at 11:54
  NY-local time, with zero trades that day. Classified as a stray/
  spurious SIP message on a closed session, not a real trading day.
  **No fix applied and none needed**: `experiment_c1_raw_drift.py`'s
  `compute_daily_obs` only processes `common_dates = trades ∩ quotes`,
  so this date is automatically excluded from all C1 observations
  without any special-casing. Documented here per the mandate's
  "VERIFY BEFORE BELIEVE" discipline rather than silently ignored.

**Overall verdict**: PASS. No monotonicity, timezone, or bad-tick
defects found in either file set. The one cross-check flag is
immaterial (holiday artifact, structurally excluded downstream) and is
recorded rather than fixed to preserve the raw audit trail.

**DST transition check**: 2026-03-08 (spring-forward) fell on a
Sunday — not a trading day, so no in-sample DST transition exists in
this 2026-02-24 to 2026-05-22 window. No DST-transition assertion was
exercised by this dataset; this is a coverage gap to note (not a bug)
if the window is ever extended into November.

---

## Bug fix (2026-08-25): crossed-market quotes not excluded from features

Before running Experiment C1, noticed `quote_imbalance`/`spread_pct` in
`quant_bot/strategy_c/features.py` only guarded against zero/negative
bid or ask, not against a CROSSED quote (bid > ask — 2,802 rows, 0.0007%
of valid quotes, per the C5 audit above). A crossed quote would have
produced a sign-flipped `quote_imbalance` or a negative `spread_pct`
instead of MISSING. Fixed both functions to exclude crossed rows
(`bid <= ask` required), and `experiment_c1_raw_drift.py`'s
`build_observations` now also drops crossed quotes before computing
`mid`/`bid`/`ask` (previously only the derived features would have been
NaN'd, not the raw mid/bid/ask used as the forward-return TARGET price).
Added `TestCrossedMarketExclusion` to `tests/strategy_c/test_causality.py`
(now 6/6 passing). At 0.0007% of quotes this has no material effect on
the results below, but is fixed rather than left in per "VERIFY BEFORE
BELIEVE."

## Performance fix (2026-08-25): null_baselines.py thrashing

First run of `null_baselines.py` (200 draws x 4 null types x 6
feature/horizon combos = 4,800 draws) recomputed `tz_convert` and
`rolling("60s").std()` over the full 294,840-row observation set AND
called `obs.copy()` (~20 columns) inside every single draw. On this
machine (~10GB RAM, ~1-2GB typically free) this thrashed for 35+
minutes with zero progress (CPU time barely advanced, working-set was
being trimmed by the OS). Killed and rewrote: grouping keys
(minute-of-day, volatility quintile) are now computed ONCE, and shuffles
operate on plain 1-D numpy arrays via a vectorized group-preserving
permutation instead of per-draw DataFrame copies. Same null
definitions, same N_DECILES=10/N_DRAWS=200 — a performance fix, not a
methodology change. Completed in 6m27s after the rewrite.

---

## Experiment C1: raw forward drift + C13 null baselines + C14 time-of-day — RESULT (2026-08-25)

**STRATEGY_ID = C. Pre-registered per `STRATEGY_C_FEASIBILITY_REPORT.md`
Sections 11/14/16. Dataset: QQQ, Databento EQUS.MINI trades + mbp-1
(top-of-book NBBO), 2026-02-24 to 2026-05-22 (63 session-days, one
Good-Friday quote-only artifact excluded — see C5 above). Observations:
294,840 rows (5-second resampled, session-only 09:30-16:00 NY,
last-observation-carried-forward capped at 60s staleness). Independent
unit count: 63 session-days (per the mandate's C21 discipline — NOT the
294,840 raw observation count, which is highly autocorrelated
intraday).**

### Raw forward drift (bucketed by feature decile)

**`quote_imbalance`** (bid_sz − ask_sz)/(bid_sz + ask_sz), vs forward
MID return at 30s/60s/5min:
- Bucket pattern is **NOT monotonic** at any horizon — it is U-shaped
  (both extreme deciles show higher mean forward return than the middle
  deciles), not the expected "most-negative-imbalance → negative drift,
  most-positive-imbalance → positive drift" monotonic staircase.
- Top-bottom decile spread: 0.052 bps (30s), 0.051 bps (60s), 0.127 bps
  (5min) — small in absolute terms (sub-basis-point).
- z-scores vs. the 4 pre-registered C13 nulls range **1.1 to 2.25**
  across all horizons/null-types — inconsistent, several below the
  conventional |z|>2 threshold, none robustly above it across all 4
  null types simultaneously.
- C14 time-of-day split: sign flips across session sub-periods (e.g. at
  30s: −0.005 bps at the open, +0.098 bps at the close — no stable
  single-direction relationship across the day).

**Verdict: quote_imbalance does NOT survive the pre-registered "monotonic
or economically coherent across deciles" pass criterion (Section 14).
REJECT for H_C1 as stated.**

**`trade_flow_imbalance`** (aggressive buy − sell volume, 60s trailing
window, normalized), vs forward MID return:
- 30s: no signal (spread 0.003 bps, all 4 null z-scores ≈ 0.1–0.3).
- **60s: spread = −0.089 bps, z = −2.5 to −2.7 across all 4 nulls
  (consistent, statistically robust).**
- **5min: spread = −0.312 bps, z = −3.9 to −4.7 across all 4 nulls
  (consistent, statistically robust, the strongest result in this
  entire experiment).**
- **The sign is OPPOSITE to H_C1's hypothesis.** H_C1 predicted
  aggressive buying pressure → positive forward drift (continuation).
  What is observed is aggressive buying pressure → **negative** forward
  drift (short-term reversal/mean-reversion), and this holds up
  robustly against all 4 independently-designed null baselines — this
  is NOT a fluke, time-of-day artifact, or volatility-regime proxy.
- C14 time-of-day split reveals this aggregate effect is **not uniform
  across the session**: at 5min, 09:30-10:00 shows +0.924 bps (correct
  H_C1 sign!), 10:00-12:00 shows −1.091 bps (opposite, and the largest
  magnitude), 12:00-14:00 ≈ 0, 14:00-15:30 shows +0.375 bps (correct
  sign again), 15:30-16:00 shows −0.790 bps (opposite again). The
  headline aggregate negative result is a mix of a strongly negative
  mid-morning/late-day regime and a positive open/mid-afternoon regime —
  not one single coherent all-day mechanism.

**Verdict: H_C1 (imbalance → continuation) is REJECTED for
trade_flow_imbalance as pre-registered** — the real, robust effect
found is a DIFFERENT phenomenon (reversal, not continuation), and it is
itself unstable across time-of-day sub-periods. Per this project's own
standing discipline (no threshold fishing, no reformulating a
hypothesis to fit an unexpected result within the same
diagnostic/TRAIN cycle — see [[research_methodology_rules]] and
[[feedback_auditor_role_no_new_strategies]]), this reversal pattern is
recorded as an **UNVERIFIED LEAD for a possible future, separately
pre-registered hypothesis** (tentatively "H_C2: short-horizon aggressive-
flow reversal on QQQ, non-uniform across session sub-periods") — it is
NOT adopted, tested for cost-survival, or acted on in this cycle.

### Executable cost check (all deciles, all features, all horizons)

`mean_exec_long_ret_bps` (enter at ask, exit at bid[t+h]) is **negative
in every single decile, for every feature, at every horizon** in the
raw C1 report — ranging roughly −0.12 to −0.67 bps, i.e. spread/
execution cost alone exceeds any raw mid-price edge observed anywhere
in this dataset for a naive LONG rule. This independently confirms
REJECT even before considering the null-baseline/monotonicity failures
above: **no decile of either feature, at any horizon, produces a
positive executable LONG edge.** (SHORT-side executable returns for the
reversal lead were not computed in this cycle since that lead is not
being pursued now — flagged for the future H_C2 pre-registration if
ever taken up.)

### PASS/REJECT — Final decision

**REJECT.** Per the pre-registered Section 14 criteria: `quote_imbalance`
fails the monotonicity/coherence requirement and shows inconsistent
(sub-|z|=2, non-uniform-sign) null-baseline survival;
`trade_flow_imbalance` shows a real, null-surviving effect but of the
**wrong sign** relative to H_C1 and is itself time-of-day-unstable; and
the executable-return check shows no decile/feature/horizon combination
produces a positive LONG edge net of spread. This is outcome **(B)** of
the mandate's two pre-committed acceptable outcomes: *"L'effet apparent
disparaît après spread/exécution/null baselines. Cette hypothèse
Strategy C est rejetée sans gaspiller du temps sur ML, full L2 ou
grosse infrastructure."*

**Not pursued in this cycle, per standing discipline**: walk-forward
validation, SPY generalization, and ML (Sections 24-28 of the mandate)
are all explicitly gated on H_C1 passing raw forward drift — it did
not, so none of these are attempted. The reversal lead
(trade_flow_imbalance, wrong-signed vs. H_C1) is documented above as an
unverified future lead only, matching [[feedback_auditor_role_no_new_strategies]]'s
"document leads, don't act on them unilaterally" rule.

**Artifacts**: `data/strategy_c/experiments/c1_observations.parquet`
(294,840 rows, full feature/return set), `c1_{feature}_{horizon}_buckets.csv`
(6 files), `c14_{feature}_{horizon}_by_subperiod.csv` (6 files) — all
preserved for independent reproduction (per the mandate's Phase 35, if
this result is ever contested).

**C1 remains REJECT. This is not requalified as a success below — C2 is
a genuinely new, separately pre-registered hypothesis discovered FROM
C1's unexpected result, not a rescue of C1.**

---

## C2 — PRE-REGISTRATION (frozen 2026-08-25, BEFORE any confirmation data is inspected)

**DISCOVERY ORIGIN**: Experiment C1's `trade_flow_imbalance` result
(above) — a real, null-surviving, wrong-signed-vs-H_C1 relationship:
extreme aggressive buying → negative forward return; by implication,
extreme aggressive selling → positive forward return. **QQQ 2026-02-24
to 2026-05-22 is hereafter the DISCOVERY SAMPLE and may NEVER be reused
to claim confirmation of C2** — any positive-looking result computed on
those same QQQ observations would be circular (the hypothesis was
mined from that exact data).

**H_C2 (economic hypothesis)**: Extreme one-sided aggressive order flow
represents late/exhausted liquidity demand rather than new directional
information. Extreme aggressive BUYING is followed by a short-term
negative reversal (SHORT profits); extreme aggressive SELLING is
followed by a short-term positive reversal (LONG profits). Tested
separately per side — symmetry is NOT assumed.

**CONFIRMATION DATA**: SPY, same dataset/schemas/window as QQQ discovery
(Databento `EQUS.MINI`, trades + mbp-1, 2026-02-24 to 2026-05-24) —
**a fully independent symbol never inspected for Strategy C before this
point.** Cost confirmed via `metadata.get_cost` (a metadata-only call,
touches no tick-level values, so this pre-registration is written with
zero information leakage from SPY's actual data): trades $0.52 + mbp-1
$19.90 = **$20.42**, cross-validated against the get_cost tool's exact
match to QQQ's already-known real charge ($37.18) — well within the
remaining Databento free credit (~$87.82 of the original $125 after the
QQQ purchase), so no new purchase/subscription is being made. Why this
is a valid independent confirmation set: different underlying index
(S&P 500 vs. Nasdaq-100), different constituent overlap, different
liquidity/volume profile, same venue/consolidated-tape mechanics, same
time window (so no regime-shift-over-time confound) — a genuinely
unseen population for this specific hypothesis.

**FROZEN DEFINITIONS (will NOT change after seeing SPY results)**:
- **Feature**: `trade_flow_imbalance` exactly as defined in
  `quant_bot/strategy_c/features.py` — trailing 60s rolling
  (aggressive-buy-volume − aggressive-sell-volume) / total classified
  volume. No other feature is used as a filter (quote_imbalance/VWAP/
  vol/time-of-day are DESCRIPTIVE diagnostics only, per the mandate's
  explicit instruction not to stack filters to rescue/improve a result).
- **Aggressor classification**: quote test (`classify_aggressor`),
  unchanged from C1 — price ≥ prevailing ask ⇒ BUY, price ≤ prevailing
  bid ⇒ SELL, else AMBIGUOUS/MISSING (never defaulted).
- **Horizons**: 30s, 60s, 5min — the same three pre-registered in C1,
  no new sweep.
- **Threshold method**: **top/bottom DECILE** of `trade_flow_imbalance`,
  computed on the confirmation (SPY) sample's own distribution — the
  same decile-bucketing method already used throughout C1 (not a new
  method chosen after seeing SPY, not a swept percentile — one
  pre-registered method: decile 9 = extreme aggressive buying, decile 0
  = extreme aggressive selling).
- **Direction / rule**: decile 9 (extreme buying) ⇒ enter SHORT;
  decile 0 (extreme selling) ⇒ enter LONG. Reported separately, no
  assumed symmetry.
- **Entry/exit prices**: identical convention to C1's
  `attach_forward_returns` (already-implemented `fwd_exec_long_ret_*`/
  `fwd_exec_short_ret_*` columns) — SHORT: sell at bid[t], buy back at
  ask[t+h]; LONG: buy at ask[t], sell at bid[t+h]. This is
  spread-crossing cost only (no additional latency/slippage buffer
  beyond crossing the touch), identical to C1 for direct comparability
  — not loosened or tightened for C2.
- **Null baselines**: the same 4 pre-registered types reused verbatim
  from `scripts/strategy_c/null_baselines.py` (same-time-of-day,
  same-vol-regime, random-direction, permutation) — no new null
  invented unless one of these proves inapplicable to SPY.
- **Time-of-day check**: same 5 session sub-periods as C14, evaluated
  for SIGN CONSISTENCY (not to pick the best-performing slice).
- **Independent-event accounting**: report raw n, session-day count,
  and flag that adjacent 5s-resampled observations within the same
  imbalance episode are NOT independent (same C21 discipline as C1).

**PASS CRITERIA** (all required — pre-registered verbatim from the
mandate): (1) reversal sign reproduces on SPY confirmation data for the
relevant side(s); (2) relationship survives all 4 null baselines; (3)
executable expectancy > 0 after spread/slippage; (4) PF > 1 after
costs; (5) not driven by a handful of sessions; (6) not purely an
open/close artifact; (7) sufficient independent (session-day) sample;
(8) no post-hoc modification of this frozen concept needed.

**REJECT CRITERIA**: sign disappears or reverses vs. discovery; effect
much weaker out-of-sample; edge < spread; executable expectancy ≤ 0;
PF ≤ 1; result depends on one time-of-day slice only; result depends on
a few days only; null baselines explain the effect. **If REJECT: close
Strategy C for this cycle, no immediate C3.**

**No ML, no L2, no ratchet on quote_imbalance/VWAP/vol/time-of-day as
filters** — simple causal edge → executable edge → independent
confirmation → (only then) walk-forward, exactly per the mandate's
phase ordering.

*Frozen 2026-08-25, before opening any SPY tick data.*

---

## C2 — RESULT (2026-08-25)

**Data acquired**: SPY, Databento `EQUS.MINI`, trades + mbp-1, 2026-02-24
to 2026-05-24, cost $20.42 (within remaining free credit, no new
purchase). Data audit: PASS — 1,952,274 trades + 222,531,170 quotes, 0
monotonicity/tz/bad-tick issues, same immaterial Good-Friday
(2026-04-03) quote-only artifact as QQQ (independently confirms it's a
genuine calendar holiday, not a data bug). One corrupted checkpoint
parquet found and regenerated during the pipeline (a partial write from
a killed background process, not a data-source problem) — flagged and
fixed before trusting results, not silently ignored. Observations:
294,837 rows (5s resampled, session-only), 63 independent session-days.

### Extreme-decile reversal test (frozen rule: decile 9 → SHORT, decile 0 → LONG)

| Horizon | Side | mean signed mid ret (bps) | win rate % | mean exec ret (bps) |
|---|---|---|---|---|
| 30s | SHORT (extreme buying) | **−0.023** | 48.78 | −0.542 |
| 30s | LONG (extreme selling) | 0.014 | 49.93 | −0.542 |
| 60s | SHORT (extreme buying) | **−0.071** | 48.21 | −0.586 |
| 60s | LONG (extreme selling) | −0.007 | 49.32 | −0.562 |
| 5min | SHORT (extreme buying) | **−0.186** | 47.47 | −0.698 |
| 5min | LONG (extreme selling) | 0.013 | 50.76 | −0.539 |

("Signed" return = actual mid return × the sign that would make the
rule's own logic correct — i.e., positive means H_C2 was right.
**Negative means the discovery-sample sign did NOT reproduce.**)

**The SHORT side (extreme aggressive buying) is negative at all three
horizons and gets MORE negative as the horizon lengthens (−0.023 →
−0.071 → −0.186 bps)** — this is the mirror image of what H_C2
predicted. Looking at the raw (unsigned) full-decile table confirms
why: on SPY, **decile 9 (extreme buying) shows a POSITIVE forward mid
return at every horizon** (+0.023 / +0.071 / +0.186 bps) — i.e.
aggressive buying is followed by further upward drift on SPY, the
**opposite of the reversal found on QQQ** (and, ironically, closer to
H_C1's ORIGINAL continuation hypothesis, which was itself already
rejected on QQQ for the unrelated reason of quote_imbalance's
non-monotonicity).

**The LONG side (extreme aggressive selling) shows no reliable
relationship at all** — signed returns are small and inconsistent in
sign across horizons (+0.014, −0.007, +0.013 bps), not a stable
reversal.

### Null baselines (C13-equivalent, SPY)

`trade_flow_imbalance` vs. forward MID return, full (unsigned) top-bottom
decile spread:
- 30s: 0.009 bps, z = 0.4–0.6 across all 4 nulls (no signal).
- **60s: 0.077 bps, z = 2.72–3.00 across all 4 nulls (real, robust).**
- **5min: 0.168 bps, z = 2.72–3.37 across all 4 nulls (real, robust).**

**This independently confirms SPY has a real, null-surviving
trade_flow_imbalance effect at 60s/5min — but it is the OPPOSITE sign
to H_C2's reversal hypothesis.** A statistically real effect of the
wrong sign is not a weaker version of a pass; it is a direct
falsification of the specific directional claim being tested.

### Time-of-day consistency check (C14-equivalent, SPY)

Sign is **not consistent** across session sub-periods at any horizon —
e.g. at 5min: 09:30-10:00 = −0.436 bps, 10:00-12:00 = +0.230 bps,
12:00-14:00 = +0.216 bps, 14:00-15:30 = +0.145 bps, 15:30-16:00 = −0.175
bps. This is a mix of signs across the session, not one coherent
all-day mechanism, on top of already conflicting with the QQQ discovery
sign in aggregate.

### PASS/REJECT — Final decision

**REJECT**, against the pre-registered criteria fixed before this data
was opened:
1. **Sign does NOT reproduce** — it reverses for the SHORT/buying side
   (the stronger, more robust side). REJECT criterion "signe disparaît
   ou inverse" is met directly.
2. **Executable expectancy ≤ 0 for BOTH sides, every horizon**
   (mean_exec_ret_bps ranges −0.54 to −0.70 bps across all six
   side×horizon combinations — never positive anywhere).
3. Time-of-day sign is inconsistent, an independent REJECT signal on
   its own.
4. Sample size is NOT the limiting factor (63 independent session-days,
   ~29-30k observations per decile) — the effect itself is wrong-signed
   and cost-negative, not underpowered.

**Per the user's explicit instruction: Strategy C is now CLOSED for
this cycle. No C3 is opened.** C1 remains REJECT (unchanged, not
requalified). C2 is REJECT — a genuinely new hypothesis, honestly
tested on a truly independent confirmation sample, and honestly
falsified. The frozen concept was NOT modified after seeing SPY data;
no threshold, horizon, or feature was changed to try to rescue it.

**Reusable finding for any future Strategy C work (if the user
reopens this track later)**: `trade_flow_imbalance`'s relationship to
short-horizon forward returns is **sign-unstable across symbols**
(QQQ: reversal: z=-2.5 to -4.7; SPY: continuation: z=+2.7 to +3.4) and
**sign-unstable across time-of-day within the same symbol** (both QQQ's
C14 and SPY's C14 results show mixed signs across session sub-periods).
This pattern — a "significant" null-surviving result that nonetheless
flips sign across symbols and across the day — is itself evidence
AGAINST a single stable causal microstructure mechanism, and more
consistent with sample-specific structure than a generalizable edge.
Any future revival of this feature should treat this cross-symbol sign
instability as the central obstacle to address, not route around it
with a new threshold or filter.

**Artifacts**: `data/strategy_c/experiments/c2_spy_observations.parquet`
(294,837 rows), `c2_spy_sides_{horizon}.csv`,
`c2_spy_full_deciles_{horizon}.csv`, `c2_spy_tod_{horizon}.csv` — all
preserved for independent reproduction.
