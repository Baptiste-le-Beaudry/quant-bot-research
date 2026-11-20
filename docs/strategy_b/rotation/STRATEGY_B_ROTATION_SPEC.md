# Strategy B_ROTATION — Pre-Registration Spec

**STRATEGY_ID = B_ROTATION**

A structurally distinct sub-family of Strategy B, kept separate from the
momentum/breakout family (B1-B8, all REJECT) and the funding-rate family
(BF1-BF2, all REJECT) at every level: own spec file, own research log,
own scripts directory (`scripts/strategy_b/rotation/`). Never confused
with Strategy A (single-symbol mean-reversion) or either rejected
Strategy B sub-family (single-symbol momentum/breakout,
single-symbol funding). User-directed: after two independent
single-asset directions REJECTED, proceed automatically to
cross-sectional rotation. Registered 2026-08-24.

## Economic hypothesis

Cross-sectional momentum: among a basket of correlated cryptos, assets
with the STRONGEST recent RELATIVE performance (vs. the rest of the
basket, not vs. their own history) tend to continue outperforming the
group over the following short period — a well-documented factor in
traditional finance (momentum/relative-strength), tested here on a
crypto universe at a DAILY rebalance cadence (deliberately slower than
every other experiment in this project, since cross-sectional
momentum/rotation is conventionally studied at day-to-week horizons, not
minute-level — forcing the same 10-minute horizon onto a fundamentally
cross-sectional question would not be a fair test of the actual
hypothesis).

**Why this is structurally different from everything tested so far**:
Strategy A and every Strategy B variant so far (breakout family,
funding family) are all SINGLE-SYMBOL, ABSOLUTE-return bets (is BTC
about to go up or down on its own). Cross-sectional rotation is a
RELATIVE-return bet across a basket (is symbol X about to outperform
symbol Y), which can in principle be profitable even in a flat or
declining overall market — a genuinely different risk/return source,
expected to have low correlation with every single-symbol strategy
tested so far for that reason (not merely different parameters on the
same underlying bet).

## Universe (fixed, chosen BEFORE looking at any result)

9 symbols with long, comparable Binance USDT-M Futures history:
BTCUSDT, ETHUSDT, XRPUSDT, TRXUSDT, LTCUSDT, ETCUSDT, LINKUSDT, ADAUSDT,
BNBUSDT — all with 1-minute data starting on or before 2020-02-10 (the
latest start date among these 9, BNBUSDT's). Deliberately EXCLUDES
SOLUSDT, AVAXUSDT, DOGEUSDT, DOTUSDT (later listing dates — including
them would either shrink the common history a lot or require a
variable/evolving universe, more complexity than a first pass needs;
per this project's own established preference for "a few solid
candidates over many, avoiding microcaps/thin-history symbols chosen
just for variety").

Common date range: **2020-02-10 to SAFE_END (2025-03-28)** — SAFE_END is
the SAME boundary already used by every walk-forward in this project
(`min(BTC, ETH HOLDOUT_START)` from `scripts/walk_forward_engine.py`),
applied uniformly to all 9 symbols (conservative even for ETC/TRX, which
don't have a formally carved own HOLDOUT_START in `quant_bot/data/
splits.py` — capping at the same 2025-03-28 boundary as BTC/ETH is at
least as conservative for them too, and is exactly the same choice
already used without incident for their Phase A transfer walk-forward).
HOLDOUT (anything from SAFE_END onward, or any symbol's own later
HOLDOUT_START) is never loaded.

## Entry / portfolio construction (simplest possible version)

Daily bars (resampled from already-downloaded 1-minute data, close-to-
close). At each day's close `t` (using only data available up to and
including `t`, no lookahead):
1. Compute each symbol's trailing 7-day return (`close[t]/close[t-7] - 1`).
2. Rank all 9 symbols by this trailing return.
3. Hold the **top 2** ranked symbols, equal-weighted, for the next day
   (enter at `t`'s close, exit/re-rank at `t+1`'s close).
4. Rebalance daily: if the top-2 set changes, sell the dropped symbol(s)
   and buy the newly-entered one(s); positions that remain top-2 are
   simply held (no unnecessary turnover).

Long-only for this first pass (matches how the momentum/breakout family
also started long-only) — a long/short market-neutral version is a
natural next step if this shows promise, not attempted in this pass.

`lookback=7 days` and `K=2` are fixed a priori (not fit to data, per
the mandate's explicit instruction to avoid a big grid search) — no
threshold is being calibrated from TRAIN here (rank-based selection has
no free numeric cutoff the way percentile-threshold entries do), so
there is no TRAIN-only calibration step needed for this specific design;
the TRAIN/VALIDATION split is still respected for REPORTING discipline
(only VALIDATION-period performance is used for the cheap-screen
verdict, consistent with every other experiment in this project even
though nothing is actually being fit here).

## Costs and sizing

Round-trip fee+slippage applied only on actual turnover (a symbol
entering or leaving the top-2 set), using this project's existing cost
constants (`FEE_PER_SIDE`, `BASE_SLIP_PER_SIDE`). No leverage (1x,
spot-style) for this first pass — deliberately conservative and
structurally different from the leveraged intraday framework used by
Strategy A and every other Strategy B sub-family, since daily-bar
rotation is a fundamentally different risk profile.

## Validation metrics

Same conventions (n_trades/rebalance-events, PF, expectancy, win rate,
MaxDD, CAGR) PLUS the mandate's explicit requirement:
`Corr(PnL_A, PnL_B_ROTATION)` and B_ROTATION's performance during
Strategy A's historical drawdown periods.

## Rejection criteria (fixed BEFORE looking at any result)

- **Cheap screen (VALIDATION-period only, frozen K=2/lookback=7)**: if
  total return over the VALIDATION period is negative (or PF <= 1 on
  the daily rebalance P&L series), REJECT the initial design outright —
  no grid search over K/lookback to rescue it.
- Given the daily rebalance cadence, "n_trades" here means rebalance
  events (position changes), not the thousands-of-trades scale of the
  intraday strategies — the sample-size floor is adjusted accordingly:
  at minimum, a full VALIDATION period of daily observations (typically
  several hundred trading days) is required before drawing any
  conclusion, rather than a fixed trade-count floor.
- **Walk-forward** (if cheap screen survives): reject if the result
  depends on a small number of dominant days/rebalance events.
- **Correlation gate**: even a positive result is only interesting for
  portfolio purposes if `Corr(PnL_A, PnL_B_ROTATION)` is genuinely low —
  per the hypothesis's own structural reasoning above, this is expected,
  but measured, not assumed.

If the simple version REJECTs clearly: per the same discipline as every
other sub-family, at most a couple of economically distinct pre-
registered follow-ups (e.g., different K, or long/short market-neutral),
not a parameter search — and if the whole rotation family shows no
robust edge, REJECT it cleanly. This is currently the last major
pre-identified alternative direction; if it also fails, the honest
overall Phase B conclusion becomes "no structurally distinct alpha
source has been found to complement Strategy A this cycle," reported as
such rather than forced positive.

## HOLDOUT policy

Identical to every other strategy in this project: completely locked,
never loaded, scored, or tuned against.

---

## REVISION 1 (2026-08-24) — BR2: cross-sectional mean-reversion
(laggard rebound)

Experiment BR1 (top-2 momentum rotation) technically didn't trigger the
narrow binary REJECT criterion (PF=1.088>1, return positive), but a
null-baseline comparison (equal-weight all-9 basket, BTC solo
buy-and-hold — both added post-hoc as a required control, not a new
hypothesis) showed BR1 is strictly dominated on every metric (far lower
return, far worse MaxDD, even worse PF) — see
`STRATEGY_B_ROTATION_RESEARCH_LOG.md`'s BR1 card. Overridden to REJECT.

**New economic angle**: this project's consistent pattern across every
sub-family tested so far is that MEAN-REVERSION works (Strategy A) and
MOMENTUM-CONTINUATION does not (the entire single-symbol Strategy B
breakout family, and now BR1's cross-sectional momentum). This motivates
testing the OPPOSITE cross-sectional selection rule: **hold the BOTTOM
2 ranked symbols** (worst trailing-7-day performers, "laggards") instead
of the top 2, betting on cross-sectional reversion (today's laggards
catch up to the group over the next period) rather than continuation.
This is a structurally different hypothesis (opposite selection
direction), not a parameter tweak (K/lookback unchanged at 2/7).

**Rejection criterion (fixed before running, same standard as BR1 but
now EXPLICITLY including the baseline comparison)**: REJECT if
VALIDATION-period total return is negative, PF <= 1, OR the strategy is
dominated by the equal-weight-9-basket null baseline on both return AND
MaxDD (the gap in BR1's own pre-registration, fixed here).

If BR2 also REJECTs (either by the binary criterion or the baseline
comparison): per the user's explicit instruction, REJECT the entire
cross-sectional rotation family cleanly. Since this is currently the
last pre-identified major alternative direction, the honest overall
Phase B conclusion becomes "no structurally distinct alpha source has
been found to complement Strategy A this cycle" — reported as such.

---

*Pre-registered 2026-08-24, before any B_ROTATION result was looked at.*
*Revision 1: 2026-08-24, after BR1's baseline-comparison REJECT.*
