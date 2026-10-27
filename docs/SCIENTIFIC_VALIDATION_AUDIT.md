# Scientific Validation Audit

**Role**: independent scientific red team / research auditor (not a
strategy-research track). Mandate: make it harder for a false edge to
be accepted, not to find another one. User-directed, 2026-08-24.

**Scope boundary**: Strategy A stays FROZEN (audited, not modified,
except two proactive bugfixes to non-active research scripts —
documented in Section 7). Strategy B is CLOSED/REJECT (not reopened).
Strategy C is Gemini's track (not duplicated — Section 9 defines the
protocol for when its artifacts exist; nothing to audit yet). Codex
owns `quant_bot/risk/`, execution, forward paper, and HOLDOUT
enforcement (`quant_bot/data/splits.py`) — read-only throughout.

---

## 1. Current evidence map

```
STRATEGY A (mean-reversion, BASELINE_CANDIDATE_V3)
  TRAIN -----------> VALIDATION -----------> WALK-FORWARD OOS -----> HOLDOUT
  (model fit,         (single-split          (13 expanding folds,     (LOCKED,
   filter cutoffs,      screening,             the population           never
   stop calibration)    now historical)        every adopted            touched)
                                                number is built from)
  Reused for portfolio construction, XRP p80 / LINK p95 refinement,
  Phase A new-symbol screens, and all Strategy A shadow diagnostics
  (Experiments 40-42) -- see Section 3 for what this reuse implies.

STRATEGY B (momentum/breakout family) -- CLOSED, 11/11 REJECT
  B1-B8 (crypto breakout/momentum), BF1-BF2 (funding), BR1-BR2
  (rotation), BI1-BI3 (Nasdaq index) -- all pre-registered, all
  falsified at the diagnostic or walk-forward stage, no result forced.

STRATEGY C (Gemini) -- no artifacts exist yet. Section 9/Section 10
define the audit and null-model protocol to apply once they do.

FORWARD PAPER (Codex) -- running against the frozen 9-symbol baseline.
Not yet a source of independent evidence (too new / not yet audited
here) -- Section 13 defines how to interpret it once results accumulate.
```

## 2. Experiment count / research ledger

Two ledgers exist, kept intentionally separate per the STRATEGY_ID
convention (`docs/STRATEGY_INDEX.md`):

- **Strategy A**: `docs/research_plan_status.md` — Experiments 0.1, 0.2,
  1, 1b, 2 through 42 (39 top-level numbered experiment cards; several
  contain 5-30+ internal parameter/variant sub-tests each — see the
  full per-experiment table below). Current frozen baseline:
  `docs/multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv`, 9
  symbols (BTC/ETH/SOL[transfer]/BNB/XRP/DOGE/ADA/LINK/LTC — AVAX
  explicitly REJECTED in Experiment 34), @ 1.50% risk/trade:
  **CAGR=56.46%, MaxDD=-14.43%, Calmar=3.912, PF=1.350, 0 forced
  liquidations**.
- **Strategy B**: `docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md` +
  `docs/strategy_b/{funding,rotation,index}/*_RESEARCH_LOG.md` — 11
  pre-registered hypotheses (B1, B4, B6, B7, BF1, BF2, BR1, BR2, BI1,
  BI2, BI3), all REJECT. Status: CLOSED for this cycle.

### Full Strategy A experiment ledger (Experiments 0.1-34)

| Exp | Hypothesis | Data | Markets | Pre-reg? | n | Decision | Bug? | Rerun? | Current relevance |
|---|---|---|---|---|---|---|---|---|---|
| 0.1 | V1 reproduces its own recorded VALIDATION numbers | VALIDATION | BTC,ETH | Y | 42/89 | PASS | N | N/A | historical (V1 superseded) |
| 0.2 | record-keeping (split boundaries) | n/a | n/a | N/A | n/a | on record | N | N/A | still authoritative |
| 1 | V1 survives realistic execution frictions | VALIDATION | BTC,ETH | Y | 42/89 | INVESTIGATE | Y (overlapping-position bug, fixed pre-report) | Y | historical; motivated V2's wider trail |
| 1b | wider trailing distance reduces gap fragility | VALIDATION | BTC,ETH | Y | 42/89 | PROMOTE trail→0.80% | N | N/A | superseded by V2 (still-active param origin) |
| 2 | V2 shows edge under expanding walk-forward | 13-fold WF | BTC,ETH | Y | ~19/36 | INVESTIGATE (weak) | Y (fold-local forced-liq risk surfaced) | N/A | superseded by Exp28's own WF |
| 3 | bucket analysis of V2's VALIDATION trades | VALIDATION | BTC,ETH | N (exploratory) | 131 | INVESTIGATE (leads) | N | N/A | superseded by Exp4/12/24 |
| 4 | TRAIN vol-filter (p75) improves PF | TRAIN calib/VALIDATION eval | BTC,ETH | Y | 5-12 | INVESTIGATE (promising, n too small) | N | N/A | unresolved lead, never revisited |
| 5 | RF threshold sweep 0.70-0.925 | TRAIN calib/VALIDATION eval | BTC,ETH | Y | 42-267 | INVESTIGATE (BTC 0.725 lead) | Y (VALIDATION-calibrated stop leak, first found+fixed here) | Y | BTC 0.725 lead formally REJECTED in Exp8 |
| 6/6b | protective-stop percentile sweep p70-p97.5 | TRAIN calib/VALIDATION+gap stress | BTC,ETH | Y | 42/89 | REJECT p70 replacement | Y (CEILING_MULT leverage bug, fixed pre-report) | Y | closed; p90 remains registered |
| 7 | entry-time linear classifier predicts bad trades | TRAIN fit/VALIDATION eval | BTC,ETH | Y | 330/628 train | REJECT (AUC≈chance) | Y (2 bugs: pandas datetime-slicing footgun, memory blowup — both fixed pre-report) | Y | closed, clean negative |
| 8 | threshold=0.725 survives gap-stress | VALIDATION+gap stress | BTC,ETH | Y | 42-104/89-165 | REJECT (both-symbols-must-agree) | Y (VALIDATION-stop leak RECURRED, caught building Exp11, fixed+rerun) | Y | closed |
| 9 | regression target beats binary classifier | TRAIN fit/VALIDATION eval | BTC,ETH | Y | 183-1065 | REJECT (AUC≈chance) | N | N/A | closed, clean negative |
| 10 | trailing/time-exit flexibility net positive | VALIDATION | BTC,ETH | N/A (confirmatory) | 131 | KEEP (confirms design) | N | N/A | still-relevant background |
| 11 | ATR-scaled trailing beats fixed 0.80% | TRAIN calib/VALIDATION+gap stress | BTC,ETH | Y | 42/89 | INVESTIGATE (not promoted) | N | N/A | not promoted; V3 kept fixed trail |
| 12 | TRAIN EV gate (vol×hour) improves baseline | TRAIN(12 cells)/VALIDATION+stress+**WF** | BTC,ETH | Y | 17-38/37-66 | DOWNGRADED to INVESTIGATE — **WF caught what fixed-split+stress missed** | N (methodological finding) | N/A | closed, not promoted |
| 13 | BTC/ETH stress asymmetry explained by VALIDATION-window move frequency | raw 1-min data | BTC,ETH | N/A | full window | RESOLVED (explanatory) | N | N/A | still-cited background |
| 14 | combined BTC+ETH portfolio improves risk-adjusted metrics | VALIDATION | BTC,ETH | Y | 131 | KEEP (real diversification) | N | N/A | **numerically superseded 2026-08-22** (see bug registry); PF/return/forced-liq analytically survive |
| 15 | uniform leverage multiplier spends diversification headroom | VALIDATION | BTC,ETH | Y | 131 | KEEP mult=1.2-1.3x | N | N/A | **reconciled 2026-08-23: survives analytically** |
| 16 | delayed/limit-retrace entry improves on immediate | VALIDATION | BTC,ETH | Y | 42/89 | REJECT all variants | N | N/A | closed; immediate entry stays default |
| 17 | Exp15's leverage candidate survives gap stress | VALIDATION+gap stress | BTC,ETH | Y | 131 | KEEP mult=1.2x | N | N/A | **reconciled 2026-08-23: survives analytically** |
| 18 | funding_ma_3 as a MODEL FEATURE carries predictive info | TRAIN fit/VALIDATION eval | BTC,ETH | Y | 30-61/42-89 | PROMOTE CANDIDATE | N | N/A | downgraded in Exp21 (WF); independently re-REJECTED this session (B_FUNDING) |
| 19 | continuous sizing (proba/MAE/EV) beats fixed sizing | TRAIN fit/VALIDATION eval | BTC,ETH | Y | 42/89 | REJECT all 4 schemes | N | N/A | closed; fixed sizing stays default |
| 20 | funding feature survives gap stress | VALIDATION+gap stress | BTC,ETH | Y | 30-61/42-89 | PROMOTE CANDIDATE | N | N/A | superseded by Exp21 |
| 21 | funding feature survives full 13-fold WF | 13-fold WF | BTC,ETH | Y | 6-7/8 folds | DOWNGRADED to INVESTIGATE (WF divergence again) | N | N/A | closed, not promoted (2nd WF-catches-fixed-split-miss instance) |
| 22 | registered leverage is calibration-window-specific | analytical, saved stop distances | BTC,ETH | N/A (diagnostic) | 16 fold×sym | INVESTIGATE (structural gap found) | N (the finding itself) | N/A | motivated Exp23's fix |
| 23 | per-fold dynamic leverage closes Exp22's gap | 13-fold WF | BTC,ETH | Y | 8/8 folds | ADOPT methodology | N | N/A | standard throughout rest of project |
| 24 | hurst×vol regime classifier reveals a bad regime | TRAIN(98-112/cell)/VALIDATION | BTC,ETH | Y | 42/89 | REJECT as filter (no-op, all cells+EV) | N | N/A | RANGE>TREND gradient later informed B_INDEX framing |
| 25 | Exp14 portfolio + Exp23 leverage removes forced-liq | VALIDATION | BTC,ETH | Y | 131 | ADOPT methodology | N | N/A | **reconciled 2026-08-23: survives analytically** |
| 26 | Monte-Carlo risk_pct sweep, elimination-before-results | full WF export | BTC,ETH | Y (elimination rule fixed first) | 55 | ADOPT methodology; do NOT adopt specific 7.5% (n=55 caveat) | **Y — MAJOR (portfolio-engine bug, see Section 7)** | Y | **CORRECTED 2026-08-23**: reported 7.5%/13.0%/0.878 → corrected 8.95%/0.567; reported "Calmar hump" doesn't exist (declines monotonically) |
| 27 | 0.60-0.75 proba band has a distinguishable positive-EV sub-population | TRAIN only, 540,763 bars | BTC,ETH | N/A (exploratory) | 4-1535/cell | INVESTIGATE → feeds Exp28 | N | N/A | directly produced BASELINE_CANDIDATE_V3 |
| 28 | threshold=0.70 (filter mandatory) increases n without destroying PF, under WF | 13-fold WF | BTC,ETH | Y | 211/333 | **KEEP — promoted to V3** | Y (frozen leverage miscalibrated for wider threshold=0.70 stop distribution, fixed via dynamic leverage before trusting results) | Y | **still authoritative** (defines V3's threshold) |
| 29 | some 10min "losers" would be winners at a different horizon | TRAIN fit/VALIDATION-only screen | BTC,ETH | Y | 70-445/127-761 | INVESTIGATE → h=20 promoted to Exp30 | N | N/A | superseded — h=20 REJECTED in Exp30 |
| 30 | horizon=20min beats V3's horizon=10 under WF | 13-fold WF | BTC,ETH | Y | 62-211/107-333 | **REJECT** | **Y — HORIZON/LOOKAHEAD decoupling bug, FIRST discovery (see Section 7)** | Y (full re-run, buggy result discarded) | closed; V3's horizon=10 stays authoritative |
| 31 | risk-sweep re-run on V3's larger population | full V3 WF export | BTC,ETH | Y (same elimination rule) | 544 | ADOPT 4.0% (superseding Exp26) | **Y — same engine bug as Exp26** | Y | **CORRECTED 2026-08-23**: reported 4.0%/60.98%/3.465 → corrected, and **the reported pick FAILS its own elimination rule** (MC P(DD>30%)=14.5%); corrected robust pick 3.0%/20.42%/1.293. Signal-quality conclusion (V3>V2) unaffected |
| 32 | V3's exact strategy shows edge on Nasdaq/SP500 before adaptation | fresh 60/20/20 per market | Nasdaq,SP500,(EURUSD) | Y | 3,493-5,532 | **REJECT** (unchanged + 3 follow-up fixes, all fail) | N | N/A | still authoritative — the finding this session's B_INDEX explicitly distinguished itself from |
| 33 | BTC/ETH edge generalizes to 8 other liquid Binance symbols | fresh 60/20/20 + transfer, then 13-fold WF | SOL,BNB,XRP,DOGE,ADA,LINK,AVAX,LTC | Y (triage bands fixed first) | 1,262 (8-sym portfolio) | **KEEP — 8-symbol ADOPTED** | Y (infra: shell-tool killing backgrounded downloads) + **same engine bug as Exp26/31** | Y (infra); Y (engine, 2026-08-22) | **CORRECTED 2026-08-22**: reported 125.0%/5.501 → corrected 29.54%/2.380. Relative "more symbols→better Calmar" conclusion survives/reinforced |
| 34 | SOL/AVAX resolved via full-WF pooling then transfer-mode WF | 13-fold WF, own then transfer | SOL,AVAX | Y (two-stage plan) | 1,287/1,394 (transfer) | SOL **ADOPTED** (transfer); AVAX **REJECTED** | **Y — same engine bug** | Y (2026-08-22) | **CORRECTED**: 9-symbol reported 282.14%/11.802 → corrected 52.05%/3.236, later refined by Exp35/36 to the current 56.46%/3.912 |
| Historical Reconciliation | do Exp15/17/25/26/31's decisions survive the corrected engine? | re-analysis, no new sim | BTC,ETH(+portfolio) | Y (protocol fixed) | 55/544/131 | 26/31 numerically corrected (methodology survives, magnitudes invalidated); 15/17/25 analytically argued to survive | N/A (meta) | N/A | **authoritative reconciliation** — the "never cite old absolute figures" list |
| 35 | XRPUSDT protective-stop p90→p80 | portfolio-level, `quant_bot/risk` | 9-symbol portfolio | Y | — | **KEEP** | N | N/A | authoritative, in current baseline |
| 36 | LINKUSDT protective-stop p90→p95 | portfolio-level, `quant_bot/risk` | 9-symbol portfolio | Y | — | **KEEP** | N | N/A | authoritative, in current baseline (current frozen reference) |
| 37-39 (Phase A) | does frozen V3 generalize to ETC/TRX/DOT? | transfer-mode WF + portfolio shadow | ETC,TRX,DOT | Y | 945/985/214 | ETC/DOT solo PASS but portfolio REJECT (Calmar drag); TRX solo REJECT | N | N/A | 0/3 adopted; documented lead only |
| 40 | acute short-horizon BTC-shock exclusion filter | single-population SHADOW | BTC+9-symbol portfolio | Y | 2549 candidates | **REJECT** (excluded 56.7% of trades incl. 825 winners; wrong reference population) | N (specification flaw, not a bug) | N/A | closed |
| 41 | cross-symbol shock breadth filter | conditional-population diagnostic | 9-symbol basket | Y | 1370 executed | **REJECT at diagnostic stage** (stop rate flat across breadth; highest-breadth bucket MOST profitable) | Y (NaN-masking bug in shock_breadth construction, found+fixed+regression-tested before trusting result) | Y | closed |
| 42 | temporal stability of BTC/ETH/BNB/LTC leave-one-out drag | 12-fold walk-forward + null control | 9-symbol portfolio | Y | 2317 (TEST-fold pop) | **REJECT** (dynamic universe underperforms static AND 91% of random-exclusion null draws) | N | N/A | closed; STATIC_9SYM remains baseline; BNB reclassified KEEP on closer inspection |

**Total distinct hypotheses/parameter variants, order-of-magnitude
estimate**: Strategy A alone (Experiments 0.1-42, counting internal
grid points/sub-variants within each card, per the extraction above) is
in the range of **180-280 individually-evaluated variants** — the exact
figure is not tracked as a running tally anywhere in the project and
cannot be reconstructed precisely (see Section 4's honest treatment of
this). Strategy B adds 11 more pre-registered hypotheses (crisper count,
since that log was built with STRATEGY_ID discipline from day one).
**Grand total: on the order of 200-300 things looked at before any
result was reported or acted on.**

## 3. Multiple-testing / researcher-degrees-of-freedom exposure

**Overall assessment: MODERATE-TO-HIGH**, concentrated in specific
areas, not uniform across the whole project. Breaking this down by
category rather than asserting one blanket number, per the mandate's
own instruction not to force an artificial global p-value where the
underlying experiments don't support one:

| Category | Exposure | Why |
|---|---|---|
| Number of ENTRY-SIGNAL hypotheses tested | **LOW** | Only one entry family (mean-reversion, threshold/filter/RF) was ever seriously pursued for Strategy A; Strategy B tested exactly 11 pre-registered, structurally distinct hypotheses (not 100s of variants per family — the project's own discipline of "at most a couple of follow-ups, then REJECT the family" visibly held throughout, verified directly this session). |
| Number of PARAMETER THRESHOLDS swept within an adopted design | **MODERATE-HIGH** | Threshold (Exp5/8/28), stop percentile (Exp6/6b), horizon (Exp29/30), leverage multiplier (Exp15/17), EV gate (Exp12) — 5+ dimensions each independently swept, several with 5-15+ grid points. Each individual sweep was disciplined (both-symbols-must-agree, WF confirmation), but the CUMULATIVE effect of "we tried threshold, then stop%, then horizon, then EV-gate, then per-symbol XRP p80/LINK p95..." on the SAME underlying BTC/ETH TRAIN/VALIDATION population is a real multiple-comparisons exposure that no single experiment's own bar fully controls for. |
| Number of CRYPTOS screened for portfolio inclusion | **MODERATE** | 8+2 (SOL/AVAX) + 3 (Phase A ETC/TRX/DOT) = 13 candidate symbols evaluated, triage bands fixed BEFORE results each time (a real, verified discipline) — but 13 independent symbol-level tests against similar entry logic is still a meaningful number of "shots on goal," and Section 42's finding (that a symbol's full-sample marginal contribution can look decisively negative yet be a near-coin-flip out-of-sample) is direct evidence that at least SOME of the 9 currently-adopted symbols' apparent individual value could be partly a selection artifact of "which symbols happened to test well in this specific historical window," not purely a stable structural property. |
| Number of PROTECTIVE-STOP PERCENTILE refinements per symbol | **HIGH, if extended further** | Exp35 (XRP p80) and Exp36 (LINK p95) were each a SINGLE, hypothesis-driven, portfolio-validated change — genuinely disciplined as executed. But this is a template ("does symbol X's stop percentile deserve a look") that could be applied to any of the other 7 symbols; doing so for all 9 without raising the acceptance bar per additional test would be a classic researcher-degrees-of-freedom trap. This is flagged as a standing risk for FUTURE work, not a criticism of Exp35/36 as already executed. |
| Number of RISK-FRONTIER re-sweeps (Codex track) | **not assessed here** | Codex-owned; out of this audit's scope by the mandate's own boundary, beyond the methodological Monte Carlo review in Section 6. |

**Results most exposed to selection bias**, ranked:

1. **The per-symbol stop-percentile refinements (XRP p80, LINK p95)** —
   each individually well-controlled (portfolio-level test, TRAIN-only
   calibration, no risk_pct inflation), but the DECISION to look at
   these two specific symbols, out of 9, for this specific
   modification, out of many possible ones, was not itself randomized
   or pre-registered across the whole symbol set — it followed from
   noticing something in the data first (this is explicitly how the
   mandate's own Phase 6 for Experiment 41/42 was framed: "a symbol
   shows unusual stop-outs → economic hypothesis about its stop," which
   is a legitimate discovery process, but is inherently NOT the same
   evidentiary strength as a pre-registered test across all 9 symbols
   decided before looking at any of them).
2. **The full-sample BTC/ETH/BNB/LTC leave-one-out finding** (alpha
   decomposition, Section 3 of that report) — directly shown by
   Experiment 42 to be substantially a full-sample/regime-dependent
   artifact, not a temporally stable property. This is the CLEAREST,
   most direct, already-demonstrated instance of selection bias in this
   project's own recent history, and is exactly why Experiment 42 was
   run and correctly REJECTED the naive full-sample conclusion.
3. **Threshold=0.70 and horizon=10min** (V3's own defining parameters)
   — both survived a full 13-fold walk-forward with both-symbols-must-
   agree discipline (a real, meaningful bar), but they are still the
   SURVIVORS of Experiments 5/8 (threshold, 2 REJECTED variants) and
   29/30 (horizon, 1 REJECTED variant at h=20, several more screened at
   the cheap-screen-only stage in Exp29 without WF confirmation) — the
   walk-forward bar is real evidence, but it was only ever applied to
   the candidates that survived an earlier, less rigorous screen, which
   is a standard and defensible research funnel, not a red flag by
   itself, but worth stating plainly as part of the full evidentiary
   picture rather than only citing the final WF pass rate.
4. **The 9-symbol portfolio composition itself** — see category table
   above; Experiment 42 already demonstrated this is a legitimate,
   ongoing concern worth monitoring, not merely a hypothetical one.

## 4. Independence audit

**Central finding, discovered and demonstrated directly in this
project's own Experiment 42 (2026-08-24)**: cumulative/expanding-window
TRAIN populations across walk-forward folds are NOT independent
observations — each fold's TRAIN nests almost entirely inside the next
fold's TRAIN (fold 8's TRAIN contains ~90%+ of fold 5's TRAIN plus a
few more months). A "92% of TRAIN folds agree" statistic can be almost
entirely autocorrelation. Experiment 42 demonstrated this concretely:
the SAME leave-one-out question showed 83-92% "consistency" on
cumulative TRAIN populations vs. 46-54% (near coin-flip) on the
genuinely non-overlapping TEST populations for the same symbols.

**Where else this class of problem could exist in the project, audited
here**:

| Location | Independence status | Assessment |
|---|---|---|
| Every "N/13 folds show PF>1" statistic reported throughout Strategy A's history (Exp2, 21, 28, 30, 33's per-symbol WF, 34) | **TRAIN is cumulative/nested by construction** (`build_folds`'s `INITIAL_TRAIN_MONTHS=24` expanding design) — but the PASS/FAIL statistics historically reported (e.g. "11/13 folds PF>1" for SOL) are computed on the **TEST populations**, which ARE non-overlapping by construction (`TEST_MONTHS=3, STEP_MONTHS=3`, no overlap between consecutive test windows) | **Genuinely OK** — the project's standard "%folds PF>1" convention already uses the correct (TEST, non-overlapping) population; Experiment 42's finding is about a case where I (this session) computed a NEW statistic on the cumulative TRAIN side specifically, not a flaw in the project's long-standing WF convention itself. This is reassuring, not alarming — but worth stating explicitly since Experiment 42's finding could otherwise be mis-generalized as "the project's walk-forward numbers are all suspect," which they are not. |
| Overlapping trades within a single TEST fold (same symbol, or portfolio-level across symbols) | Potentially overlapping in TIME (two different symbols' positions open simultaneously) but each trade is still a **distinct, independent draw of the underlying signal** (different symbol, different entry trigger) | **Low concern for the signal's own statistical validity**, but HIGH relevance for portfolio risk accounting (correctly handled by `quant_bot/risk`'s exit-time-ordered realization) and for Monte Carlo bootstrap assumptions (see Section 6 — this is where overlapping-trade dependence actually matters). |
| Overlapping LABELS (a single price series' forward-looking label windows can overlap between adjacent entries) | Present by construction (`LOOKAHEAD=50` bar window, entries can occur closer together than 50 bars apart in principle, though `fast_trades`'s own pointer-jump logic advances past `next_i = i + HORIZON or i + exit_offset`, meaningfully reducing but not eliminating overlap) | **Not separately audited with a dedicated purge/embargo mechanism** anywhere in this project's history, as far as this audit's ledger review found. This is a real, standard "label overlap" concern from the broader ML-for-finance literature (e.g. triple-barrier/purged-CV literature) that this project has never explicitly addressed. Flagged as a genuine, previously-unexamined gap — see Section 15 for whether it's likely to matter in practice given the pointer-jump mitigation already in place. |
| Repeated market regimes (the same underlying 2021-2024 crypto cycle observed through 9 different, highly-correlated symbols) | The 9 symbols are NOT independent draws of "crypto market behavior" — they share substantial common variance (BTC-driven macro moves, as directly confirmed by this session's own cross-correlation/breadth measurements in Experiment 41: shock_breadth=1.0, i.e. ALL 9 symbols simultaneously shocked, in >10% of Strategy A's own entries) | **This is the single most important standing independence concern in the whole project.** "9 symbols confirm the edge" is meaningfully weaker evidence than 9 independent markets would provide, because they substantially share the same underlying regime history. Experiment 33/34's own "more symbols → better Calmar" finding is a genuine diversification result (correctly measured through the portfolio engine, which does account for cross-symbol correlation in risk terms) but should not be read as "9 independent confirmations of the entry-signal edge" — it is closer to "1-2 effectively-independent market regimes (crypto bull/bear cycles), replayed through 9 correlated instruments." |
| Portfolio aggregation (does combining symbols create a NEW, unaudited independence assumption) | `quant_bot/risk`'s `simulate_portfolio` correctly realizes P&L in exit-time order on a SHARED equity base — this is NOT naively summing 9 independent equity curves, it is a single, correctly-sequenced simulation. **No independence assumption is silently smuggled in at the aggregation step itself.** | **OK** — this was exactly the class of bug Codex's `C-AUDIT-001` already found and fixed (Section 7); the CURRENT engine is correctly ordered. |
| Monte Carlo bootstrap (`bootstrap_drawdowns`) | See Section 6 — a genuine, separate independence concern (does resampling preserve real clustering) | **See Section 6.** |

## 5. Strategy A confidence assessment (Phase 3 audit questions)

**1. What is genuinely out-of-sample?** The 13-fold walk-forward TEST
populations (non-overlapping, each fold's model/cutoffs/stop fit only
on that fold's own TRAIN) — this is the strongest evidence class in the
project. The XRP p80/LINK p95 portfolio-level tests are ALSO
genuinely evaluated against the walk-forward OOS trade population, not
re-fit.

**2. What participated in MODEL selection?** Threshold (0.70, survivor
of Exp5/8), horizon (10min, survivor of Exp29/30), EV-gate (rejected,
Exp12), protective-stop percentile (p90 base + XRP p80/LINK p95
refinements) — each was screened on VALIDATION and/or a fixed split
BEFORE its own dedicated walk-forward confirmation. The MODEL
ARCHITECTURE itself (RF, joint BTC+ETH training, feature set via
`prune_redundant`) was fixed early (Phase 3-era) and not itself
re-swept across this later parameter-tuning history.

**3. What participated in CRYPTO selection?** All 9 currently-adopted
symbols passed a pre-registered triage band (Experiment 33) BEFORE
their own dedicated walk-forward — a real, disciplined process. But
per Section 3/4 above, "passed triage + WF" is not the same evidentiary
strength as "pre-registered across an unbiased universe with no
opportunity for the triage bands themselves to be tuned toward already-
observed results" — the triage bands are stated as fixed before results
in the ledger, which this audit takes at face value from the document
but did not independently re-derive from raw logs.

**4. What participated in STOP selection?** The base p90 percentile was
fixed early (pre-V3). XRP's p80 and LINK's p95 are the two SPECIFIC,
already-executed exceptions — both hypothesis-driven and portfolio-
validated (Experiments 35/36), not a blind sweep. Experiment 42's
BTC/ETH/BNB/LTC drag investigation deliberately did NOT touch stops
(explicitly scoped to symbol removal, not stop retuning) — so stop
selection remains confined to exactly these 2 documented instances.

**5. What participated in PORTFOLIO selection?** The 9-symbol
composition itself (Experiments 33/34, AVAX explicitly rejected, SOL
transfer-mode adopted) and the risk_pct level (1.50%, from the Monte
Carlo elimination-rule sweep, corrected 2026-08-23). Experiment 42's
STATIC_9SYM decision means no FURTHER portfolio-composition selection
has occurred beyond this.

**6. What data has been observed MULTIPLE TIMES during research?**
BTC and ETH's TRAIN+VALIDATION history has been observed and re-used
across essentially every experiment in the ledger (0.1 through 42) —
this is the single most-reused dataset in the project by a wide margin.
The 13-fold walk-forward's EXPANDING TRAIN windows mean later folds'
TRAIN data overlaps heavily with earlier folds' TEST data too (a fold's
TEST trades, once "seen," inform the researcher's general understanding
even if not literally re-used as TRAIN for THAT specific symbol/fold
combination) — this is a subtle, hard-to-fully-eliminate form of
research contamination inherent to any iterative walk-forward-based
project, not unique to this one, but worth stating plainly rather than
implying the walk-forward folds are fully hermetically sealed from each
other in the researcher's own mind.

**7. What remains genuinely, truly unobserved?** **HOLDOUT** — for every
symbol, at every stage, confirmed never loaded/scored/summarized
throughout this entire audit and the whole session's prior work (every
script in this session's own history explicitly truncates price/
funding/shock-breadth data at each symbol's own `HOLDOUT_START` BEFORE
computation, verified directly in this session's own code, e.g.
`scripts/strategy_a/build_regime_context.py`,
`scripts/strategy_a/build_shock_breadth.py`). This is the ONE dataset
in the whole project that has zero reuse across the ~200-300 variants
counted in Section 2.

**Split taxonomy, stated explicitly per the mandate's request**:
- **TRAIN**: per-fold expanding window, refit every fold, never reused
  across symbols' own model fits (BTC/ETH jointly trained; other
  symbols either transfer-scored with BTC/ETH's frozen model or
  independently fit, per Experiment 33's own documented per-symbol
  choice).
- **VALIDATION/WALK-FORWARD OOS**: the TEST folds — genuinely
  out-of-sample per-fold, the strongest evidence tier, and (per Section
  4) correctly non-overlapping for the standard "%folds PF>1"
  statistics.
- **RESEARCH-REUSED DATA**: the aggregate TRAIN+TEST history considered
  as a whole across the ~40 experiment cards — reused dozens of times
  for different questions, the source of the multiple-testing exposure
  in Section 3.
- **TRUE HOLDOUT**: locked, confirmed untouched throughout.
- **FORWARD PAPER**: Codex's live-forward track — not yet a mature
  evidence source (Section 13).

## 6. Monte Carlo / bootstrap methodology review (`quant_bot/risk.bootstrap_drawdowns`)

Read directly (`quant_bot/risk/portfolio.py`), not rebuilt. The function
resamples PER-TRADE PnL fractions (one value per executed trade, taken
from the exit-time-ordered `simulate_portfolio` log) either IID
(`block_size=1`, used implicitly whenever a caller doesn't pass
`block_size`) or via circular block bootstrap (`block_size>1`, e.g.
`block_size=20` as used in this session's own portfolio-comparison
scripts).

**Assessment, by the mandate's specific questions**:

- **Block length appropriate?** `block_size=20` is a project-wide
  default used in several of this session's own scripts, but is not
  visibly derived from the empirically observed cluster size — this
  session's own alpha decomposition found protective-stop clusters
  typically span 2-25 trades per cluster-day (Section 5 of
  `docs/strategy_a/STRATEGY_A_ALPHA_DECOMPOSITION.md`), so 20 is
  roughly the right ORDER OF MAGNITUDE for short-range (single-event)
  clustering, but this alignment appears coincidental/convention-
  inherited rather than deliberately calibrated against the measured
  cluster-size distribution.
- **Trade sequence dependence preserved?** Partially. Block bootstrap
  preserves LOCAL sequence (a block of 20 consecutive, exit-time-
  ordered trades stays together), which does carry SOME of a real
  cluster event's trades together into a resampled path IF the cluster
  is smaller than the block size and doesn't straddle a block boundary.
  It does NOT preserve sequence beyond the block: consecutive blocks in
  a resampled path can be stitched together from arbitrarily distant
  real time periods (the "circular" wraparound explicitly allows this).
- **Simultaneous crypto trades preserved?** **No, and this is the most
  important gap.** The bootstrap operates on a 1-D array of per-trade
  fractions; it has no explicit notion of "these N trades, across N
  different symbols, were open/losing AT THE SAME REAL MOMENT because
  of one shared shock." The exit-time ordering of the source log
  implicitly places same-event trades near each other in the sequence
  (since they tend to exit within minutes of each other, per this
  session's own 90-minute-window clustering measurement), so block
  bootstrap captures this ONLY INCIDENTALLY, not by design.
- **Regime clustering preserved?** **No, likely understated.** Bad
  REGIMES (e.g. a multi-month bear stretch) operate on a much longer
  timescale than a 20-trade block. A block-length calibrated to capture
  single-event (minutes-to-hours) clustering is very unlikely to also
  capture multi-week/multi-month regime clustering — these are two
  different scales of dependence, and only the shorter one is
  addressed by the current default.
- **Cross-symbol dependence preserved?** Only incidentally, as above —
  no explicit cross-symbol structure is modeled.
- **Conditional tail behavior?** Given the above, the bootstrap likely
  **understates** true tail risk to some degree — deep drawdowns in
  the REAL history are disproportionately produced by correlated,
  clustered events (both short-range shock clusters and longer-range
  regime stretches), and a bootstrap that only partially captures the
  shorter of these two dependence scales will generate resampled paths
  that are, on average, somewhat LESS clustered (and therefore somewhat
  less severe) than reality.

**Does this change any existing conclusion?** Not definitively
determinable without rerunning simulations (explicitly out of scope per
the mandate — "pas de simulations redondantes sans raison," and this is
Codex-owned methodology, not something to silently alter). The
DIRECTIONAL implication is that the project's `MC_P(DD>30%)<=5%`
elimination gate (used throughout Experiments 26/31/33/34/35/36/Phase A
A5) is **plausibly a bit optimistic** — true tail risk is more likely
UNDERSTATED than overstated by this methodology, not the reverse. This
is a methodological flag for Codex's attention (risk-frontier owner),
not a claim that any specific adopted risk_pct is definitively wrong.

**Recommendation** (methodological, not a rerun): if/when Codex next
revisits the risk frontier, consider (a) a longer secondary block size
(e.g. calendar-month blocks) specifically to probe regime-scale
clustering sensitivity, and (b) an explicit cross-symbol block bootstrap
(resample WHOLE calendar days across all 9 symbols simultaneously,
preserving true same-day cross-symbol co-occurrence) as a robustness
check against the current per-trade approach — both are refinements
Codex should evaluate for whether they would change the frontier, not
a demand that they be implemented. **A standalone note formalizing this
for Codex's own track has been prepared separately**:
`docs/NOTE_TO_CODEX_MONTE_CARLO_BOOTSTRAP.md`.

## 7. Data bug history (registry, by class)

| Bug | Root cause | Affected results | Fix | Regression test | Could it exist elsewhere? |
|---|---|---|---|---|---|
| **Portfolio-engine compounding bug** (Codex `C-AUDIT-001`, 2026-08-22) | `scripts/walk_forward_risk_sweep.py` family: (1) non-chronological equity realization (entry-order not exit-order), (2) registered costs computed but never deducted, (3) no one-position-per-symbol enforcement | Experiments 26, 31, 33, 34 — every multi-symbol portfolio CAGR/MaxDD/Calmar reported before 2026-08-22 (magnitude overstated ~2-3x, worse with more symbols) | `quant_bot/risk` corrected engine (Codex-owned) | Codex-owned (out of this audit's direct scope to re-verify the test suite, `tests/test_validation_risk.py` exists) | **Checked, not found elsewhere** — every portfolio-level number in this session's OWN work (Phase A, Experiments 40-42, the alpha decomposition) used the CORRECTED `quant_bot/risk.simulate_portfolio` directly, read-only, never the old broken scripts. |
| **HORIZON/LOOKAHEAD decoupling** (class) | `scripts/fast_trades.py` (and its source, `scripts/mae_mfe_analysis.py`) used to bind `HORIZON`/`LOOKAHEAD` as **module-level globals at import time**, not function parameters — a caller reassigning its own local `HORIZON` variable did not propagate | **First instance**: Experiment 30 (BTC/ETH horizon=20 test) — first run silently used the old 50-min window, caught by noticing `stop_distance` hadn't widened as expected; fixed, full rerun, REJECT conclusion stands on corrected data. **Second instance**: Experiment 33 needed "the same fix Experiment 30 needed the hard way" (per the ledger) for its own `--horizon` CLI flag. **Third/fourth instances (found this audit, 2026-08-24)**: `scripts/multi_crypto_walkforward.py` and `scripts/multi_crypto_transfer_walkforward.py` both had a `--horizon` CLI flag that reassigned only their own local `HORIZON`, never propagating to trade-building — a live recurrence of the same class. **Verified via reproduction** that the historical `SOLUSDT_transfer_horizon15/20` output files were NOT corrupted (their `close_path` lengths, 56/61 points, correctly match the intended LOOKAHEAD, meaning some other process — not the buggy code path — produced them). | This audit's own first fix used a monkey-patch (`_fast_trades_module.HORIZON = ...`). **Since superseded by a more robust upstream fix**: `scripts/fast_trades.py`'s `build_trades_with_mae_mfe_fast` now accepts `horizon`/`lookahead` as EXPLICIT keyword parameters (default `None`, falling back to `mae_mfe_analysis`'s `HORIZON` only when omitted) — eliminating the whole bug class at the source rather than requiring every caller to remember a workaround patch. Both affected files now call `build_trades_with_mae_mfe(..., horizon=HORIZON)` explicitly at every call site. This audit's monkey-patch code was cleanly superseded (no leftover dead code — verified via grep) and the audit's own regression test was updated to recognize the new canonical pattern (see next column). | `tests/test_horizon_lookahead_binding.py` (updated this audit after the upstream fix landed) — statically scans every script for the risk pattern and asserts EITHER an explicit `horizon=` kwarg at every `build_trades_with_mae_mfe(_fast)` call site (the current canonical fix) OR the older monkey-patch pattern (still accepted, functionally correct if present) — using a line-window scan rather than naive paren-matching, since nested calls (e.g. `.to_numpy()`) inside the argument list broke an earlier, simpler regex attempt (caught via self-test before trusting the tool). Currently passes. | **A genuine "search for the bug class, not just the instance" success** — any FUTURE script with the same pattern will fail this test automatically, and the test now correctly tracks the CURRENT best-practice fix rather than a stale one. |
| **`build_labels_h1` missing NaN-label guard** (Task B, found 2026-08-24) | `quant_bot/features/build_h1.py`'s `build_labels_h1` — the H1/hourly sibling of `quant_bot/features/build.py`'s `build_labels` — was missing the exact NaN-preservation guard its sibling already has (with an explicit comment acknowledging the risk: "pandas comparisons map NaN to False. Preserve the unavailable future target..."). The final `horizon_hours` rows of any close-price series have no future bar (`close.shift(-horizon)` is NaN there); a plain `(fwd > threshold).astype(float)` silently mapped that to class `0.0` instead of a correctly-excluded/missing label. | Only `scripts/h1_dedicated_model.py` and `scripts/h1_multi_asset_test.py` call this function — **verified via grep that neither is ever cited in `docs/research_plan_status.md`** (no reported/adopted experiment used this code path). **No historical result affected.** | Added the same `.where(fwd.notna())` guard already present in the sibling `build_labels`. Fixed proactively since this H1/multi-asset infrastructure could be reused for future work (e.g. if Gemini's Strategy C track needs an hourly timeframe). | `tests/test_label_nan_boundary.py` (new) — asserts both `build_labels` and `build_labels_h1` correctly return NaN (not 0.0) for the final `horizon` rows, for both long and short label directions. | Checked: `build_labels`'s sibling relationship was the only such pair found; no other H1-vs-1min function-pair mismatch was identified during this audit's review. |
| **VALIDATION-calibrated stop-distance leak** (class) | Protective stop computed from VALIDATION's own trades instead of TRAIN's — a mild self-referential leak | First found+fixed in Experiment 5 (quantified ~10% PF difference on ETH); **recurred** in Experiment 8's stress script (`get_setup_for_threshold` built trades from VALIDATION and calibrated stop on those), caught while building Experiment 11, fixed+rerun | Both instances fixed within their own experiment cards before being trusted/reported | Not independently verified by this audit whether a standing regression test exists for this specific class (not found in `tests/` during this audit's review) | **Not systematically re-checked project-wide by this audit** — flagged as an open item; the TRAIN-only-calibration discipline has been the project's stated standing rule since, and every script this session's own work touched was manually verified TRAIN-only, but no automated project-wide static check exists for this class the way the HORIZON/LOOKAHEAD one now does. **Recommended as a natural next automated-audit addition.** |
| **CEILING_MULT leverage bug** | First-pass Experiment 6 computed `leverage = formula_value * 2`, based on a mis-description (since corrected) of the registered 12.1x/9.9x values in the project's own docs | Only Experiment 6's own first-pass numbers (never previously reported elsewhere, since those scripts used hardcoded literals) | Fixed within the same experiment card | N/A (isolated, one-time doc/code mismatch) | Low risk — this was a specific numeric mis-description, not a structural pattern likely to recur. |
| **Overlapping-position bug** | An early Experiment 1 script draft iterated every filtered-mask index independently, allowing overlapping positions (inflated n) | Only Experiment 1's own first-pass numbers | Fixed by reusing the existing sequential trade builder; corrected n exactly matched the registered baseline | N/A (isolated) | Structurally the SAME class of issue as the portfolio-engine bug (position-overlap not enforced) — worth noting as the same conceptual failure mode recurring at two different points in the project's history (single-symbol level here, then multi-symbol-portfolio level in the 2026-08-22 bug), even though these are technically two separate code paths. |
| **Funding-data pagination bug** (this session, 2026-08-24) | `quant_bot/data/download_funding_oi.py` advanced pagination by a fixed +8h assumption instead of past the last returned row, silently skipping real settlement events when timing didn't align exactly | The pre-existing `BTCUSDT/ETHUSDT_funding_20190328_20260818.csv` files (used historically by Experiment 18's `funding_ma_3` feature, and this project's own step27_funding_feature.py-era work) — ~41% of real events missing | Advance by `data[-1]["fundingTime"] + 1` instead | Not yet added as an automated regression test (the fix was verified via direct re-download + audit script re-run, not a standing `tests/` entry) | **Recommended addition**: a lightweight regression test asserting the re-downloaded funding files show 100% exact-8h cadence, to catch a future pagination regression. |
| **Funding-data value-based deduplication bug** (this session, 2026-08-24) | `.drop_duplicates()` on a single-column (`fundingRate`) DataFrame dedupes by VALUE, not timestamp — collapsed 7619 genuinely distinct events to 4512 unique rate values | Same files as above | `df[~df.index.duplicated()]` (index/timestamp-based dedup) | Same as above — recommended, not yet added | **This is a distinct, GENERAL pattern worth flagging class-wide**: any `.drop_duplicates()` call on a DataFrame where the intended uniqueness key is the INDEX, not the remaining column(s), is at risk of this exact mistake. See Section 15's cross-code note. |
| **shock_breadth NaN-masking bug** (this session, 2026-08-24, Experiment 41) | `ret15_df[sym] < thresholds[sym]` on a column containing NaN (not-yet-listed symbol) silently evaluates to `False` (numpy semantics), not missing — wrongly counted not-yet-listed symbols as "active and not shocked" | Would have affected `shock_breadth`'s value only in the 2019-2020 window before all 9 symbols were listed — caught BEFORE it reached any Strategy-A-trade-population computation (Strategy A's own trades don't start until Nov 2021, by which point all 9 symbols were already listed), so **no reported Experiment 41 result was actually corrupted**, but the underlying construction code was wrong | Explicit `.notna()` masking before the comparison | `n_active_symbols` regression assertion added directly in `scripts/strategy_a/build_shock_breadth.py` (checks the count varies over time and never shows all 9 before the historically-correct date) | **Directly related to the funding-dedup bug's general pattern** (an implicit "missing means default/false" assumption baked into a comparison or dedup operation) — see Section 15. |

**Bug-class summary (not just instances)**: four genuinely distinct
CLASSES recurred more than once in this project's history: (1)
**module-level-global binding vs. local-variable override** (HORIZON/
LOOKAHEAD, 4 instances, now fixed at the source — see the corrected
entry above), (2) **implicit "missing means default" in a boolean
comparison or uniqueness operation** (shock_breadth NaN, funding dedup,
`build_labels_h1` — 3 instances, all now fixed and covered by static
scanners + regression tests, see Sections 7.1-7.2 below), (3)
**position/trade overlap not enforced at a compounding step**
(Experiment 1's early draft, then the major 2026-08-22 portfolio-engine
bug — conceptually the same failure mode recurring at two different
scales of the codebase, both now fixed), (4) **sibling-function
asymmetry** (a fix applied to one function of a near-duplicate pair —
`build_labels` vs `build_labels_h1` — not propagated to its sibling;
worth checking for again if this codebase ever grows more near-
duplicate function pairs, e.g. if Strategy C introduces its own
timeframe-specific variants of shared infrastructure).

### 7.1 Task A — STOP CALIBRATION LEAKAGE GUARD (executed 2026-08-24)

**Tooling**: `scripts/audit/scan_stop_calibration_leakage.py` — an AST-
based (not regex-fragile) static scanner for two patterns: (a) `np.
percentile`/`np.quantile`/`<series>.quantile()` calls whose data-
population argument's identifier components (split on `_`, since Python
`\b` regex boundaries do NOT separate `val` from `_` in `val_trades` —
a real gap found and fixed in the scanner itself via a synthetic self-
test before trusting its output) reference `val`/`validation`/`test`
without also referencing `train`; (b) assignments to a stop/trail/
leverage-named variable with the same signature on the RHS. A second
real scanner gap was also found and fixed: method-style `series.
quantile(p)` calls were being checked against the wrong AST node (the
quantile LEVEL, e.g. `0.90`, instead of the actual data population,
`series`) — caught by a synthetic self-test that deliberately planted a
known-bad pattern and confirmed the (first-draft) scanner missed it.

**Result**: 170 files scanned under `scripts/` and `quant_bot/`. **Zero
genuine leaks found.** All flagged occurrences (0 after fixing the
scanner's method-call gap, since the only two hits were in unrelated
files) were manually reviewed; the two historical instances documented
in the ledger (Experiments 5 and 8) were both already fixed within
their own experiment cards before being trusted, and no new instance
was found in currently-active code.

**Dynamic check added**: `tests/test_fold_boundaries_train_before_test.py`
— asserts `TRAIN_END < TEST_END` and non-overlapping TEST windows for
every fold-construction function actually used across the project
(`walk_forward_engine.build_folds`, `multi_crypto_transfer_walkforward.
build_folds`, `multi_crypto_walkforward.build_folds` in both its
standard 24/3/3 and adapted-short-history branches) — all 4 tests PASS,
confirming the project's core walk-forward machinery correctly
maintains temporal ordering and produces genuinely non-overlapping TEST
samples (directly relevant to Section 4's independence audit).

**Regression coverage added**: `tests/test_stop_calibration_leakage_scan.py`
(pins down both scanner-correctness fixes with synthetic bad/good
examples, and locks in the live codebase's current zero-genuine-leak
state) + `tests/test_fold_boundaries_train_before_test.py` (4 dynamic
tests). All pass.

**Material impact**: none — no new bug found in currently-active code
for this class.

### 7.2 Task B — NaN BOOLEAN SEMANTICS GUARD (executed 2026-08-24)

**Tooling**: `scripts/audit/scan_nan_boolean_semantics.py` — AST-based,
two-pass per function scope: (1) track variables assigned from a NaN-
producing expression (`.pct_change`/`.shift`/`.diff`/`.rolling`/
`.resample`/`merge_asof`/`.reindex`) without an accompanying guard
(`.notna`/`.dropna`/`.fillna`/`.isna`) in the same assignment; (2) flag
every comparison (`<`,`>`,`<=`,`>=`,`==`,`!=`) whose operand traces back
to a tracked risky variable, unguarded at the comparison site.
Deliberately conservative (flags even indirectly-guarded cases, e.g. a
separately-computed boolean mask combined via `&` later) to avoid false
NEGATIVES from over-trusting a superficial guard pattern — every
candidate still requires manual semantic classification, per the
mandate's explicit instruction not to blindly "fix" every NaN
comparison.

**Result**: 171 files scanned, **41 candidates found**, all manually
reviewed and classified into pattern families:

| Pattern family | Count | Correct semantics | Verdict |
|---|---|---|---|
| Entry-signal boolean AND-chains (`breakout_level`, `prior_high`/`prior_low`, `z`-score, `imb_pctile`, `entry_feats` range/vol cutoffs) | ~20 | **FALSE is correct**: NaN in an early rolling-window row means "no valid signal yet" — False correctly excludes that row from the entry set, exactly the desired behavior (not a leak, since exclusion IS the intended semantics) | OK, verified |
| Gap/session detection on the first `.diff()`/`.shift()` row (`deltas_min`, `nasdaq_baseline_test.py`/`diagnostic_bi1/bi2.py`) | 3 | **FALSE is correct**: the very first bar can't meaningfully be "a gap since the dataset start" — False (not a gap) is the right answer | OK, verified |
| Timestamp/index comparisons on a risky-tracked variable (`ret15.index < CUTOFF`, `merged["entry_time"] < CUTOFF`) | 4 | **N/A — not actually a NaN-value comparison**: these compare `.index` (timestamps), not the NaN-prone VALUES of the tracked variable — scanner false positive (root-name tracking doesn't distinguish `.index` access from value access) | OK, scanner false positive, confirmed benign |
| Already-fixed shock_breadth code (`ret15_df.loc[valid, sym] < ...`) | 1 | Already inside the `.notna()`-masked branch from this session's earlier fix | OK, confirmed correctly fixed |
| Purely descriptive/diagnostic bucketing of already-known-valid data (`decompose_trades.py`'s month/year/symbol/pnl comparisons) | 8 | Scanner over-generalized "risky" status to the whole `df` variable from an unrelated earlier assignment in the same function scope (a real scanner precision limit — it tracks by variable NAME, not by DataFrame COLUMN) — the actual compared columns (`month`, `year`, `symbol`, `pnl`) are fully-populated per-trade fields, not rolling/shift-derived | OK, scanner false positive, confirmed benign |
| Already ex-post guarded (`merged["btc_ret_15min"] < threshold` immediately followed by `.fillna(False)` on the NEXT line, outside the scanner's same-expression guard check) | 1 | Correctly guarded, just not visible to the scanner's single-expression guard detection | OK, confirmed benign |
| **`build_labels_h1` (real bug)** | — | Found via this scan prompting a manual read of the shared label-construction code, not directly flagged by the scanner itself (the function doesn't match the scanner's own tracked call-pattern signature) — **the search process itself, not just the tool, is what found this** | **REAL BUG, FIXED** (see Section 7's registry table) |

**Material impact of the one real bug**: none historically (verified via
grep — the affected function's only callers are never cited in `docs/
research_plan_status.md`); fixed proactively.

**Regression coverage added**: `tests/test_label_nan_boundary.py` (3
tests, locks in the fix and its sibling's already-correct behavior) +
`tests/test_nan_boolean_semantics_scan.py` (pins down the scanner's own
correctness via the real historical bug pattern, plus a bounded-count
guard on the live codebase's candidate set). All pass.

**Explicitly NOT done, per the mandate's own instruction**: no blanket
replacement of NaN comparisons was performed. Every one of the 41
candidates was individually classified (MISSING vs FALSE vs EXCLUDE ROW
vs NOT ACTIVE) before any conclusion was drawn, and only the one
genuinely wrong case was changed.

## 8. Forward-paper falsification criteria (pre-registered, before any forward results are examined)

Per the mandate's explicit instruction not to choose thresholds after
seeing results, these are derived from the project's OWN existing
historical evidence and standard uncertainty reasoning, not arbitrary
round numbers:

- **PF**: the walk-forward OOS population's own aggregate PF is 1.350
  (n=2355, current frozen baseline). A reasonable short-run forward-
  paper sample (say, the first 100-200 live-equivalent trades) will
  have wide sampling uncertainty around this — **falsification
  trigger: forward PF's 95%-CI lower bound (via the same bootstrap
  methodology, Section 6 caveats noted) excludes 1.0 in the ADVERSE
  direction for two consecutive non-overlapping evaluation windows**,
  not a single bad window (given Section 6's own finding that short-
  range clustering is real and expected, one bad window alone is not
  sufficient evidence).
- **Edge retention**: defined as forward realized PF (or expectancy)
  divided by the walk-forward OOS PF/expectancy for the SAME symbol mix
  and comparable market regime. **Falsification trigger: edge retention
  <50% sustained over >=100 trades**, chosen because this project's own
  historical WF-vs-fixed-split divergence pattern (Experiments 12, 21 —
  both cases where a real WF check revealed a fixed-split-only
  conclusion was overstated) demonstrates that SOME degradation between
  research-stage and stricter-evaluation-stage performance is normal
  and expected; a 50%+ collapse would be a qualitatively different,
  alarming signal beyond that already-observed pattern.
- **Execution drag**: forward paper's realized cost/slippage per trade
  vs. the registered `ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST` assumption
  used throughout every backtest. **Falsification trigger: realized
  execution drag exceeds 2x the modeled assumption sustained over
  >=50 trades** (2x chosen to match the project's own standard
  "2x slippage" stress-test scenario already used throughout Strategy
  A's stress battery — i.e. using an ALREADY-established project
  convention rather than inventing a new number).
- **MaxDD**: the frozen baseline's own backtested MaxDD is -14.43% at
  1.5% risk, with a Monte Carlo P(DD>30%)=3.1% (noting Section 6's
  caveat that this may be somewhat optimistic). **Falsification
  trigger: forward paper MaxDD exceeds -30% at any point**, OR forward
  paper reaches a materially worse drawdown than the WORST individual
  backtested walk-forward fold's own within-fold drawdown (a directly
  comparable, historically-grounded reference point rather than an
  arbitrary round number).
- **Protective-stop clustering**: per the alpha decomposition (Section
  5), roughly half of historical protective-stop-loss dollars occurred
  in cross-symbol same-day clusters. **Falsification trigger: forward
  paper shows a SINGLE cluster episode (3+ symbols stopped within a
  90-minute window, matching the historical definition) that alone
  produces a loss exceeding 10% of account equity** — a materially
  worse single-episode impact than any historical cluster produced
  (the worst historical cluster day, per the decomposition, was well
  below this threshold relative to account size at the time).
- **Signal divergence**: forward paper's live entry signals should
  match what an offline replay of the SAME frozen model/features/
  thresholds on the same market data would have produced.
  **Falsification trigger: signal match rate <95%** on overlapping,
  independently-replayable periods — this is an EXECUTION/INFRASTRUCTURE
  correctness check, not a market-performance one, and any divergence
  at all deserves investigation; 95% is a pragmatic operational
  tolerance (data feed timing jitter, not a market-quality bar).

**Explicit rule, per the mandate**: none of the above thresholds may be
adjusted AFTER seeing forward-paper results. If a genuinely new
falsification dimension is identified once real forward data exists, it
must be added as a NEW criterion with its own stated rationale, not a
retroactive edit to an existing one.

## 9. Strategy C future audit protocol (Gemini, no artifacts yet)

To be applied in full once Strategy C produces any result/artifact.
Nothing executed yet — protocol only, per the mandate's explicit
instruction not to act before artifacts exist.

**Checklist** (per the mandate's own Phase 8 list, expanded with
project-specific context):
- **DATA**: source, coverage, known gaps — apply the SAME rigor as this
  project's own funding-data audit (Section 7) found necessary; assume
  nothing is clean until independently verified.
- **TIMESTAMPS**: open-time vs close-time convention (this project's
  own established convention: Binance klines are OPEN-time indexed,
  confirmed via `quant_bot/data/download_klines.py`'s raw column
  order — verify whether Gemini's data source uses the same or a
  different convention, and whether Strategy C's code assumes the
  right one).
- **MARKET SESSION / DST**: if Strategy C touches non-24/7 markets
  (equities, futures with session structure), apply the SAME care this
  session's own B_INDEX work required (the NY-open DST-aware conversion
  bug found and fixed in that work is a directly relevant precedent —
  Section 7's bug registry should be extended with it if/when
  cross-referenced).
- **LOOKAHEAD**: independently verify no future bar is used, ideally via
  the SAME "independent manual recompute" sanity-check pattern used
  throughout this project's own Strategy B diagnostics (compare a
  vectorized computation against a hand-rolled loop on a small sample).
- **QUOTE/TRADE ALIGNMENT**: if microstructure data (bid/ask, trade
  prints) is used, verify quotes and trades are correctly time-aligned,
  not just both "roughly the same day."
- **SPREAD / EXECUTABLE PRICE**: verify Strategy C's assumed fill price
  is actually achievable (not a mid-price fantasy) — a classic
  microstructure-strategy failure mode explicitly named in the
  mandate.
- **TARGET OVERLAP**: check for the same label-overlap concern flagged
  as an open gap in Section 4 of this audit.
- **PURGING**: if Strategy C uses any ML component, verify a
  purge/embargo exists between TRAIN and TEST if labels can overlap the
  boundary — this project's own history (Section 4) has never
  implemented this explicitly, so don't assume Gemini's does either;
  verify directly.
- **BENCHMARK**: verify against a credible null (Section 10), not just
  "beats zero" or "beats buy-and-hold" without considering regime.
- **COSTS / SLIPPAGE**: verify realistic, ideally matching or exceeding
  this project's own stress-tested assumptions (2x slippage, gap,
  latency scenarios).
- **MULTIPLE TESTING / PARAMETER SEARCH**: apply Section 3's own
  framework — ask how many variants were tried before the reported one,
  and whether the acceptance bar was raised accordingly.
- **"Was the edge visible BEFORE ML?"**: the mandate's own explicit,
  final, and most important question for any microstructure strategy —
  verify a SIMPLE, rule-based version of the same hypothesis shows
  signal before trusting any ML-model version of it. This directly
  mirrors this project's OWN successful discipline in Strategy B (every
  sub-family started with a simple rule-based cheap screen before any
  model complexity was ever considered, and none of them needed to
  reach the ML stage because the rule-based version was falsified
  first) — the SAME discipline should be demanded of Strategy C.

## 10. Strategy C null models (protocol, not yet applied)

Per the mandate: do not let a microstructure strategy profit from the
open, intraday drift, market trend, or a bid/ask convention bug while
appearing to have found real information-content edge. Required null
comparisons before crediting any Strategy C result:
- **Same-time-of-day random events**: does the strategy's edge exist
  specifically at its claimed trigger, or would ANY random entry at the
  same time-of-day distribution show similar performance?
- **Same-volatility-regime random entries**: does the edge exist beyond
  what's explained by entering during elevated volatility generally
  (the SAME check this project's own B1-B8 Strategy B family
  implicitly required and often failed against — e.g. B1's dead-signal
  finding was exactly "elevated volatility + breakout" showing no edge
  beyond chance)?
- **Randomized direction**: does a LONG-only version beat a version
  with entry direction randomized (keeping the same trigger timing)?
- **Permuted imbalance, preserved intraday structure**: for order-flow/
  imbalance-based signals specifically, shuffle the imbalance VALUES
  while preserving the intraday volume/volatility shape — tests whether
  the specific imbalance INFORMATION matters, or just its general
  presence/timing.

## 11. Independent reproduction policy (formalized)

```
RESEARCH AGENT RESULT
  ↓
FREEZE ARTIFACTS (exact script + exact output CSV/trade population,
  timestamped, never silently overwritten)
  ↓
INDEPENDENT REPRODUCTION (by an agent who did NOT write the original
  implementation — Claude reproducing Gemini's Strategy C without
  reusing Gemini's own code, or preparing a clean reproduction spec
  for Codex if Claude cannot reproduce independently for a legitimate
  reason, e.g. missing proprietary data access)
  ↓
DIFFERENCE REPORT (exact numeric deltas, not just "looks similar" —
  this project's own precedent: Codex's C-RISK-002 raw-data
  reconstruction matched 1,262 reference trades field-for-field with
  ZERO numeric deltas, including matching SHA-256 hashes on six
  per-asset CSVs — this is the bar an independent reproduction should
  aim for, not an approximate match)
  ↓
ONLY THEN PROMOTION
```

If Gemini reports Strategy C profitable, Gemini must NOT be the sole
validator, per the mandate's explicit instruction. This audit commits
to attempting independent reproduction using a fresh implementation
(not importing Gemini's code) whenever Strategy C artifacts exist and
the underlying data is accessible to this session; if genuinely
infeasible (e.g. a data source only Gemini has access to), this audit
will instead prepare a precise reproduction SPEC (exact hypothesis,
exact data requirements, exact expected numbers) for Codex to execute
independently.

## 12. Promotion pipeline (formalized states)

```
IDEA -> PRE_REGISTERED -> CHEAP_SCREEN -> CANDIDATE ->
WALK_FORWARD_VALIDATED -> STRESS_VALIDATED -> INDEPENDENTLY_REPRODUCED ->
FORWARD_PAPER -> HOLDOUT_READY -> MICRO_LIVE_CANDIDATE
```

No strategy may skip a state. Mapping the project's OWN history onto
this pipeline retroactively (illustrative, not a re-litigation):
Strategy A's current baseline sits at **FORWARD_PAPER** (Codex is
actively running it there; it has NOT reached HOLDOUT_READY — no
HOLDOUT criteria have been defined or met, matching Section 8's
falsification criteria being pre-registered for exactly this purpose).
Strategy B's 11 sub-families each terminated at CHEAP_SCREEN or
WALK_FORWARD_VALIDATED with a REJECT, never reaching CANDIDATE. Strategy
C, per Section 9, has not yet reached even IDEA-with-artifacts from this
audit's perspective — nothing to place on the pipeline yet.

## 13. HOLDOUT governance protocol

**Conditions that must be met before HOLDOUT is ever opened** (for
Strategy A, since it's the only track currently near that stage):
1. Forward paper has run long enough to independently validate (not
   replace) the walk-forward evidence — Section 8's falsification
   criteria must have been checked and NOT triggered over a
   pre-specified minimum window (this audit recommends: not less than
   the shortest individual walk-forward TEST fold's own duration, 3
   months, as a floor — matching an already-established project
   convention rather than inventing a new number).
2. No pending, unresolved audit findings from this document (Sections
   4, 6, 7's "recommended, not yet added" items) that could plausibly
   change the interpretation of a HOLDOUT result.
3. Explicit, documented sign-off from the user (not an agent decision)
   — matching the project's own standing rule
   (`docs/AGENT_COORDINATION.md`: "HOLDOUT remains forbidden unless the
   user explicitly authorizes a separately preregistered final run").

**Metrics to be examined when HOLDOUT is opened** (pre-specified NOW,
per the mandate's explicit "prepare this before it's needed"
instruction): the SAME metric set as every walk-forward fold
throughout this project's history (n_trades, PF, expectancy, CAGR,
MaxDD, Calmar, forced liquidations) PLUS the Section 8 falsification
criteria, computed ONCE, with no re-computation after seeing a
disappointing first look.

**Decisions possible after HOLDOUT is opened**: PASS (matches
walk-forward-implied expectations within Section 8's stated
tolerances) or FAIL (does not) — a binary, pre-committed outcome, not a
spectrum requiring further judgment calls made AFTER seeing the number.

**What is FORBIDDEN after HOLDOUT is opened** (the mandate's own
explicit rule, restated as a hard governance line): **if HOLDOUT FAILS,
there is no retuning on HOLDOUT.** A HOLDOUT failure means returning to
pre-HOLDOUT research (new hypotheses, tested again on TRAIN/VALIDATION/
walk-forward) — HOLDOUT itself is never used as a new optimization
target, and once opened for a given strategy version, it cannot be
"re-locked" and reused for a materially different version of that same
strategy without an explicit, separately-justified decision that the
new version is different enough to warrant a fresh HOLDOUT question (a
judgment call reserved for the user, not an agent).

## 14. What would falsify Strategy A (consolidated from Section 8)

Summarized here as the single most important practical answer this
audit can give: Strategy A's currently-held belief ("a real, if modest
and concentrated, mean-reversion edge exists in crypto dip-buying, most
of it produced by asymmetric exit mechanics rather than a large average
per-trade edge") would be falsified by ANY of: (a) forward PF's
confidence interval sustainedly excluding 1.0 on the adverse side, (b)
edge retention collapsing below 50% versus backtested expectancy, (c)
execution drag exceeding 2x modeled assumptions, (d) a MaxDD breach
beyond the worst historical fold's own drawdown or -30% outright, (e) a
single cluster episode losing >10% of equity, or (f) signal-match rate
falling below 95% (an infrastructure-correctness falsification, not a
market one). None of these have been evaluated yet — forward paper is
too new (Section 13's own stated position).

## 15. What evidence is still missing

- **No project-wide automated check for the "VALIDATION-calibrated stop
  leak" bug class** (Section 7) — recommended as a natural next
  addition, mirroring the HORIZON/LOOKAHEAD static test added this
  audit.
- **No project-wide automated check for the "implicit missing-means-
  default" class** (NaN-comparison, value-based dedup) — the shock_
  breadth and funding-dedup bugs were each caught individually, not by
  a general static scanner; a grep-based lint rule (flag any
  `.drop_duplicates()` call not preceded by a comment justifying it's
  not index-based, and any `<`/`>` comparison on a column immediately
  after a `.pct_change()`/`.shift()` without a preceding `.notna()`
  check) would be a cheap, high-value addition.
- **Label-overlap/purging** (Section 4) has never been explicitly
  addressed anywhere in this project's history — worth a dedicated,
  small investigation (not a full rebuild) into whether `fast_trades`'s
  pointer-jump mitigation is sufficient or whether a small but real
  leakage margin remains.
- **No independent, non-Codex-authored re-verification of the
  Monte-Carlo/bootstrap methodology's actual sensitivity** — Section
  6 is a methodological READ, not a rerun; whether block_size or a
  cross-symbol block bootstrap would actually MOVE any adopted risk_pct
  decision is unknown until someone (most naturally Codex, who owns
  this engine) tests it.
- **Forward paper track record** — too new to have produced any of the
  Section 8 falsification-relevant evidence yet.
- **Strategy C** — no artifacts exist; Sections 9-10's protocol is
  ready but unexercised.
- **No formal project-wide multiple-testing correction** was ever
  applied (nor does this audit recommend inventing an artificial one —
  Section 3's qualitative/category-based assessment is the honest
  alternative given the underlying experiments weren't designed for a
  single global p-value framework).

## 16. Recommended scientific next action

Given the above, and per the mandate's own explicit instruction not to
launch a new strategy track: the highest-value, lowest-cost next action
is **NOT** a new experiment — it is closing the two concrete,
already-identified gaps from Section 15 that are cheap and don't touch
any active baseline:
1. Add a static regression test for the "VALIDATION-calibrated stop
   leak" bug class (mirrors the HORIZON/LOOKAHEAD test added this
   audit — same spirit, different pattern).
2. Add a lightweight lint-style check for the "implicit missing-means-
   default" class (NaN comparisons, value-based `.drop_duplicates()`).

Beyond that, this audit's role is now to **wait**: for forward-paper
data to accumulate (to evaluate against Section 8's pre-registered
criteria), and for Strategy C artifacts to exist (to apply Sections
9-10's protocol). No further Strategy A, B, or C research should be
launched by this track in the meantime, per the mandate's explicit
scope.

## 17. Final status

```
RED_TEAM_ACTIVE_WORK = COMPLETE
WAITING_FOR_FORWARD_OR_STRATEGY_C_ARTIFACTS = TRUE
```

**Task A (STOP CALIBRATION LEAKAGE GUARD)**: COMPLETE. 170 files
scanned, 0 genuine leaks found in currently-active code (both historical
instances, Experiments 5/8, were already fixed within their own
experiment cards). 2 real gaps found and fixed IN THE SCANNER ITSELF
before trusting its output (snake_case identifier matching, method-
style `.quantile()` call-site detection). New tests: `tests/
test_stop_calibration_leakage_scan.py`,
`tests/test_fold_boundaries_train_before_test.py`. All pass.

**Task B (NaN BOOLEAN SEMANTICS GUARD)**: COMPLETE. 171 files scanned,
41 candidates found and individually classified (no blanket fix
applied). **1 real bug found and fixed**: `quant_bot/features/
build_h1.py`'s `build_labels_h1` was missing a NaN-label guard its
sibling function already had — verified zero historical impact (never
cited in any reported experiment), fixed proactively. New tests:
`tests/test_label_nan_boundary.py`, `tests/
test_nan_boolean_semantics_scan.py`. All pass.

**Monte Carlo note**: prepared and delivered to Codex as a standalone
document (`docs/NOTE_TO_CODEX_MONTE_CARLO_BOOTSTRAP.md`) — informational
only, no simulation rerun, no risk_pct decision touched.

**No new research launched.** No Strategy D. No new Strategy A
features/thresholds/cryptos. No new Strategy B variants. No new Monte
Carlo runs beyond reading Codex's existing methodology. Per the
mandate, this track now goes idle until one of the two reactivation
events:

- **EVENT 1 — Codex forward-paper results**: once sufficient forward
  data exists, audit signal matching, execution drag, edge retention,
  PF/expectancy uncertainty, protective-stop behavior, drawdown
  clustering, risk-cap behavior, and historical-vs-forward distribution
  differences, against the Section 8 falsification criteria — already
  pre-registered, not to be changed after seeing results.
- **EVENT 2 — Gemini Strategy C artifacts**: once produced, run the
  Section 9/10 audit protocol (data/timestamps/session/DST/quote-trade
  alignment/executable prices/spread/slippage/target overlap/purging/
  null models/multiple testing/parameter search/pre-ML signal
  existence) BEFORE any promotion; attempt independent reproduction
  per Section 11 rather than accepting Gemini's own conclusion at face
  value.

HOLDOUT remains LOCKED throughout; never accessed at any point in this
audit.

---

*Audit compiled and finalized 2026-08-24. Scripts:
`scripts/strategy_a/experiment42_*.py` (temporal validation work this
audit builds on), `scripts/audit/scan_stop_calibration_leakage.py`,
`scripts/audit/scan_nan_boolean_semantics.py` (new static scanners).
New regression tests: `tests/test_horizon_lookahead_binding.py`,
`tests/test_stop_calibration_leakage_scan.py`,
`tests/test_fold_boundaries_train_before_test.py`,
`tests/test_label_nan_boundary.py`,
`tests/test_nan_boolean_semantics_scan.py` — all pass. Fixes applied:
`scripts/multi_crypto_walkforward.py` / `scripts/
multi_crypto_transfer_walkforward.py` (HORIZON/LOOKAHEAD, superseded by
a cleaner upstream fix since this audit began — verified, not
reverted), `quant_bot/features/build_h1.py` (NaN-label guard, zero
historical impact, fixed proactively). No changes to the frozen
Strategy A baseline, no Codex-owned file modified, HOLDOUT never
accessed.*
