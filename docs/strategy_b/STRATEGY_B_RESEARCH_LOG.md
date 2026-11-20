# Strategy B — Research Log

**STRATEGY_ID = B**

Experiment cards for Strategy B only. See `docs/STRATEGY_INDEX.md` for the
A/B separation convention and `docs/strategy_b/STRATEGY_B_SPEC.md` for the
frozen pre-registration this log is validated against. Strategy A's log is
`docs/research_plan_status.md` and is never written to from here.

## OVERALL PHASE B CONCLUSION (2026-08-24) — all three sub-families
REJECT

This log covers the momentum/breakout sub-family only (B1-B8). Two
further sub-families were pre-registered and tested under their own
dedicated STRATEGY_IDs, each with their own spec/log/scripts directory,
per the user's explicit separation requirement:
- **B_FUNDING** (funding-rate crowded-long/short mean-reversion):
  `docs/strategy_b/funding/STRATEGY_B_FUNDING_RESEARCH_LOG.md`. Found
  and fixed 2 real data-integrity bugs in the funding downloader (~41%
  of BTCUSDT funding history was being silently dropped) before testing
  2 economically distinct hypotheses (instantaneous extreme, persistent
  24h-averaged extreme) — both REJECT (PF 0.801/0.693 and 0.895/0.876
  on BTC/ETH).
- **B_ROTATION** (cross-sectional momentum/mean-reversion across a
  9-symbol basket): `docs/strategy_b/rotation/
  STRATEGY_B_ROTATION_RESEARCH_LOG.md`. Tested both selection directions
  (top-2 momentum, bottom-2 laggard) — both REJECT, dominated by a
  trivial equal-weight-basket null baseline on both return and MaxDD.

**Across all three sub-families (momentum/breakout: 4 variants;
funding: 2 variants; rotation: 2 variants — 8 independently
pre-registered hypotheses total), none survived initial testing on
BTC/ETH (or the 9-symbol basket for rotation).** Every REJECT was
clean: adequate sample size, zero forced liquidations, no unresolved
bugs, and in most cases a mechanistic or comparative explanation for
WHY the hypothesis failed (near-zero net drift after breakout;
funding-extreme reversion too weak after realistic costs; cross-
sectional selection actively destroying value vs. naive diversification
via concentration risk). Per the user's explicit instruction throughout
("ne cherche pas à produire un résultat positif à tout prix"), no result
was forced, rescued via parameter search, or reframed to look better
than it is.

**Honest overall conclusion**: no structurally distinct alpha source
complementing Strategy A has been found in this cycle. This is reported
as the correct, well-earned answer — a thorough, well-documented
negative result across three genuinely different economic hypotheses is
more valuable than a fragile, over-searched "edge" that wouldn't survive
out-of-sample. Two genuine leads remain for a FUTURE cycle if the user
wants to continue this direction: (1) B_FUNDING's persistence-smoothing
direction improved results in both symbols without crossing 1.0 — worth
a more patient revisit; (2) a risk-managed (volatility-scaled sizing,
wider K, or long/short market-neutral) version of cross-sectional
rotation was not attempted, since the naive version's failure was
clearly concentration-risk-driven, not necessarily proof the underlying
relative-strength signal has zero information content.

---

## Interim status (2026-08-23)

The initial momentum/breakout economic hypothesis (STRATEGY_B_SPEC.md
Section 1) has been tested via 4 independently-designed variants, all
REJECT:

| Exp | Concept | Timeframe | BTC PF | ETH PF | n_total | Verdict |
|---|---|---|---|---|---|---|
| B1 | naive breakout+vol+volume | 1min | 0.540 | 0.736 | 1196 | REJECT |
| B4 | + trend-regime gate (hurst>0.5) | 1min | 0.576 | 0.791 | 1016 | REJECT |
| B6 | B5 concept, real walk-forward | 15min | med.0.940 | med.1.237* | 212 | REJECT (2 grounds) |
| B7 | + volatility-squeeze pre-filter | 1min | 0.601 | 0.968 | 300 | REJECT |

*ETH's B6 walk-forward PF is a single-fold artifact — see B6 card.

A dedicated diagnostic (B4 follow-up) established the MECHANISM: raw
MFE/MAE on breakout entries is roughly symmetric and the raw
(exit-rule-independent) path return at trade end is ~zero — there is no
sustained net directional drift after these breakout triggers on BTC/ETH
1-minute (or 15-minute) data, regardless of trend-regime gating or
pre-breakout volatility compression. This is a dead-signal finding, not
an implementation bug or an exit-design artifact.

**Conclusion so far**: the specific "breakout + confirmation filter"
family of momentum entries, as operationalized here, does not survive
initial testing on BTC/ETH. Per the mandate's explicit instruction not to
force a positive result, this family is closed pending a genuinely
different Strategy B economic hypothesis (see "Ranked next Strategy B
directions" below — order-flow imbalance, funding-rate mean-reversion,
and cross-sectional rotation remain untested and require new
data/infrastructure, so were not launched this cycle after 4 converging
negative results).

---

## Experiment B1-B3 — naive breakout+vol+volume cheap screen — REJECT

**STRATEGY_ID = B**
**Date**: 2026-08-23
**Script**: `scripts/strategy_b/cheap_screen.py`
**Output**: `docs/strategy_b/strategy_b_cheap_screen_btc_eth.csv`

**Design (frozen, pre-registered in STRATEGY_B_SPEC.md Section 4, no tuning)**:
entry = `close > rolling_max(high, 60).shift(1)` (breakout) AND
`realized_vol_ratio > 1.5` (vol expansion) AND `rel_volume_20 > 1.5`
(volume confirmation). Exit = trailing stop, TRAIN-derived
stop-distance/activate/trail constants (own population, not copied from
Strategy A). TRAIN/VALIDATION split via `scripts/phase3_baseline.load_split`.

**B2 manual sanity check**: 3 real signals per symbol manually inspected;
independent recomputation of the breakout level (`max(high[i-60:i])`)
matched the vectorized `breakout_level` in all 6 cases (MATCH). No
lookahead bug found. Signal examples economically sensible (small breakout
margins 0.04-0.5%, elevated vol_ratio 1.5-2.0, volume_ratio up to 12x).

**B3 cheap screen results (VALIDATION split, BTC/ETH, frozen rule)**:

| Symbol | n_trades | PF | Win rate | Forced liq | Stop dist | Leverage |
|---|---|---|---|---|---|---|
| BTCUSDT | 655 | 0.540 | 35.0% | 0 | 1.327% | 28.26x |
| ETHUSDT | 541 | 0.736 | 37.2% | 0 | 1.453% | 25.80x |

n_total = 1196 (floor = 30, satisfied by a wide margin).

**Verification (VERIFY BEFORE BELIEVE)**: BUG CHECK PASS, DATA CHECK PASS,
LOGIC CHECK PASS, REPRODUCIBILITY PASS (deterministic rule, no
randomness). Result is a clean, unsurprising negative — matches one of
the pre-registered expected failure modes (Section 7: "breakouts in
crypto may simply be false signals more often than not"), so no
suspicion of a spectacular/anomalous result requiring extra scrutiny.

**Pre-registered rejection criterion (STRATEGY_B_SPEC.md Section 9)**:
REJECT if aggregate PF <= 1.0 on BOTH BTC and ETH with n>=30 combined.
Both symbols PF <= 1.0, n_total=1196 >> 30.

**VERDICT: REJECT.** The naive breakout+vol-expansion+volume-confirmation
design, as specified, does not show positive expectancy on either BTC or
ETH. Per the mandate's explicit instruction, no parameter grid-search was
run to try to rescue this result. This closes the B1 hypothesis as
originally specified.

**Interpretation note**: the pre-registration's own Section 2 (regime
targeted) hypothesized Strategy B needs a genuinely *trending* regime
(high `hurst_120`), but B1's entry rule never actually gated on trend
regime — it only required a breakout + vol/volume expansion, which can
fire inside a choppy/mean-reverting regime just as easily as a trending
one. This is a gap between the stated economic hypothesis and what was
implemented, not a post-hoc rationalization of the negative result (the
gap was visible by re-reading Section 2 against Section 4, independent of
the outcome). Testing this as a new, separately-numbered hypothesis
(trend-regime-gated breakout) is a conceptual redesign, not a parameter
tweak on the same design — see Experiment B4 below.

---

## Experiment B4 — trend-regime-gated breakout — IN PROGRESS

**STRATEGY_ID = B**
**Date**: 2026-08-23
**Status**: pre-registered below, cheap screen about to run.

**Design**: same as B1 (breakout N=60, vol_ratio>1.5, volume_ratio>1.5,
same exit mechanics) PLUS one new conceptual filter: `hurst_120[t] >
0.5` (trending regime, per the spec's own Section 2 economic hypothesis —
mean-reversion favors hurst<0.5, trend-continuation should favor
hurst>0.5). No other parameter changed. This directly operationalizes the
pre-registered regime hypothesis rather than searching new thresholds.

**Rejection criterion (fixed before running, same standard as B1)**:
REJECT if aggregate PF <= 1.0 on BOTH BTC and ETH with n>=30 combined.
If this also REJECTs, Strategy B's simple rule-based momentum/breakout
direction will be documented as REJECTED overall (both the naive and the
regime-gated variants failing is strong evidence against the phenomenon
at this timeframe/frozen-parameter level), and the next step would be to
rank alternative Strategy B directions rather than keep iterating on
breakout variants.

**Results (VALIDATION split, BTC/ETH, frozen exit mechanics)**:

| Symbol | n_trades | PF | Win rate | Forced liq |
|---|---|---|---|---|
| BTCUSDT | 551 | 0.576 | 36.1% | 0 |
| ETHUSDT | 465 | 0.791 | 37.6% | 0 |

n_total = 1016 (floor 30, satisfied). Manual sanity check: all 6 inspected
signals (3 BTC + 3 ETH) show MATCH on the independent breakout-level
recheck, and `hurst_120` values on the printed signals (0.50-0.62) are
correctly above the 0.5 gate. BUG CHECK / DATA CHECK / LOGIC CHECK /
REPRODUCIBILITY: all PASS, same reasoning as B1-B3.

Adding the trend-regime gate removed ~13% of BTC entries and ~13% of ETH
entries (fewer choppy-regime false breakouts) and produced a small PF
improvement (BTC 0.540->0.576, ETH 0.736->0.791) but **both symbols
remain well below the PF<=1.0 REJECT threshold**.

**VERDICT: REJECT.** Per the pre-registered plan above: both the naive
(B1) and trend-regime-gated (B4) variants fail cleanly on BTC and ETH
with adequate sample size. This is strong, consistent evidence against
this specific entry concept at the 1-minute timeframe with these frozen
parameters — not a borderline result that would justify further
parameter search on the entry side.

**Follow-up diagnostic (before fully closing the direction)**: since PF
improved only marginally between B1 and B4 despite a real regime filter
change, it's worth checking whether the failure is at the ENTRY level
(price simply doesn't move favorably after these breakouts — dead
signal) or at the EXIT level (the trailing-stop mechanics borrowed
wholesale from Strategy A's mean-reversion design, tuned for a ~10min
reversion horizon, may be structurally mismatched to a slower-developing
momentum move — cutting winners early via a tight 0.66-0.76% trail while
still eating full stop losses). This is checked via the raw MFE/MAE
distribution on B4's VALIDATION trades BEFORE any exit rule is applied
(the best-case forward excursion available to any exit design), not by
grid-searching exit parameters.

**Diagnostic script**: `scripts/strategy_b/diagnose_b4_mfe_mae.py`.
**Output**: `docs/strategy_b/strategy_b_diagnose_b4_mfe_mae.csv`.

| Symbol | n | MFE mean | MFE median | MAE mean | MAE median | Final mean | Final median | %MFE>cost |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 551 | +0.508% | +0.320% | -0.544% | -0.364% | -0.046% | -0.060% | 68.6% |
| ETHUSDT | 465 | +0.660% | +0.352% | -0.581% | -0.432% | +0.042% | -0.079% | 74.2% |

(round-trip cost = 0.12%; the `best_possible_pf` column in the raw CSV is
a divide-by-near-zero artifact of clipping negative MAE at 0 and should
be ignored — it does not affect the conclusion below, which rests on the
mean/median MFE/MAE/final-return figures.)

**Interpretation**: favorable excursion (MFE) and adverse excursion (MAE)
are roughly symmetric in magnitude, and critically, the RAW unmanaged
path return at trade end (no exit rule applied at all, just holding to
the end of the observation window) is close to zero on both symbols
(slightly negative on BTC, slightly positive but still ~breakeven on
ETH; medians negative on both). This means price does move favorably
enough to clear costs most of the time (68-74% of trades) but gives it
back just as often — there is no sustained net directional drift after
these breakouts at the 1-minute timeframe. This is a **dead-signal**
finding, not an exit-design artifact: no exit rule, however cleverly
designed, can reliably extract an edge from a path with ~zero net drift.
This directly explains why B1's and B4's PF stayed well below 1 despite
different exit-adjacent regime filtering, and rules out "wrong exit
design" as the explanation for the REJECT verdicts above.

**FINAL VERDICT on the momentum/breakout entry direction (B1+B4):
REJECT, with a documented mechanistic reason** (near-zero net drift after
breakout, not an implementation bug and not a fixable exit-parameter
issue). Per the mandate's explicit instruction not to force a positive
result, this direction is closed here — no further breakout-parameter or
exit-parameter search will be run against it. See "Ranked next Strategy B
directions" below for what to try instead.

---

## Experiment B8 — order-flow imbalance continuation (structurally new
hypothesis) — IN PROGRESS

**STRATEGY_ID = B**
**Date**: 2026-08-24
**Script**: `scripts/strategy_b/cheap_screen_b8_taker_imbalance.py`
**Pre-registered BEFORE running** in `docs/strategy_b/STRATEGY_B_SPEC.md`
REVISION 1.

**Design**: NOT a breakout-family variant — entry uses `taker_imbalance_20`
(already-existing order-flow feature) in its own top decile (240-bar
rolling percentile > 0.90) PLUS `rel_volume_20 > 1.5`, with NO
price-breakout/new-high condition at all. Economic rationale: aggressive
taker buy-vs-sell imbalance reflects urgent/informed order flow, a
different (microstructure) mechanism from price-level breakouts. Exit
mechanics, TRAIN-only calibration, and leverage formula are identical to
the B1 family (shared infrastructure, not shared alpha).

**Rejection criterion (fixed before running)**: REJECT if aggregate
PF <= 1.0 on BOTH BTC and ETH with n>=30 combined — same standard as
every prior Strategy B cheap screen.

**Results (VALIDATION split, 1-minute bars, frozen exit mechanics)**:

| Symbol | n_trades | PF | Win rate | Total return (unlevered) | Forced liq |
|---|---|---|---|---|---|
| BTCUSDT | 6999 | 0.507 | 33.2% | -709.79% | 0 |
| ETHUSDT | 6605 | 0.584 | 35.9% | -671.16% | 0 |

n_total = 13,604 — by far the largest sample of any Strategy B
experiment (a top-decile relative threshold recomputed continuously
still fires often in 1-minute data). Sanity check: all 6 inspected
signals MATCH between the vectorized rolling-rank and an independent
manual percentile recomputation. BUG CHECK / DATA CHECK / LOGIC CHECK:
PASS.

**VERDICT: REJECT — decisively.** PF 0.507/0.584 with n>6900 per symbol
is not a borderline call; this is one of the clearest negative results
in the Strategy B chain so far. The order-flow-imbalance hypothesis, as
operationalized here (top-decile relative taker imbalance + volume
confirmation, immediate entry), does not show positive expectancy on
BTC or ETH. No parameter variation of this specific filter will be
tested further.

**Updated interim status**: 5 independently-designed Strategy B
hypotheses now tested (B1 naive breakout, B4 trend-gated breakout, B6
15-min walk-forward, B7 squeeze-gated breakout, B8 order-flow
imbalance) — all REJECT. The two remaining ranked directions
(funding-rate/basis mean-reversion, cross-sectional relative-strength
rotation) both require NEW data acquisition or NEW infrastructure not
yet built, a meaningfully larger investment than the self-contained
cheap screens run so far. Per the anti-overfit discipline (raise the
bar as more variants are tested) and given this is a genuine
scope/resource decision rather than a "which experiment next"
choice, this is flagged for the user rather than launched
autonomously.

---

## Ranked next Strategy B directions (not yet launched)

Since the initial momentum/breakout hypothesis is cleanly REJECTED with a
mechanistic explanation (near-zero net post-breakout drift at 1-minute
resolution), these are candidate NEW economic hypotheses for a future
Strategy B iteration, ranked by expected scientific value. None have been
run — this is a ranking only, per the mandate's "rank, don't launch"
instruction for next-direction planning.

1. **Lower-frequency trend continuation (15min/1h bars)** — the diagnostic
   shows breakouts on 1-minute bars get faded within the same noisy
   micro-timeframe; crypto trend-following literature and this project's
   own regime work (`hurst_120`) target multi-hour+ structure. Testing
   the SAME conceptual entry (breakout + vol expansion + volume
   confirmation) on a coarser bar resolution is a natural, cheap next
   test and directly addresses the mechanism found here (drift may exist
   at a slower timescale even though it doesn't at 1-minute resolution).
2. **Volatility squeeze -> expansion (contraction-then-breakout)** —
   instead of a pure N-bar high breakout, require a preceding
   LOW-volatility contraction period before the expansion/breakout. This
   targets a more specific, arguably more genuine momentum setup
   (coiled-spring pattern) than "any breakout during elevated vol," which
   the diagnostic suggests is too permissive/noisy.
3. **Order-flow/taker-imbalance-driven continuation** — `taker_imbalance`
   already exists as a computed (if not yet pruned-in) feature in
   `quant_bot/features/basics.py`; a signal built on aggressive-buyer
   dominance rather than price-level breakout is a structurally distinct
   hypothesis from both Strategy A (mean-reversion) and the breakout
   idea just rejected.
4. **Funding-rate / basis mean-reversion** — a different structural
   family entirely (derivatives-market-specific mean reversion, not
   price-action momentum); would need new data (funding rate history)
   not yet downloaded, so higher setup cost than 1-3.
5. **Cross-sectional relative-strength rotation** — rank cryptos by
   recent relative performance and go long the strongest; a genuinely
   different signal class (cross-sectional, not single-symbol
   time-series), but needs a coherent multi-symbol universe and rotation
   mechanics not yet built, so highest setup cost of the five.

---

## Experiment B7 — volatility squeeze-then-breakout (1-minute) — IN PROGRESS

**STRATEGY_ID = B**
**Date**: 2026-08-23
**Script**: `scripts/strategy_b/cheap_screen_b7_squeeze.py`
**Pre-registered BEFORE running.**

**Design**: ranked direction #2 above. Same core filters as B1 (breakout
N=60 on 1-MINUTE bars, `realized_vol_ratio>1.5`, `rel_volume_20>1.5`),
PLUS exactly one new conceptual filter: a volatility SQUEEZE must have
existed near the start of the breakout range, i.e. `realized_vol_30`'s
240-bar rolling percentile rank, evaluated `BREAKOUT_LOOKBACK` (60) bars
before the signal bar, was `< 0.25` (bottom quartile — genuinely
compressed, not just "not currently expanding"). Economic rationale: a
breakout out of a range that itself formed during low volatility (a
"coiled spring") is a more specific, plausibly more genuine setup than
any breakout during merely-elevated current volatility (which B1/B4
already showed has ~zero net drift on average). Reverting to 1-minute
bars (not 15-min) for this first pass since B5/B6 showed 15-min sample
sizes are too thin to draw reliable conclusions; if this survives a 1-min
cheap screen, a 15-min version would be tested next with its own
pre-registration.

**Rejection criterion (fixed before running, same standard as B1)**:
REJECT if aggregate PF <= 1.0 on BOTH BTC and ETH with n>=30 combined.

**Results (VALIDATION split, 1-minute bars, frozen exit mechanics)**:

| Symbol | n_trades | PF | Win rate | Total return (unlevered) | Forced liq |
|---|---|---|---|---|---|
| BTCUSDT | 160 | 0.601 | 34.4% | -17.16% | 0 |
| ETHUSDT | 140 | 0.968 | 37.1% | -1.378% | 0 |

n_total = 300 (floor 30, satisfied by a wide margin). Sanity check: all 6
inspected signals (3 BTC + 3 ETH) MATCH on the independent breakout-level
recheck, and all show `vol_pctile` correctly below the 0.25 squeeze
threshold at the check index (0.013-0.204). BUG CHECK / DATA CHECK /
LOGIC CHECK: PASS.

**VERDICT: REJECT.** Both symbols PF <= 1.0 with adequate sample. Adding
the pre-breakout volatility-compression filter did not produce a
positive-expectancy setup — consistent with the B4 diagnostic's earlier
finding that price action after these breakout triggers shows no
reliable net directional drift regardless of what preceded the breakout
range. No further parameter variation of this filter will be tested. Per
the ranked list, remaining untested directions (order-flow imbalance,
funding-rate mean-reversion, cross-sectional rotation) are structurally
more different from the breakout family and would need dedicated new
data/infrastructure — noted as open leads, not launched this cycle given
three independently-designed breakout-family variants (B1, B4, B7) plus
one walk-forward (B6) have now all failed on 1-minute and/or 15-minute
BTC/ETH data.

---

## Experiment B5 — 15-minute timeframe trend continuation — IN PROGRESS

**STRATEGY_ID = B**
**Date**: 2026-08-23
**Script**: `scripts/strategy_b/cheap_screen_b5_15m_timeframe.py`
**Pre-registered BEFORE running.**

**Design**: identical conceptual entry to B4 (breakout above prior 60-bar
high + `realized_vol_ratio>1.5` + `rel_volume_20>1.5` + `hurst_120>0.5`
trend gate) and identical exit mechanics (TRAIN-derived trailing stop),
with exactly ONE variable changed: OHLCV bars are resampled from 1-minute
to 15-minute resolution (open=first/high=max/low=min/close=last/
volume=sum) independently within the already-split TRAIN and VALIDATION
frames (no leakage across the split boundary). Bar-count parameters
(N=60 etc.) are held numerically identical — this isolates timeframe as
the single new variable, motivated directly by the B4 diagnostic finding
of ~zero net drift at 1-minute resolution.

**Rejection criterion (fixed before running, same standard as B1/B4)**:
REJECT if aggregate PF <= 1.0 on BOTH BTC and ETH with n>=30 combined.
Given resampling to 15min reduces bar count ~15x, the n>=30 floor is a
real constraint here, not a formality — if VALIDATION doesn't yield
n>=30 combined, the correct conclusion is INSUFFICIENT SAMPLE, not REJECT
or CONFIRM.

**Results (VALIDATION split, 15-min bars, frozen exit mechanics)**:

| Symbol | n_trades | PF | Win rate | Total return (unlevered) | Forced liq |
|---|---|---|---|---|---|
| BTCUSDT | 59 | 0.998 | 39.0% | -0.093% | 0 |
| ETHUSDT | 38 | 1.279 | 47.4% | +9.244% | 0 |

n_total = 97 (floor 30, satisfied but thin — 12x fewer trades than the
1-minute screens). Sanity check: all 6 inspected signals MATCH on the
independent breakout-level recheck.

**Verdict on the pre-registered binary criterion**: does NOT trigger
REJECT (not both symbols have PF<=1.0 — ETH is 1.279).

**However, this is NOT being recorded as CONFIRMED.** Two reasons this
must stay at INVESTIGATE, not CONFIRMED, pending real walk-forward:
1. BTCUSDT's PF (0.998) is essentially exactly breakeven, not a real
   positive edge — only ETHUSDT clears 1.0 with any margin. This
   project's own standing methodology rule requires BOTH symbols to
   agree before treating a result as validated
   ([[research_methodology_rules]]); a single-symbol result here would
   not meet that bar even before considering sample size.
2. n=97 combined is thin (12x fewer trades than the 1-minute cheap
   screens which had n=1016-1196) — a small-sample result sitting right
   at the pre-registered pass/fail boundary is exactly the situation the
   project's anti-overfit rule warns about (raise the bar as the number
   of tested variants grows; this is already the 3rd distinct entry
   concept tried: B1 naive, B4 trend-gated, B5 timeframe-shifted).

**NEXT ACTION**: per STRATEGY_B_SPEC.md Section 9/10, since the cheap
screen did not trigger the binary REJECT, the correct next step is a real
walk-forward (multiple expanding-TRAIN folds, not just one TRAIN/VALIDATION
split) at 15-minute resolution, which will either (a) show a stable,
majority-of-folds-PF>1 result on BOTH symbols — worth then treating as a
genuine candidate — or (b) reveal this VALIDATION-window result was
itself a fold-specific fluke, consistent with REJECT. Proceeding to B6.

---

## Experiment B6 — 15-minute walk-forward (frozen B5 entry concept) — IN PROGRESS

**STRATEGY_ID = B**
**Date**: 2026-08-23
**Script**: `scripts/strategy_b/walkforward_b6_15m.py`
**Pre-registered BEFORE running.**

**Design**: reuses Strategy A's fold construction
(`scripts/walk_forward_engine.py`'s `build_folds` — expanding TRAIN,
24-month initial, 3-month TEST, 3-month step, bounded by
`SAFE_END = min(BTC, ETH HOLDOUT_START)`, imported not re-derived) as
shared infrastructure. The B5 entry rule (breakout N=60 on 15-min bars +
vol_ratio>1.5 + volume_ratio>1.5 + hurst_120>0.5) is completely FROZEN
across folds — only the TRAIN-derived stop-distance/activate/trail/
leverage constants are recalibrated per fold from that fold's own TRAIN
population (same discipline as every walk-forward in this project).

**Rejection criteria (fixed before running, per STRATEGY_B_SPEC.md
Section 9)**: reject if median PF <= 1 on either symbol, or if the
result depends on a single dominant fold (a small number of folds
carrying all the positive P&L while the rest are flat/negative). Given
B5's already-thin per-window sample (n=97 for the whole VALIDATION
period), per-fold trade counts here will be even smaller — if any fold
has too few trades to be meaningful, it will be reported but not treated
as informative on its own; the SUMMARY (median PF, %folds PF>1 per
symbol, n_total) is the deciding evidence, not any single fold.

**Results (13 folds, 2019-11 -> 2025-02, bounded by SAFE_END=2025-03-28)**:

| Symbol | n_folds | median PF | %folds PF>1 | n_total_trades | forced_liq |
|---|---|---|---|---|---|
| BTCUSDT | 13 | 0.940 | 46.2% | 123 | 0 |
| ETHUSDT | 13 | 1.237 | 61.5% | 89 | 0 |

Full per-fold table: `docs/strategy_b/strategy_b_walkforward_b6_15m.csv`.

**VERDICT: REJECT, on two independently sufficient grounds**:
1. **BTCUSDT median PF = 0.940 <= 1.0** — directly triggers the
   pre-registered "median PF<=1 on either symbol" criterion by itself.
2. **ETHUSDT's positive aggregate is a single-fold artifact.** Summing
   `total_return_pct_unlevered` across all 13 ETH folds gives ~+5.28%
   total. The single fold with `test_end=2024-05-27` (n=7 trades,
   PF=15.47) alone contributed +14.77% — MORE than the entire 13-fold
   aggregate. Removing that one fold, the remaining 12 folds net to
   roughly -9.5%. This is exactly the "depends on a single dominant
   fold" pattern the pre-registration flagged as disqualifying,
   independent of the median-PF check.

Both BTC and ETH fail the walk-forward on independent grounds, so this
is not a borderline call. Per-fold trade counts are also uniformly thin
(2-14 trades per 3-month TEST window), consistent with the earlier
finding that the entry concept fires rarely and, per the B4 diagnostic,
carries no reliable net directional edge once it does fire.

**This formally closes the momentum/breakout entry-concept line for
Strategy B** (B1 naive REJECT -> B4 trend-gated REJECT -> B4 diagnostic:
dead signal, not exit-design artifact -> B5 15-min cheap screen:
marginal/thin, correctly flagged INVESTIGATE rather than accepted ->
B6 walk-forward: REJECT on two independent grounds). No further
parameter variation of THIS concept will be tested; per the ranked
"next Strategy B directions" list above, any future Strategy B work
should pursue a structurally different hypothesis (volatility-squeeze
setup, order-flow imbalance, etc.), each requiring its own fresh
pre-registration — not a continuation of this experiment chain.
