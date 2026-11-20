# Strategy C — Feasibility Report

**STRATEGY_ID = C**

User-directed takeover, 2026-08-24: Strategy C (US equity/ETF intraday
microstructure) transfers from Gemini to Claude. Claude's prior RED TEAM
mandate is COMPLETE (`docs/SCIENTIFIC_VALIDATION_AUDIT.md`); all
scientific discipline developed there is carried forward and applied
here. Strategy A stays FROZEN (Codex's forward-paper baseline, not
touched). Strategy B stays CLOSED (not reopened). HOLDOUT stays LOCKED.

## 1. Takeover audit from Gemini

Before writing anything, the repo was inspected for any Gemini-created
Strategy C artifacts (`docs/strategy_c/`, `scripts/strategy_c/`,
`quant_bot/strategy_c/`, and a repo-wide search for QQQ/SPY/
microstructure/order-flow/quote-imbalance/Databento/Polygon/SIP/L2
references).

**Found**:
- `docs/strategy_c/STRATEGY_C_SPEC.md` (1681 bytes) — a reasonable,
  well-scoped pre-registration skeleton: objective, scope/constraints
  (QQQ primary, SPY generalization, Strategy A/B independence, no ML
  before raw drift, no live execution), a 13-phase scientific protocol
  outline, an initial economic hypothesis ("abnormally strong and
  persistent buying/selling pressure in the order flow precedes
  short-term directional price movements before fully reflected in
  mid-price"), and a documentation policy. **Classification: PARTIAL,
  TRUSTWORTHY as a starting skeleton** — consistent with this mandate's
  own framing, no factual claims to independently verify since it
  contains no data or results, only a plan.
- `docs/strategy_c/STRATEGY_C_RESEARCH_LOG.md` (763 bytes) — one
  registry row, "C0 | Initial Setup | 2026-08-24 | PASS | ADOPTED |
  Created structure and SPEC." **Classification: MISLEADING LABELING,
  corrected below** — marking directory/file creation as a scientific
  "PASS/ADOPTED" result conflates administrative setup with an actual
  hypothesis test. No real experiment was run. Corrected in Section 16
  below (relabeled as C0 = SETUP, not a scientific PASS).
- `scripts/strategy_c/` — **empty directory**, no code.
- `quant_bot/strategy_c/` — **empty directory**, no code.
- No data files (QQQ, SPY, or otherwise tick-level) found anywhere in
  the repo. No provider SDK/dependency in `requirements.txt`. No API
  keys or provider config in `.env.example` or `quant_bot/config.py`.

**Verdict: AUDIT → VERIFY → REUSE IF VALID, applied.** Gemini's actual
work product is minimal (two short documents, no code, no data) but the
hypothesis framing and phased protocol are sound and consistent with
this mandate's own instructions — **reused as the starting point**
(Section 3's hypothesis below builds directly on it, refined), not
discarded. Nothing else exists to verify or reuse; this report
effectively starts substantive work from scratch, with Gemini's
documents kept (and corrected) rather than replaced.

## 2. Economic hypothesis

Refined from Gemini's starting framing, made falsifiable and specific
per this mandate's own emphasis on causal, executable-price-based
testing:

**H_C1**: On QQQ, when order-flow/quote imbalance — the relative
pressure of aggressive buying vs. selling, and/or resting bid vs. ask
size — is extreme and persistent over a short window, AND trading
activity is elevated (confirming genuine participation, not noise),
the subsequent short-horizon (30s-5min) price move is directionally
biased in the same direction as the imbalance, by an amount that
survives realistic spread, slippage, and cost after accounting for
using EXECUTABLE (not mid) prices.

This targets a fundamentally different market mechanism than Strategy
A (crypto mean-reversion) or the rejected Strategy B family (crypto
momentum/breakout on OHLCV only) — order-flow pressure in a
lit, NBBO-quoted equity market is a structurally distinct information
source from price-action-only signals, and the venue/asset class itself
(US equity ETF vs. 24/7 crypto perpetuals) removes the crypto-specific
correlated-regime concentration flagged in Section 4 of the scientific
audit.

## 3. Minimal required dataset

Per the mandate's explicit "determine the MINIMUM necessary to falsify
the hypothesis" instruction — NOT full L2, NOT multiple years, NOT
every venue:

- **Trades**: price, size, timestamp (exchange + receive if available),
  venue, trade condition flags (needed for aggressor classification,
  Section 9 of the spec).
- **Quotes (NBBO/top-of-book)**: bid price, ask price, bid size, ask
  size, timestamp. **Consolidated NBBO is the target, not single-venue
  quotes** — a single-venue (e.g. one exchange's own book) view
  understates true available liquidity and would bias any imbalance
  measure.
- **Explicitly NOT required for the first pass**: full order-book depth
  (L2/L3, multiple price levels), multiple exchanges' raw depth feeds,
  or a multi-year history. Section 26 of the mandate is explicit: L2 is
  a response to a specific, demonstrated information gap from an L1
  analysis, not a default starting point.
- **Time span**: a few months of continuous QQQ tick data (trades +
  NBBO) is very likely sufficient to either find or cleanly falsify a
  raw forward-drift relationship (Section 12's bucket analysis needs
  enough independent EVENTS, not calendar years — see Section 21's
  independent-unit-count discipline, carried over directly from
  Experiment 42's own lesson). A precise sample-size target is set
  AFTER the raw-drift diagnostic's own bucket populations are visible
  (pre-registered rule, not chosen post-hoc: at least 30 independent
  SESSION-days per decile bucket, mirroring this project's own n>=30
  floor convention used throughout Strategy A/B).

## 4. Provider options (researched 2026-08-24, current pricing verified via web search — not from training-data memory, which could be stale)

| Provider | Dataset | Historical coverage | Trades | Quotes/NBBO | L1 | L2 | Venues | Cost | Notes |
|---|---|---|---|---|---|---|---|---|---|
| **Databento** | `XNAS.ITCH` (full Nasdaq depth) | From 2018-05-01 | Y | Y (derivable from book) | Y | Y (full MBO) | Nasdaq only | Usage-based $/GB, exact quote via their price-estimate tool | Overkill for a first pass — full order-book depth, not needed yet per Section 26 |
| **Databento** | **L1 schemas: Trades, BBO, TBBO, MBP-1** | Not fully verified per-schema (needs the price-estimate/schema-coverage tool before committing) | Y | Y (BBO/TBBO/MBP-1 = top-of-book, exactly what Section 3 needs) | Y | N (by design — this is the RIGHT granularity for C1) | Depends on schema/venue selected | **Usage-based $/GB. $125 FREE CREDIT for new signups (valid 6 months).** A few months of QQQ L1 trades+BBO very plausibly fits within this free credit, but the EXACT size/cost was not obtained (requires their price-estimate tool, which needs an account) | **Recommended starting option** — right granularity, likely zero out-of-pocket for the first pass |
| **Massive.com** (formerly Polygon.io, rebranded early 2026) | Stocks Basic | 2yr | N | N | N | N | — | $0/mo | Insufficient — no trades/quotes at all |
| **Massive.com** | Stocks Starter | 5yr | N | N | N | N | — | $29/mo | Still insufficient — no trades/quotes, 15-min delayed bars only |
| **Massive.com** | Stocks Developer | 10yr | Y | N | — | N | — | $79/mo | Trades only, no quotes — insufficient for the imbalance hypothesis, which needs bid/ask |
| **Massive.com** | Stocks Advanced | 20+yr | Y | Y | Y | N | Consolidated | **$199/month** | The cheapest Massive/Polygon tier that actually has BOTH trades and quotes — a real, usable alternative if Databento's actual cost estimate turns out unfavorable |
| **Alpaca (IEX free feed)** | IEX only | Not specified in docs | Y | Ambiguous (FAQ doesn't confirm bid/ask at free tier) | Unclear | N | **IEX only — ~2.4% of total market trade count** (verified via Alpaca's own documented example: 12,630 IEX trades vs 535,136+ SIP trades for one AAPL daily bar) | **$0** | Free, but a single thin venue is NOT representative of consolidated market pressure — the core hypothesis is about AGGREGATE order flow, so this venue-limited feed risks a false negative (real signal present in the full tape, invisible in a 2.4% slice). Could serve as a near-zero-cost SANITY PILOT only, not the main test. |
| **Alpaca (SIP)** | Consolidated, all exchanges | — | Y | Y | Y | N | All | Requires "Algo Trader Plus" subscription for reliable access; a "historical query must be 15+ min old" carve-out exists in the docs but is described ambiguously/inconsistently on Alpaca's own FAQ page (verified via direct fetch — the same page both states the 15-min carve-out AND says "all the latest endpoints require a subscription to be used with SIP") | Not independently confirmed — **do not rely on this without direct account-level verification** | Flagged as UNVERIFIED, not assumed free |

**Recommendation, pending your approval (per the mandate's explicit
STOP-and-ask rule)**: **Databento's L1 schema (Trades + BBO/TBBO/MBP-1)
for QQQ**, starting with their $125 free credit, is the strongest
candidate — right data granularity (not overpaying for full L2 depth
we don't need yet), usage-based (pay only for what's downloaded, not a
recurring subscription), and the free credit plausibly covers an
initial few-months QQQ sample entirely at zero net cost. **The exact
size/cost was NOT obtained** (Databento's price-estimate tool requires
an account/API key to query precisely) — per Section 5 below, this is
exactly the trigger point for the mandate's STOP rule.

## 5. Data cost — STOP point (per the mandate, no automatic spending)

**I have not created a Databento (or any provider) account, and no
money has been spent.** Before proceeding further:

```
PROVIDER: Databento
DATASET: XNAS.ITCH or equivalent consolidated feed's L1 schema
  (Trades, BBO/TBBO/MBP-1 — top-of-book, not full order-book depth)
PERIOD: proposed 3-6 months of continuous QQQ history (exact window
  TBD based on the price-estimate tool's own size/cost readout)
SYMBOLS: QQQ only for this first pass (SPY deferred to the
  generalization stage, Section 12 of the SPEC, only after QQQ passes)
ESTIMATED SIZE: not obtained — requires Databento's own price-estimate
  tool, which requires account creation
ESTIMATED COST: plausibly $0 (within the $125 free credit) based on
  typical L1 (not full-depth) tick data volumes for a single liquid
  ETF over a few months, but NOT independently verified/quoted
REASON: this is the minimal dataset identified in Section 3 to test
  H_C1 (Section 2) — trades + top-of-book NBBO, no full order-book
  depth, no multi-year history, no multi-symbol download before QQQ's
  own result is known
```

**Requesting your decision**: may I create a Databento account (free
signup, no payment method required for the $125 credit per their own
signup flow as described publicly) and query their price-estimate tool
to get an EXACT size/cost figure for the proposed QQQ window, before
downloading anything? This itself involves creating a third-party
account under the project's name/email, which I'm flagging for your
awareness even though the immediate data pull is expected to stay
within the free credit — I will not download anything or incur any
charge without a further explicit confirmation once the exact quote is
in hand, per Section 2's STOP rule.

## 6. Storage estimate

Given Section 4's schema choice (L1: trades + top-of-book quotes, not
full depth), and this project's own established convention (`data/
strategy_c/{raw,normalized,features,experiments}/`, Parquet for tick/
quote data, CSV only for small summaries — per the mandate's C4), a
few months of QQQ L1 tick data is expected to be on the order of a few
GB to a few tens of GB (a single liquid ETF's L1 trades+BBO stream is
much lighter than full order-book depth, though not as light as this
project's existing 1-minute crypto bars) — this is a rough order-of-
magnitude estimate, to be replaced with an exact figure once Section 5's
price-estimate query is run.

## 7. Timestamp requirements

Per the mandate's C5/C7 and this project's own prior bug history
(Section 7 of the scientific audit — the B_INDEX NY-open DST bug is a
direct precedent):
- **Exchange timestamp preferred over receive timestamp** where both
  are available, for causal ordering; if only receive timestamps exist,
  document this explicitly as a limitation (adds a small, bounded
  latency margin to any "causal" claim, not a leak, but worth stating).
- **Session boundaries**: regular US session 09:30-16:00
  America/New_York, DST-aware (reusing the exact `tz_convert
  ("America/New_York")` pattern already validated in this project's
  B_INDEX work, not re-deriving it from scratch).
- **Explicit tests required** (per the mandate) at the 09:30 NY open,
  16:00 NY close, and DST transition dates — planned for the Section 5
  (data audit) stage once real data exists, not yet built (no data to
  test against).

## 8. Initial features (4-8 maximum, per the mandate's C8)

1. **Quote imbalance**: `QI = (bid_size - ask_size) / (bid_size + ask_size)`.
2. **Trade flow imbalance**: aggressive buy volume vs. aggressive sell
   volume over a short trailing window (requires an aggressor
   classification method — Section 9).
3. **Spread**: `(ask - bid) / mid`.
4. **Trade intensity**: recent trade count/volume vs. that symbol's own
   recent-history baseline (relative, not absolute — matching this
   project's own established preference, e.g. `realized_vol_ratio` in
   Strategy A/B, for the same reason: raw thresholds don't transfer
   across regimes).
5. **Short-term volatility**: trailing realized volatility over a short
   window (same causal-rolling-window discipline as every other feature
   in this project).
6. **Distance to session VWAP**: current price relative to the
   session's own volume-weighted average price so far.
7. **Short-term price impact**: price change per unit of aggressive
   flow (a direct microstructure-impact measure, distinct from #1/#2's
   pressure measures).

Kept to exactly this list for the first pass, per the mandate's
explicit "not immediately 100 features" instruction.

## 9. Trade aggressor classification

No dataset has been acquired yet, so the exact method is not yet
selected — documented here as a REQUIRED, explicit decision before
Section 8's features can be computed: candidates are the **quote test**
(compare trade price to the prevailing NBBO: at/above ask = buyer-
initiated, at/below bid = seller-initiated, midpoint = ambiguous) or
the **tick rule** (compare to the previous trade price) as a fallback
if quote data has gaps. Per the mandate's explicit warning, "a trade
above the last price" will NOT be assumed buyer-initiated without this
being verified against the actual quote context. This will be
documented precisely, with its own verification against known
liquidity events, once real data exists (Section 5 of the data-audit
stage, not yet run).

## 10. Initial targets

Forward EXECUTABLE return (Section 11 below), NOT mid-to-mid, over
three pre-registered horizons (Section 10 of the mandate): **30
seconds, 60 seconds, 5 minutes**. A 15-minute horizon is explicitly
deferred, only added if the diagnostic (Section 12/raw forward drift)
shows a reason to — not swept blindly.

## 11. Null baselines (pre-registered before any result is examined)

Per the mandate's C13, four null comparisons are pre-committed as part
of this design, before any real data exists to bias the choice:
1. Same-time-of-day random timestamps (controls for intraday drift/
   volatility patterns unrelated to the actual imbalance signal).
2. Same-volatility-regime random timestamps (controls for "the signal
   just proxies for high volatility," the exact failure mode that
   killed the entire crypto Strategy B breakout family per the
   scientific audit's own ledger).
3. Randomized entry direction (controls for a structural long/short
   bias in QQQ's own drift, e.g. the well-known equity index upward
   drift).
4. Permuted imbalance values preserving intraday structure (controls
   for "any plausible-looking feature would show this" vs. the SPECIFIC
   informational content of the imbalance measure).

## 12. Cost model

Per the mandate's C11/C15: EXECUTABLE entry (long ≈ ask + slippage,
short ≈ bid - slippage) and EXECUTABLE exit, not mid-price. Every
result reported as MID-TO-MID EDGE and EXECUTABLE EDGE separately, with
an explicit RAW EDGE → SPREAD → SLIPPAGE → OTHER COSTS → NET EDGE
waterfall, mirroring the crypto strategies' own stress-test convention
in spirit but using equity-appropriate cost components (bid/ask spread
directly measured from the NBBO data itself, not assumed; commissions;
regulatory fees; latency sensitivity per Section 27 of the mandate).

## 13. Walk-forward design

Deferred to AFTER a positive raw-forward-drift + null-baseline result
(per the mandate's explicit phase ordering — walk-forward is Step 9 of
12, not Step 1). When reached: TRAIN/PURGE/TEST/EMBARGO, purging
specifically because high-frequency targets can overlap heavily (a
30-second-horizon label computed every second means adjacent
observations' target windows overlap massively) — this directly
extends the scientific audit's own Section 4 finding (label overlap was
flagged there as a previously-unaddressed gap in the crypto strategies)
to a context where it is now unambiguously material, not a minor
theoretical concern.

## 14. Pass/reject criteria (fixed now, before any data exists)

- **Raw forward drift** (Section 12/C12 of the mandate): REJECT if the
  bucket-level relationship between imbalance and forward return is not
  monotonic or economically coherent across deciles, or if it doesn't
  survive the Section 11 null baselines.
- **Cheap screen** (C17): REJECT if PF <= 1 after realistic costs
  (Section 12), computed separately for LONG and SHORT.
- **Sample size**: REJECT-pending-more-data (not REJECT outright) if
  independent event count (Section 21 of the mandate — sessions/days/
  regimes, NOT raw tick count) is below a floor to be set once the real
  data's own event-clustering structure is visible.
- **Break-even execution** (C28): every surviving candidate must report
  break-even spread/slippage/latency BEFORE declaring PF<=1 the actual
  failure point — a strategy that only works at unrealistically tight
  spreads is REJECT regardless of its raw PF.

## 15. Leakage risks (pre-identified, before any code is written)

Per the mandate's C7 explicit list: quotes received after a trade
(sequencing), bar aggregation windows, session VWAP (must be computed
causally, resetting each session, never using the full session's future
volume), rolling features (standard causal-window discipline, already
well-established throughout this project), trade aggressor
classification (Section 9 — must use only the quote state KNOWN at
trade time, not a future-revised NBBO), forward-filled quotes (a stale
quote must not be treated as "current" indefinitely — needs an explicit
staleness cutoff), and resampling (any bar aggregation must respect
strict left-closed, causal boundaries). Synthetic tests that
deliberately inject future data and confirm the pipeline REJECTS it are
planned for the data-audit stage (C7's explicit requirement), not yet
built since no data/pipeline exists yet.

## 16. Exact first experiment (C16-style pre-registration)

**Experiment C1** (to run once data exists): raw forward drift +
null-baseline diagnostic for quote imbalance and trade flow imbalance
on QQQ, at 30s/60s/5min horizons, bucketed by imbalance decile,
reporting n/mean/median forward return/win rate/MFE/MAE per bucket,
compared against all four Section 11 null baselines, BEFORE any
threshold, entry rule, or exit rule is defined. This is explicitly the
FALSIFICATION step (Section 12 of the mandate: "we want to arrive at
either A) a real, causally-observable QQQ microstructure drift that
survives nulls and costs, warranting a walk-forward, OR B) apparent
effects that disappear after executable prices/spread/nulls, and
Strategy C is REJECTED at this level without wasting time on ML/L2" —
both are valid, pre-committed outcomes).

**Whether L2 is actually necessary**: **not yet, and not by default.**
Per Section 3/26 of this report, L1 (trades + top-of-book NBBO) is the
minimal dataset needed to test H_C1 as currently specified. L2 (multi-
level depth, queue position, book slope) would only become justified if
Experiment C1's diagnostic shows a signal that L1 data can't
sufficiently characterize (e.g. if top-of-book imbalance is too noisy
but the underlying economic mechanism plausibly depends on deeper book
pressure) — a decision to be made AFTER C1's own result, not before.

## Correction to Gemini's research log

`docs/strategy_c/STRATEGY_C_RESEARCH_LOG.md`'s existing "C0 | Initial
Setup | PASS | ADOPTED" entry is corrected below (not deleted, per this
project's standing convention of never silently erasing prior text) —
directory/file creation is administrative setup, not a scientific
result, and should not carry a PASS/ADOPTED label implying a hypothesis
was tested.

---

*Report compiled 2026-08-24 by Claude, taking over Strategy C from
Gemini per explicit user direction. No data downloaded, no account
created, no money spent. Awaiting explicit go-ahead on Section 5 before
proceeding to actual data acquisition.*
