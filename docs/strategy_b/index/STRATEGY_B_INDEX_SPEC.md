# Strategy B_INDEX — Pre-Registration Spec

**STRATEGY_ID = B_INDEX**

A structurally distinct sub-family of Strategy B, kept separate from
every crypto sub-family (momentum/breakout B1-B8, funding BF1-BF2,
rotation BR1-BR2 — all REJECT) and from Strategy A at every level: own
spec file, own research log, own scripts directory
(`scripts/strategy_b/index/`). User-directed 2026-08-24, after all
crypto Strategy B sub-families closed. See `docs/STRATEGY_INDEX.md` for
the full A/B/B_FUNDING/B_ROTATION/B_INDEX separation.

## Why this is a genuinely new question, not a re-run

Two prior, DIFFERENT questions already have answers in this project and
are explicitly NOT what this spec re-tests:
1. **Experiment 32** (`docs/research_plan_status.md`): does Strategy
   A's crypto mean-reversion logic, applied UNCHANGED (same model,
   features, horizon=10min, threshold=0.70, trailing exit), show any
   edge on Nasdaq100/SP500/EURUSD? **Answer: no — clean, well-powered
   PF<1 on all three**, even after 3 follow-up fixes (ATR-scaled
   trailing, gap exclusion, percentile-relative volatility feature).
   This established that CRYPTO mean-reversion doesn't trivially
   transfer to indices — it says nothing about a strategy actually
   DESIGNED for indices.
2. **The crypto Strategy B momentum/breakout family** (B1-B8, this
   project's `docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md`): tested
   breakout+volatility+volume continuation on BTC/ETH at 1-15min
   resolution — REJECTED, with a mechanistic diagnostic showing
   near-zero net drift after breakout on those specific markets at
   those specific timeframes. This says nothing about whether the SAME
   general concept (breakout + trend confirmation → continuation) has
   a real economic basis on indices, where the underlying market
   structure (institutional flow, session effects, macro-news
   reactions, structural long-term upward drift) is fundamentally
   different from 24/7 crypto.

B_INDEX tests neither of the above — it is a fresh hypothesis, with
fresh (not copy-pasted) parameters, chosen because index market
structure has a plausible economic mechanism for trend-continuation
that crypto's tested breakout concept lacked.

## Economic hypothesis

Nasdaq 100 / S&P 500 exhibit intraday/intersession trending behavior
driven by institutional order flow, macro-news reactions, and a
structural long-term upward drift — mechanisms largely absent or much
weaker in 24/7 crypto. The hypothesis: **a breakout of a significant
recent range, confirmed by genuine volatility expansion, occurring
WITHIN an established directional trend regime, tends to continue** —
distinct from the rejected crypto version specifically because the
TREND REGIME CONFIRMATION is new (the crypto version had no regime
filter beyond the local vol-expansion condition, and its own B4 variant
that added a trend gate via `hurst_120` still failed — here the
regime concept is different: a structural, longer-horizon directional
filter appropriate to indices' own known institutional-flow dynamics,
not `hurst_120`, which is a statistical measure with no special claim
to index market structure).

## Data / universe

- **Nasdaq 100 first** (Dukascopy `USATECH.IDX-USD`,
  `data/indices/NASDAQ100_1m.csv`, 4,187,584 bars, 2011-09-19 ->
  2026-08-18 — already downloaded and validated: no NaN, no high<low,
  no close-outside-range, no duplicate timestamps, per
  `docs/research_plan_status.md`'s Experiment 32 card).
- **S&P 500 second**, as an independent generalization test (Dukascopy
  `USA500.IDX-USD`, `data/indices/SP500_1m.csv`) — the SAME frozen rule
  (no re-tuning) applied unchanged, exactly mirroring how this
  project's own crypto multi-symbol expansion always tests a frozen
  rule on the next symbol before ever adapting it.
- Split: 60/20/20 TRAIN/VALIDATION/HOLDOUT, positional (matches
  `scripts/nasdaq_baseline_test.py`'s established, already-used
  convention for this exact dataset). HOLDOUT (last 20%) is never
  loaded, scored, or tuned against.
- **Known data-quality artifact** (already documented in Experiment
  32): Dukascopy's Nasdaq CFD data has a genuine ~112min daily closure
  (22:07-00:00 UTC). Bars within a configurable window after any gap
  >10min are EXCLUDED from entries (reusing
  `nasdaq_baseline_test.py`'s `post_gap_mask` concept) — this is a
  DATA-HYGIENE fix, not alpha, applied identically regardless of
  outcome.
- Dukascopy's aggregated OHLCV has no buy/sell volume split;
  `taker_buy_volume`/`taker_sell_volume` are set to `volume/2` (neutral,
  makes `taker_imbalance_20` a constant/uninformative feature rather
  than crashing) — same established accommodation as Experiment 32,
  not a new assumption.

## Entry conditions (simplest possible version, no ML, no grid search)

At bar `t` (1-minute resolution, all conditions causal/backward-looking):
1. **Trend regime**: `dist_ema200_atr[t] > 0` — price above its own
   200-period EMA, ATR-normalized distance already computed by
   `quant_bot/features/build.py` (equivalent to "price above EMA200",
   derived from an existing leak-free feature, not a new computation).
2. **Range breakout**: `close[t] > rolling_max(high, 60)[t-1]` — same
   structural breakout DEFINITION as the crypto family (a well-tested,
   leak-free mechanism), applied to a fresh hypothesis, not reusing the
   crypto CONCLUSION.
3. **Volatility confirmation**: `realized_vol_ratio[t] > 1.5` (already-
   existing feature).
4. **Data hygiene**: excluded if within `POST_GAP_BARS` (60, i.e. 1h)
   of a session gap >10min.

No session-time-of-day filter in this first pass (deferred as a
possible follow-up hypothesis if the base version shows promise, not
bundled in now, per "one hypothesis at a time").

## Step-by-step protocol (fixed BEFORE looking at any result)

1. **DATA AUDIT**: light re-validation of NASDAQ100/SP500 files
   (already validated per Experiment 32, re-confirmed here for this
   specific pipeline).
2. **LOGIC AUDIT**: independent manual recompute of the breakout level
   and gap-mask on a sample of real signals (same discipline as every
   prior sub-family).
3. **MFE/MAE forward-drift diagnostic FIRST** (before any exit-mechanics
   commitment, per the user's explicit sequencing): for Nasdaq
   VALIDATION-split entries, compute the RAW forward path (no exit
   rule) at three candidate horizons (15min/30min/60min) and report
   mean/median MFE, MAE, and raw drift at each. **If drift is
   approximately zero (or negative) at ALL three horizons: REJECT
   immediately** — no walk-forward, no exit-mechanics engineering, no
   parameter search to rescue it (mirrors exactly how the crypto B4
   diagnostic was used, but run proactively here instead of as a
   post-hoc explanation).
4. **If drift is genuinely positive at some horizon**: build TRAIN-
   derived exit mechanics (same trailing-stop convention as every other
   sub-family, calibrated on Nasdaq's own TRAIN population) at that
   horizon, run a real walk-forward (expanding TRAIN / fixed TEST
   folds, adapted to this market's own available history length).
5. **Apply the SAME frozen rule (identical thresholds, no re-tuning) to
   S&P 500** as an independent generalization test.
6. **Stress test**: standard fee/slippage/gap/latency battery.
7. **Correlation**: `Corr(PnL_A_crypto, PnL_B_INDEX)` — daily/weekly,
   and B_INDEX's performance during Strategy A crypto's historical
   drawdown periods. This is explicitly flagged by the user as
   potentially the single most valuable outcome of this whole
   direction, even if B_INDEX's own standalone numbers are modest — a
   genuinely low-correlation, real-if-modest edge could be worth more
   to the overall portfolio than another crypto strategy correlated
   with Strategy A.

## Rejection criteria (fixed BEFORE looking at any result)

- **Diagnostic stage**: REJECT if forward drift is ~zero or negative at
  all three tested horizons (15/30/60min), on Nasdaq VALIDATION data.
- **Walk-forward stage** (if diagnostic survives): reject if median PF
  <= 1, or the result depends on a single dominant fold.
- **Generalization stage**: if the frozen rule fails outright on S&P
  500 despite passing on Nasdaq, this is reported honestly as
  "Nasdaq-specific, does not generalize even within US equity indices"
  — not a reason to re-tune for S&P 500 (defeats the point of the
  generalization test).
- **Forced liquidations**: any forced liquidation under the registered
  dynamic-leverage sizing is disqualifying, same as every other
  sub-family.
- **Stress test**: must not collapse catastrophically under the
  standard combined-worst-case scenario.
- **Correlation gate**: even a walk-forward-confirmed edge is only
  interesting for portfolio purposes if genuinely low-correlation with
  Strategy A crypto is CONFIRMED, not assumed from the different-market
  argument alone.

If the simple version REJECTs clearly at the diagnostic stage: per the
same discipline as every other sub-family, at most a couple of
economically distinct pre-registered follow-ups (e.g., adding a
session-time filter, or testing SHORT continuation during downtrend
regimes), not a parameter search.

## HOLDOUT policy

Identical to every other strategy in this project: completely locked,
never loaded, scored, or tuned against.

---

## REVISION 1 (2026-08-24) — BI2: classic opening-range breakout (ORB)

Experiment BI1 (any-time breakout + trend regime + vol confirmation)
REJECTED at the diagnostic stage: drift ~zero to slightly negative at
15/30/60min, ~50% win rate at every horizon, n=3468 (see
`STRATEGY_B_INDEX_RESEARCH_LOG.md`). No walk-forward was built.

**New economic angle**: rather than a generic any-time breakout, test
the CLASSIC opening-range-breakout (ORB) structure that specifically
targets the US market-open mechanism (institutional order flow
concentrating in the first minutes of the session, price discovery
after the ~112min daily closure) — a well-known, economically distinct
equity/futures trading concept, not a parameter tweak of BI1's rolling
60-bar lookback.

**Entry (session-specific, replacing BI1's rolling breakout entirely)**:
1. Identify each session's start as the bar immediately after a >10min
   gap (reusing the already-validated gap-detection logic — this
   directly identifies the post-112min-closure reopen each day).
2. Define the **opening range** as `[min(low), max(high)]` over the
   first `OR_MINUTES=30` minutes of that session.
3. **Entry window**: the following `BREAKOUT_WINDOW=120` minutes (2h)
   after the opening range closes.
4. **Signal**: the FIRST bar in the entry window where
   `close > opening_range_high` AND `dist_ema200_atr[t] > 0` (same
   trend-regime filter as BI1, reused as shared infrastructure) —
   at most ONE entry per session (avoids re-triggering repeatedly
   within the same range breakout).
5. No separate volatility-expansion filter this time (the opening-range
   structure itself is a volatility-regime concept — the range is
   defined BY the session's own opening volatility, making a redundant
   `realized_vol_ratio` filter less economically motivated here than
   in BI1's any-time version).

**Rejection criterion (fixed before running, same standard)**: REJECT
if forward drift (measured the same way as BI1, at 15/30/60min from the
ORB signal bar) is ~zero or negative at all three horizons.

If BI2 also REJECTs: per the user's explicit instruction, REJECT the
Nasdaq leg of B_INDEX cleanly. Since S&P 500 testing was explicitly
conditioned on a Nasdaq-confirmed edge (a generalization test, not an
independent first attempt), and testing the same rejected rule on
S&P 500 would not be informative either way, B_INDEX closes for this
cycle without an S&P 500 test if both Nasdaq hypotheses fail.

---

*Pre-registered 2026-08-24, before any B_INDEX result was looked at.*
*Revision 1: 2026-08-24, after BI1's clean REJECT.*
