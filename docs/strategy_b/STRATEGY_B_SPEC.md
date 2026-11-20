# Strategy B — Pre-Registration Spec

**STRATEGY_ID = B**

Written and frozen BEFORE any optimization or parameter search, per the
user's explicit mandate (2026-08-23). This document is not to be edited
retroactively to fit results — if the initial design needs to change, that
is a new, separately-dated revision noted at the bottom, not a silent edit.

## 1. Economic hypothesis

Strategy A profits from short-term **mean-reversion**: a sharp intraday dip
in an already-volatile market tends to bounce within ~10-50 minutes,
because the drop is read as a short-term overreaction (liquidation
cascade, thin order book, panic selling) that gets partially reversed once
the selling pressure exhausts.

Strategy B targets the structurally **opposite** phenomenon:
**trend-continuation after a volatility-confirmed breakout**. The
hypothesis is that when price breaks above a recent local high WHILE
volatility is genuinely *expanding* (not just elevated — accelerating)
and volume confirms real participation, the move tends to continue for a
similar short horizon, because in crypto specifically: (a) breakouts
trigger stop-loss orders from short-sellers positioned inside the prior
range, mechanically pushing price further in the breakout direction; (b)
trend-following retail and algorithmic flow chases confirmed breakouts
rather than fading them; (c) unlike Strategy A's "overreaction that
reverts," a genuine volume+volatility-confirmed breakout is read as
*information* (a real shift in supply/demand), not noise.

## 2. Regime targeted

Trending / expanding-volatility regime — the opposite of Strategy A's
target (range-bound-but-locally-volatile mean-reversion regime).
Concretely: Strategy A's own regime classifier work (Experiment 24,
`hurst_120` x volatility tercile) already established that every cell had
positive EV for A, with an unexploited RANGE > TREND quality gradient —
i.e. A's edge is best in RANGE-like conditions. Strategy B is expected to
need the opposite: a high-`hurst_120` (trending), volatility-EXPANDING
(not just elevated) condition. Reusing the existing `hurst_120`/volatility
FEATURE COMPUTATION code is fine (shared infrastructure, like
`quant_bot/risk` is shared) — but Strategy B's ENTRY LOGIC itself is new
and does not reuse Strategy A's signal/model.

## 3. Why low correlation with Strategy A is expected

Strategy A's entry filter explicitly requires **LOW** `range_pos_60`
(price near the BOTTOM of its recent range) and elevated volatility.
Strategy B's entry requires the opposite: price making a NEW LOCAL HIGH
(breaking the top of its recent range) with volatility genuinely
expanding. These two conditions are close to mutually exclusive on the
same bar for the same symbol at the same time — a bar cannot simultaneously
be "near the bottom of its N-bar range" and "breaking above its N-bar
high." This is a structural (not just empirical) reason to expect low
same-instant overlap; actual P&L correlation is measured empirically in
Experiment B9, not assumed.

## 4. Entry conditions (conceptual, B1 = simplest possible version)

Rule-based, NOT machine-learning, for the first pass (per the mandate:
prove the phenomenon exists before any model complexity). Long-only
initially (matches Strategy A's scope; short side explicitly deferred,
not attempted this cycle — crypto's structural long bias and funding-rate
asymmetry make short breakouts a genuinely different question that
deserves its own separate hypothesis later, not bundled in here).

At each bar `t` (using ONLY information available up to and including bar
`t`, i.e. all rolling windows computed with backward-looking windows,
`shift`ed where needed to avoid any same-bar lookahead into the breakout
level itself):

1. **Breakout**: `close[t] > rolling_max(high, N)[t-1]` — strictly above
   the highest high of the PRIOR N bars (N excludes bar `t` itself, so the
   breakout level is fully known before the triggering bar closes).
2. **Volatility expansion** (relative, not absolute — the multi-asset
   generalization work already found absolute vol cutoffs don't
   transfer well): `realized_vol_30[t] / realized_vol_30.rolling(120)
   .mean()[t] > vol_expansion_ratio`.
3. **Volume confirmation**: `volume[t] / volume.rolling(60).mean()[t] >
   volume_ratio`.

Starting parameter guesses (chosen a priori, NOT fit to data — see
Section 9 for the falsification-first cheap-screen plan before any
tuning): N=60 (1 hour lookback), vol_expansion_ratio=1.5,
volume_ratio=1.5. Minimum parameter count by design.

Entry fill: at bar `t`'s own close (immediate entry), mirroring Strategy
A's own finding (Experiment 16) that immediate entry beat every delayed/
limit-retrace variant tested — reusing a validated finding about market
microstructure, not reusing A's alpha logic itself.

## 5. Exit conditions (conceptual)

Reuses Strategy A's PROVEN EXIT MECHANICS (trailing stop after
activation, protective stop from a TRAIN-derived MAE percentile) as
shared risk-management infrastructure — this is analogous to reusing
`quant_bot/risk` for portfolio accounting: exit plumbing is not the
alpha being tested, entry logic is. Critically, the exact
activate_at/trail_distance/stop-percentile NUMBERS are re-derived from
Strategy B's OWN TRAIN population, never copied from Strategy A's frozen
0.63%/0.80%/p90 constants (same TRAIN-only-calibration discipline as
every experiment in this project). Exit METHOD itself (fixed trailing vs.
something else) is explicitly flagged as a candidate for a LATER,
separate optimization experiment (Section 12/B3 in the parent mandate),
not decided now.

## 6. Risk assumptions

Same dynamic-leverage-cap formula as Strategy A
(`min(SAFETY_MARGIN*STOP_OUT_FRACTION/stop_distance, MAX_LEVERAGE_CAP)`,
SAFETY_MARGIN=0.75, STOP_OUT_FRACTION=0.5, cap=30x) — this is a portfolio-
risk-management primitive, not strategy alpha, reused for the same reason
as Section 5. Position sizing at the portfolio level uses
`quant_bot/risk` (Codex-owned, read-only) exactly as Strategy A does.

## 7. Expected failure modes (pre-registered, so a bad result isn't
   post-hoc rationalized)

- Breakouts in crypto may simply be false signals more often than not
  (crypto is famous for stop-hunts and fakeouts) — the strategy could
  show negative expectancy outright.
- The "volatility expansion" and "volume confirmation" filters could be
  too loose (too many false breakouts pass) or too tight (too few trades
  to be statistically meaningful) at the starting parameter guesses.
- Momentum in 1-minute crypto data may already be arbitraged away by
  faster market participants by the time a bar closes and a signal could
  realistically be acted on.
- The strategy could show a real edge on paper but be dominated by
  execution/gap fragility even worse than Strategy A's (already-known)
  gap/latency sensitivity, since momentum entries chase a fast-moving
  price rather than catching a stall.

## 8. Validation metrics

Same conventions as this project's entire history (not reinvented):
n_trades, PF, expectancy, total return, win rate, MaxDD, walk-forward
median PF / %folds PF>1, Monte Carlo tail risk, forced liquidations,
stress-test degradation. PLUS, specific to Strategy B's purpose:
correlation with Strategy A's P&L (daily and weekly), Strategy B's
performance specifically DURING Strategy A's historical drawdown periods
(and vice versa), and simultaneous-trade overlap.

## 9. Rejection criteria (fixed BEFORE looking at any result)

- **Cheap screen (BTC+ETH, frozen simple rule, no tuning)**: if aggregate
  PF <= 1.0 on BOTH BTC and ETH with a reasonable sample (n>=30 combined),
  REJECT the initial design outright — do not immediately grid-search
  parameters to rescue it. A redesign (different conceptual filter, not a
  parameter tweak) would be a new, separately-numbered hypothesis, not a
  continuation of this one.
- **Walk-forward** (if cheap screen passes): reject if median PF <= 1,
  or if the result depends on a single dominant fold (same "don't trust
  one lucky fold" discipline as every prior walk-forward in this
  project).
- **Forced liquidations**: any forced liquidation under the registered
  dynamic-leverage sizing is disqualifying, same as Strategy A's standard.
- **Stress test**: must not flip catastrophically negative under the
  standard combined-worst-case scenario (slippage 2x + gap 0.25% + 1min
  latency) — "degrades but stays roughly breakeven-or-better" is
  acceptable, "collapses to deeply negative" is not, mirroring how
  Strategy A's own known gap/latency fragility is treated as a flagged
  caveat, not an automatic killer, IF the degradation is proportionate.
- **Correlation gate**: even a positive, walk-forward-confirmed edge is
  only interesting for this project's purpose if it's NOT highly
  correlated with Strategy A (per Section 3's hypothesis) — a profitable
  but highly-A-correlated Strategy B would be documented honestly as
  "real edge, low diversification value," not silently reframed as a
  portfolio win.

## 10. Walk-forward method

Same expanding-TRAIN-window, fixed-TEST-window design as Strategy A
(`scripts/walk_forward_engine.py`'s own `build_folds`), reused as
shared research INFRASTRUCTURE (fold construction is a methodology
choice, not alpha) — 24-month initial TRAIN, 3-month TEST, 3-month step,
same per-symbol HOLDOUT boundaries from `quant_bot/data/splits.py`
(Codex-owned canonical guard, read-only).

## 11. Stress method

Same scenario grid as Strategy A's established stress battery (slippage
2x/3x, gap 0.10/0.25/0.50%, latency 1-2min, combined worst-case),
`scripts/multi_crypto_walkforward.py`'s `SCENARIOS`/`resolve_stressed`
reused as shared infrastructure.

## 12. HOLDOUT policy

Identical to Strategy A: completely LOCKED, at every stage, for every
symbol. Strategy B is not a reason to open it. No `--unlock-holdout`
mechanism exists or will be added.

---

## REVISION 1 (2026-08-24) — order-flow imbalance continuation
(Experiment B8)

The original momentum/breakout hypothesis (Sections 1-12 above) was
REJECTED after 4 independently-designed variants (B1, B4, B6, B7 — see
`docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md`), with a mechanistic
diagnostic showing near-zero net drift after breakout triggers on
BTC/ETH. This revision does not edit that original text (kept above for
the record) — it registers a NEW, structurally different economic
hypothesis under the same STRATEGY_ID = B umbrella and general
infrastructure/discipline (exit mechanics, walk-forward method, stress
method, HOLDOUT policy — all identical to Sections 5/10/11/12 above,
reused as shared infrastructure).

**New economic hypothesis**: short-term order-flow imbalance predicts
continuation. When aggressive TAKER BUY volume dominates aggressive
taker sell volume over a recent window (not just price making a new
high), this reflects informed or urgent buying pressure consuming
resting liquidity — a well-documented microstructure effect where order
flow imbalance has short-horizon price impact that persists for a few
bars before mean-reverting or being arbitraged away. This is
conceptually DIFFERENT from the rejected breakout hypothesis: it does
not require price to make a new high at all, only that the flow
composition (not the price level) is unusually one-sided.

**Entry (B1-style, simplest possible version, no ML)**: at bar `t`,
using `taker_imbalance_20` (already-existing, already-leak-free feature
from `quant_bot/features/basics.py`, smoothed 20-bar mean of
`(taker_buy_volume-taker_sell_volume)/volume`):
1. `taker_imbalance_20[t]`'s 240-bar rolling percentile rank > 0.90
   (order flow in the top decile of its own recent history — relative,
   not absolute, per this project's established preference).
2. `rel_volume_20[t] > 1.5` (real participation, avoids thin-liquidity
   noise) — same volume-confirmation filter reused from the breakout
   family for the same reason (shared infrastructure convention, not
   shared alpha).
No breakout/price-level condition at all — this is the key structural
difference from B1/B4/B7.

**Exit, risk, walk-forward, stress, HOLDOUT policy**: identical to
Sections 5/6/10/11/12 above (TRAIN-derived trailing stop, same dynamic
leverage formula, same fold construction, same stress battery, HOLDOUT
locked).

**Rejection criterion (fixed before running, same standard as B1)**:
REJECT if aggregate PF <= 1.0 on BOTH BTC and ETH with n>=30 combined.

Results in `docs/strategy_b/STRATEGY_B_RESEARCH_LOG.md`, Experiment B8
card.

---

*Original pre-registration: 2026-08-23. Revision 1: 2026-08-24.*
