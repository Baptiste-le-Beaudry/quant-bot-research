# Strategy Index — instant "which strategy is this result from?" lookup

This file exists solely so that, at any point in the future, a single
glance answers: **does this result belong to Strategy A or Strategy B?**
Created 2026-08-23 per the user's explicit mandate to keep the two
strategies completely separated at every level (concept, code, config,
results, docs, experiments, trade files, metrics, KEEP/REJECT decisions).

## STRATEGY_ID = A — mean-reversion / dip-buying

- **Concept**: buy short-term oversold dips in elevated volatility,
  trailing-stop exit. The ONLY strategy family that has existed in this
  project until 2026-08-23.
- **Status**: FIXED BASELINE ADOPTED (2026-08-25), frozen for independent
  forward paper. OLD is SUPERSEDED; FIXED is the CURRENT RESEARCH / FORWARD
  PAPER BASELINE. Signal logic remains threshold=0.70 with the mandatory
  entry filter, dynamic leverage and trailing exit. Risk=1.5%/trade,
  open-risk cap=13.5%, gross cap=3x, XRP stop=p80, LINK stop=p95 and
  `live_enabled=false`. No real order is authorized. Critical limitation:
  combined 3x-slippage + 1-minute-latency + 25bp-stop-gap stress has CAGR
  -6.32% and PF 0.961. Current evidence is under
  `docs/forward_paper/fixed_validation_20260825/`.
- **All research history**: `docs/research_plan_status.md` (every
  experiment card in that file — Experiments 1-36 — is Strategy A,
  whether or not it says so explicitly, since Strategy B didn't exist
  yet when they were written).
- **Current frozen portfolio / numbers**: see `docs/research_plan_status
  .md`'s "Current position" section (top of file) for the latest pointer
  — as of Experiments 35/36 (2026-08-23), the reference trade population
  is `docs/multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv`.
- **Scripts**: everything under `scripts/` with names like
  `multi_crypto_*`, `walk_forward_*`, `step*` — all Strategy A.
- **Trade/result file naming**: no special prefix (this predates the A/B
  split) — e.g. `multi_crypto_wf_XRPUSDT_trades.csv`,
  `walk_forward_v3_trades_export.csv`.

## STRATEGY_ID = B — momentum / breakout / trend-continuation (candidate)

- **Concept**: TBD in detail in `docs/strategy_b/STRATEGY_B_SPEC.md`
  (pre-registered BEFORE any optimization, per the user's mandate) —
  initial direction is trend-continuation after a significant breakout,
  the structural opposite of Strategy A's mean-reversion premise.
- **Status**: under development / early validation. NOT adopted. May be
  REJECTED at any gate (cheap screen, walk-forward, stress,
  generalization, correlation, portfolio) — a clean, well-documented
  REJECT is an acceptable and expected possible outcome, not a failure
  of this work.
- **All research/results**: `docs/strategy_b/` directory exclusively.
  `docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md` is the experiment-card
  log (same Hypothesis/Method/Results/Conclusion/Keep-Reject-Investigate
  discipline as `research_plan_status.md`, but scoped to Strategy B
  only).
- **Scripts**: everything under `scripts/strategy_b/` (new subdirectory).
- **Trade/result file naming convention (MANDATORY)**: every file must
  start with `strategy_b_` — e.g. `strategy_b_btc_walkforward.csv`,
  `strategy_b_btc_trades.csv`. NEVER a generic name like
  `walkforward_new.csv`.
- Every experiment card in `docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md`
  explicitly states `STRATEGY_ID = B` at the top.

## STRATEGY_ID = B_FUNDING — funding-rate crowded-long/short mean-reversion (crypto)

- Own dedicated directory `docs/strategy_b/funding/` (spec + research
  log) and `scripts/strategy_b/funding/`. Never mixed with Strategy A,
  Strategy B (momentum/breakout), or B_ROTATION.
- **Status**: CLOSED, REJECT (2026-08-24). Two economically distinct
  hypotheses tested (instantaneous extreme, persistent 24h-averaged
  extreme funding), both REJECT on BTC and ETH. Found/fixed two
  data-integrity bugs in `quant_bot/data/download_funding_oi.py` along
  the way (~41% of funding history was being silently dropped) — that
  fix is a lasting, reusable infrastructure improvement independent of
  this strategy's own REJECT outcome.
- See `docs/strategy_b/funding/STRATEGY_B_FUNDING_RESEARCH_LOG.md`.

## STRATEGY_ID = B_ROTATION — cross-sectional momentum/mean-reversion (crypto basket)

- Own dedicated directory `docs/strategy_b/rotation/` and
  `scripts/strategy_b/rotation/`. Never mixed with any other strategy.
- **Status**: CLOSED, REJECT (2026-08-24). Both selection directions
  (top-2 momentum, bottom-2 laggard) dominated by a trivial
  equal-weight-basket null baseline on both return and MaxDD.
- See `docs/strategy_b/rotation/STRATEGY_B_ROTATION_RESEARCH_LOG.md`.

## STRATEGY_ID = B_INDEX — momentum/breakout/trend-continuation (Nasdaq 100 / S&P 500)

- **Concept**: a FRESH economic hypothesis designed specifically for
  index CFDs (Dukascopy USATECH.IDX-USD / USA500.IDX-USD), NOT a
  copy-paste of the rejected crypto breakout parameters — trend regime
  confirmation + significant range breakout + volatility confirmation
  → continuation, at a longer horizon (15min-1h candidates, tested via
  forward-drift diagnostic before commitment) than crypto's 10min. See
  `docs/strategy_b/index/STRATEGY_B_INDEX_SPEC.md` for the full
  pre-registration.
- **Why this is a different question from Experiment 32**
  (`docs/research_plan_status.md`): Experiment 32 tested whether
  Strategy A's CRYPTO mean-reversion logic, applied unchanged, works on
  Nasdaq/SP500/EURUSD — it does not (clean PF<1 on all three). B_INDEX
  tests a DIFFERENT, freshly-designed momentum/breakout hypothesis,
  motivated by indices' own market structure (institutional flow,
  session effects, structural long-term drift) — a genuinely new
  question, not a re-run of Experiment 32 nor of the rejected crypto
  Strategy B breakout family.
- Data already downloaded and validated: `data/indices/NASDAQ100_1m.csv`
  (4,187,584 bars, 2011-09-19 -> 2026-08-18),
  `data/indices/SP500_1m.csv`. Sequence: Nasdaq cheap screen -> MFE/MAE
  forward-drift check -> (if drift exists) real walk-forward -> apply
  the SAME frozen rule to S&P 500 as an independent generalization test
  -> stress -> `Corr(PnL_A_crypto, PnL_B_INDEX)`.
- Own dedicated directory `docs/strategy_b/index/` and
  `scripts/strategy_b/index/`.
- **Status**: in progress, registered 2026-08-24.

## Combined A+B portfolio work (once/if Strategy B clears its gates)

- Lives in `docs/strategy_b/` too (e.g. `strategy_b_a_plus_b_portfolio_*`),
  clearly labeled, since it only exists BECAUSE of Strategy B's
  development — never silently merged into Strategy A's own files/history.

## HOLDOUT

Locked for BOTH strategies, at every stage, no exceptions. See
`docs/research_plan_status.md`'s HOLDOUT sections and
`quant_bot/data/splits.py` (Codex-owned canonical guard) for the
per-symbol boundaries.
