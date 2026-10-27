# Quant Bot V1 — Cahier des charges

Status: sections 1-13's three open questions are answered (see section 13a).
Nothing beyond the data-download plumbing, the exchange-adapter
abstraction, and reused utilities has been implemented yet — features,
labels, and models still wait on this document being read, per the plan's
own "cahier des charges before code" instruction.

## 0. Why this document exists

The previous bot (`confluence_ai_v3`) taught three expensive lessons the hard
way, after weeks of work:

1. A training-label bug (79% of pretraining samples were uninformative
   "neither TP nor SL hit" placeholders) silently collapsed the neural net to
   a near-constant output for years of backtests before anyone noticed —
   because nobody checked prediction *variance*, only backtest P&L.
2. The main backtest engine pretrained on the *entire* dataset before walking
   through it chronologically — a lookahead bug that inflated every headline
   number in that repo (`backtest_h1_9y` claiming +15%, etc.) until a proper
   walk-forward split (train N days → test next 2 days → slide) was used,
   which is the only number that turned out to be trustworthy.
3. "More indicators" and "more trades" both made things *worse*, not better.
   The only backtests with a real edge (PF > 1) were the low-frequency,
   high-conviction ones.

Everything below is designed so these three mistakes can't happen silently
again: label sanity checks are mandatory, the backtest engine is walk-forward
by construction, and feature count is capped with an explicit redundancy
check rather than "add more and see."

## 1. Objective & how success is measured

> Build a system that discovers, validates, and exploits a real statistical
> edge — not a bot that tries to predict price.

Success is judged in this order (matches the plan's Phase 10, this order is
the important part — a bot is not "done" just because step 6 is positive):

1. Statistically real edge (survives a train/validation split, not just an
   optimized single backtest)
2. Out-of-sample robustness (walk-forward across regimes, not one window)
3. Survives realistic costs (fees + slippage + funding)
4. Acceptable drawdown (we'd rather have Bot B: +80%/-15% DD than Bot A:
   +150%/-70% DD, exactly as the plan says)
5. Stable across regimes (trend, range, high-vol, low-vol — not just the
   regime that happened to dominate the backtest window)
6. Profitability, and specifically: **beats buy-and-hold of the traded
   instrument over the same period.** If it can't clear that bar in
   backtest + walk-forward, it does not go to paper trading.

## 2. Market & venue — decided, not open

**Binance USDT-margined Perpetual Futures, BTCUSDT and ETHUSDT.**

Reasoning (this is the one concrete decision I made rather than leaving
open, because it determines what data is even possible to get):

- The plan's feature wishlist explicitly wants funding rate, open interest,
  and liquidations. Those are perpetual-futures-native concepts — a spot
  exchange or an MT5 CFD broker (what `confluence_ai_v3` used, `BTCUSD` as a
  synthetic CFD symbol) cannot provide them. Perpetual futures is the only
  choice that makes Phase 4's DSP/order-flow ambitions actually buildable.
- Binance specifically: deepest liquidity of any venue for these two pairs,
  free public REST endpoints for historical klines, funding rate history,
  and open interest history — no API key needed for research/backtesting,
  only for live/paper execution later.
- Single market first (BTCUSDT), ETHUSDT as the out-of-sample sanity check
  once BTCUSDT shows a real edge — exactly the plan's Phase 1 sequencing.
  Do not add a third market until BTCUSDT's edge survives walk-forward.

**Confirmed decision (see section 13a): Binance USDT-M Futures stays as the
data/research venue. It is explicitly NOT assumed to be a legal
live-execution venue** — Binance withdrew from Canada in 2023 and cannot
legally onboard Canadian residents (Quebec included) for trading, retail
derivatives access being additionally restricted by Canadian regulators on
top of that. Confirmed via web search this session, sources in section 13a.

This only affects `quant_bot/live/` (Phase 12, still far off). Public
market-data endpoints (klines, funding, open interest) need no account and
carry no legal exposure — nothing about the venue decision above changes.
What *does* change: every execution path is written against
`quant_bot.live.exchange_adapter.ExchangeAdapter` (implemented this
session), never against a specific exchange's SDK directly.
`BinanceFuturesAdapter` implements the read-only data methods for real, but
its order/balance/position methods deliberately raise `NotImplementedError`
referencing this section — so live trading cannot silently "just work"
through it. When a compliant venue is confirmed (a Canada-registered
platform, an MT5 CFD broker as `confluence_ai_v3` used, or a different
jurisdiction's account), it's a new adapter class, not a rewrite of
backtest/risk/signal/management code.

## 3. Data engine (Phase 2)

Reused as-is: `download_history.py`'s Binance klines downloader (already in
`confluence_ai_v3`, no API key required, already proven — copied into
`quant_bot/data/download_klines.py`).

New, to add:
- Funding rate history: `GET /fapi/v1/fundingRate` (free, no key)
- Open interest history: `GET /futures/data/openInterestHist` (free, no key,
  max 30 days per request — needs chunked pagination like the klines
  downloader already does)
- Liquidation events: `GET /fapi/v1/allForceOrders` gives limited recent
  history only; full liquidation history realistically needs a paid data
  vendor (e.g. CoinGlass, Kaiko) or your own long-running collector. **V1
  ships without a liquidation feature** — flagged as a later addition once
  the base signal shows an edge, not a blocker for V1.
- Order book depth: not pulled historically (Binance doesn't offer historical
  L2 depth for free) — if this becomes important, it requires either a live
  websocket collector running continuously from today forward, or a paid
  vendor. **Also deferred past V1.**

Minimum stored columns per bar: `open, high, low, close, volume, timestamp,
taker_buy_volume, taker_sell_volume` (the last two ARE available for free on
Binance klines responses — `confluence_ai_v3`'s downloader discards them
today; V1's downloader keeps them, since they're the cheapest available proxy
for real order-flow imbalance without needing tick data).

Base resolution: **1-minute perpetual futures klines** (spot klines are not
pulled in V1 — spot/perp basis as a feature is a plausible later addition,
not needed for the baseline). Multi-horizon features (1min/5min/15min
returns etc.) are computed *from* the 1-minute series, not downloaded
separately — one source of truth, no resampling drift.

Data cleaning checklist (new — v3 never had this as an explicit step):
- No gaps > 2 minutes without being flagged (Binance downtime, not silently
  forward-filled)
- No zero-volume bars treated as real ticks
- Funding/OI series aligned to kline timestamps with an explicit
  as-of/backward join (never forward-looking)

**Confirmed decision on data depth (section 13a): phased, not maximal
upfront.** Iteration (Phases 3-7, feature engineering and model tiers 1-3)
runs on ~12-24 months of history — enough to be meaningful, cheap enough to
re-download and re-process quickly while features/labels are still
changing. This session downloaded 730 days (~24 months) of BTCUSDT and
ETHUSDT 1-minute klines plus funding history as that working set. Once a
tier's out-of-sample edge looks stable, final validation (section 8's
holdout + a fresh walk-forward pass) re-runs on the deepest reliable history
available before anything is trusted — the 24-month set is for fast
iteration, not the number that decides whether the strategy works.

## 4. Architecture

```
              MARKET DATA (Binance USDT-M Futures: BTCUSDT, ETHUSDT)
                      |
          +-----------+-----------+
          |                       |
       PRICE (klines)        ORDER FLOW PROXY (taker buy/sell vol,
          |                  funding, open interest)
          +-----------+-----------+
                      v
                FEATURE ENGINE  (quant_bot/features/)
                      |
       +--------------+---------------+
       v              v               v
   Momentum       Volatility         DSP
   /Trend         /Regime          (quant_bot/features/dsp.py)
       |              |               |
       +--------------+---------------+
                      v
              REDUNDANCY PRUNING (correlation / mutual-info filter,
              quant_bot/features/pipeline.py — this step is mandatory,
              not optional, see section 5)
                      v
                REGIME MODEL   (quant_bot/regime/)   -- IA #1
                      v
                SIGNAL MODEL   (quant_bot/signal/)   -- IA #2
                      v
              P(win) / EDGE ESTIMATE
                      v
              RISK MANAGEMENT (quant_bot/risk/)  -- sizing + kill switch
                      v
               POSITION SIZE
                      v
          MANAGEMENT MODEL (quant_bot/management/) -- IA #3 (exit timing)
                      v
                  EXECUTION (quant_bot/live/)
                      v
                  BINANCE
                      v
        MONITORING (quant_bot/monitoring/) -> decision log -> DASHBOARD
                                                            -> TELEGRAM
                      |
                      +--> feeds back into RESEARCH / next walk-forward cycle
```

Three separate models (regime / signal / management), exactly as the plan
specifies — each with a narrow, testable question, instead of one model
trying to do everything (this mirrors the one thing that *did* work in
`confluence_ai_v3`: its position-management model was already separate from
its entry model, and that separation made both easier to debug).

## 5. Feature set V1 (target: 20-30 features, pruned)

The rule, stated precisely so it's checkable: after computing the full
candidate list below, compute the pairwise correlation matrix (and/or mutual
information with the label) and **drop any feature with |correlation| > 0.9
to an already-kept feature**, keeping the one with higher standalone mutual
information with the label. This is the concrete implementation of "if RSI,
MACD, EMA, Stochastic and CCI all say the same thing, that's one piece of
information repeated five times" — run the check, print the dropped list,
keep it in the repo as a record (`quant_bot/features/redundancy_report.md`,
regenerated each time the feature set changes).

Candidate families (this is the input list *before* pruning — expect V1 to
ship with fewer than what's listed here):

**Price / momentum**
- Return over 1min, 5min, 15min, 1h (log returns)
- Distance to VWAP (session and rolling)
- Distance to EMA20 / EMA50 / EMA200
- Distance to recent N-bar high/low
- Slope of a short linear regression on close (structure/trend proxy)

**Volume / order-flow proxy**
- Relative volume (vs rolling average)
- Volume acceleration (2nd derivative)
- Taker buy volume − taker sell volume, normalized (the free order-flow
  proxy from section 3)
- Volume-to-realized-volatility ratio

**Volatility / regime**
- ATR, realized volatility (rolling stdev of returns)
- Average range vs its own rolling average (expansion/contraction)
- Bollinger/Keltner squeeze state (reused concept from `confluence_ai_v3`,
  it was one of the few filters never shown to hurt)

**Structure**
- Breakout distance from N-bar range
- Pullback depth after a breakout
- Distance to nearest support/resistance (swing high/low based, not the
  Fibonacci/Gann features from `confluence_ai_v3` — those never showed
  measurable standalone value there and are dropped)

**DSP (the actually-new part vs. `confluence_ai_v3`)**
- Dominant FFT frequency and its spectral power, over a rolling window
  (e.g. 128 or 256 bars)
- Ratio of low-frequency to high-frequency spectral energy
- Rolling autocorrelation at a few fixed lags
- Hurst exponent (rolling, R/S or variance-ratio estimator) — this doubles
  as the regime-detection input for IA #1 (trend H>0.55 / mean-revert
  H<0.45 / uncertain in between, per the research from the previous
  session)
- Hilbert-transform instantaneous phase/amplitude (optional stretch item —
  build after the simpler DSP features are shown to carry signal, not
  before)

**Explicitly NOT carried over from confluence_ai_v3:** Fibonacci position,
Gann angle, Ichimoku score, Order Block / FVG zone detection. These made up
6 of the old bot's 13 features and none were ever individually validated —
they were carried on faith. If you want them back, they go through the same
redundancy/mutual-information gate as everything else, not back in for free.

## 6. Label / target definition (Phase 4/6)

Primary target, exactly as proposed, with the horizon as a parameter, not a
constant baked into the formula:

```
y(h) = 1[ R_forward(h) > cost_threshold ]      h in minutes
cost_threshold = round_trip_fee + expected_slippage   (see section 9)
```

modeled as a probability via the signal model: `P(R_h > cost_threshold)`.

**Confirmed decision (section 13a): h=10min is the working baseline, not a
locked-in choice.** Before any feature-engineering effort gets spent
optimizing around 10 minutes specifically, Phase 3 (the no-AI baseline)
must run a horizon-selection experiment: for each candidate in
`quant_bot.config.LABEL_HORIZON_CANDIDATES` (5, 10, 15, 30 minutes),
measure a model-free predictability statistic (e.g. mutual information or
simple correlation between the obvious features — momentum, VWAP distance,
realized vol — and the forward return at that horizon) and report which
horizon actually carries the most signal before committing to it. Every
label/feature function in `quant_bot.features` and `quant_bot.signal` must
accept `horizon_min` as an argument for this reason — nothing hardcodes 10.

This replaces `confluence_ai_v3`'s TP/SL-barrier label (which is exactly
where its bug lived: unresolved barrier touches got silently kept as
"neutral" training examples and dominated the loss). The forward-return
label above has **no unresolved case** — every bar has a real, computable
forward return. That category of bug structurally cannot recur with this
label design.

Symmetric short-side label: `y_short = 1[ R_forward(10min) < -cost_threshold ]`.

Secondary target (for the management model, IA #3, once a position is open):
expected R-multiple of holding vs. exiting now — same counterfactual-once-
resolved design `confluence_ai_v3`'s position manager already used
successfully; that piece is worth porting in concept.

## 7. Modeling roadmap (Phase 6) — promotion criteria, not a wishlist

Each tier must **beat the previous tier's validated out-of-sample Sharpe**
(on the walk-forward protocol in section 8) to justify the added complexity.
If Logistic Regression already clears the buy-and-hold bar, that may be all
V1 needs — added complexity is not automatically better, and every added
layer is another way to overfit.

| Tier | Model | Promote to next tier only if |
|---|---|---|
| 1 | Logistic Regression | baseline; always build this first |
| 2 | Random Forest | beats tier 1's OOS Sharpe by a real margin, not noise |
| 3 | XGBoost / LightGBM | beats tier 2 OOS |
| 4 | Small neural net | beats tier 3 OOS — and only with the label-sanity
|   |                    | check from section 10 passing first |
| 5 | Sequence model (if 1-4 all plateau) | last resort, most overfit risk |

Three separate models per the architecture diagram: regime (IA#1), signal
(IA#2), management (IA#3) — each gets its own tier progression, they are not
required to be the same model class.

## 8. Backtesting protocol (Phase 7/8) — the part that matters most

Chronological split, touched in this order only:

```
ALL DATA (oldest -> newest)
   |
   +-- 60% TRAIN        (feature/model iteration happens here, freely)
   +-- 20% VALIDATION   (used to pick hyperparameters / promote tiers)
   +-- 20% FINAL HOLDOUT (touched exactly once, after everything else is
                           frozen — if the strategy is changed after seeing
                           this, it is no longer a valid holdout and a new
                           holdout window must be carved out)
```

Within TRAIN+VALIDATION, walk-forward exactly like the working half of
`confluence_ai_v3`'s validation (`walk_forward.py`, ported/rewritten for the
new feature set): train on a rolling N-day window, test on the next unseen
M days, slide forward, concatenate results. **No single-shot
pretrain-on-everything-then-walk** — that was the exact bug that made
`confluence_ai_v3`'s headline backtest numbers untrustworthy.

Every backtest report must include, non-negotiably:
- Buy-and-hold return of the same instrument over the same calendar period
  (added to `confluence_ai_v3` only in the last session — ship it from day 1
  here)
- Number of trades (flag anything under ~100 as low-confidence, per the
  research from last session)
- Profit factor, Sharpe, Sortino, max drawdown, expectancy/trade

## 9. Transaction costs (Phase 9) — modeled from the start, not bolted on

- Binance USDT-M futures taker fee: 0.05% per side (0.10% round trip) at
  base tier — confirm current tier/BNB-discount before trusting this exactly
- Maker fee: 0.02% per side, if the strategy can realistically use limit
  entries (worth testing both)
- Slippage: model as a function of order size vs. recent volume, not a flat
  constant — start conservative (e.g. 1-2 ticks) and calibrate against paper
  trading fills once that phase starts
- Funding: perpetuals accrue funding every 8h while a position is held —
  must be included in any multi-hour hold's P&L, pulled from the funding
  rate history in section 3

`cost_threshold` in section 6's label uses round-trip fee + slippage
estimate; funding is applied in backtest P&L directly rather than baked into
the label (it depends on hold duration, which isn't known at entry time).

## 10. Label/model sanity checks — mandatory, not optional

Directly born from the bug that cost the last bot months of trustworthy
numbers. Before trusting *any* backtest result:

1. Print the label distribution (class balance) before training — if one
   class is >70% of samples, stop and reconsider before training on it.
2. Print the trained model's prediction distribution (min/max/mean/std) on a
   held-out slice — if std is near zero, the model is not using its inputs;
   do not proceed to backtest a degenerate model.
3. Feature importance / permutation importance on the validation set for
   every promoted model — a feature that never matters should be pruned
   from the redundancy list (section 5), not kept "just in case."

## 11. Risk management (Phase 10/11)

- Position size: `size = f(P_win, volatility, current_drawdown)` — start
  with a simple fractional-Kelly cap (e.g. quarter-Kelly, capped at 1% of
  equity risked per trade) rather than full Kelly, which is well known to be
  too aggressive for parameter estimates this noisy
- Single market, single concurrent position in V1 (no portfolio-level
  correlation risk yet — add only once BTCUSDT+ETHUSDT both show
  independent edges)
- Kill switch — bot goes flat and stops opening new positions if:
  - Daily loss exceeds a configured % of equity
  - WebSocket/REST connection lost or data goes stale beyond a timeout
  - Incoming bar data is anomalous (price jump beyond N standard deviations
    with no matching volume, gap detection from section 3)
  - Spread or slippage on recent fills exceeds a configured threshold
  - Realized volatility exceeds a configured multiple of its rolling average
    (regime the model wasn't validated on)

## 12. Monitoring & reuse from confluence_ai_v3

Directly reused, adapted only where variable names differ:
- **`dashboard.py`** → `quant_bot/dashboard/` — the web dashboard
  (equity curve, trades table, diagnostics-why-no-trade panel, learning
  curve panel, adaptive-position panel all built last session) is
  architecture-agnostic; it just needs the new feature/score names fed into
  `bot_data.update_symbol()`/`add_learning_point()` instead of the old ones.
- **`telegram_notify.py`** → `quant_bot/notify/` — trade open/close/signal
  messages, reused as-is with new field names.
- **Decision logging** (Phase 13's example) is new — port the *idea* from
  `confluence_ai_v3`'s diagnostic panel (which already logs *why* a trade
  was or wasn't taken) but extend it to log the full feature vector + regime
  + signal probability + chosen size for every decision, not just entries
  that were blocked.

## 13. What ships in this session vs. what's next

Done now: this spec, the project skeleton, the reused dashboard/telegram
utilities, the Binance historical data downloader (klines, funding, open
interest — 24 months of BTCUSDT + ETHUSDT downloaded as the working
dataset), and the `ExchangeAdapter` abstraction (section 2) with a Binance
implementation whose live-order methods are deliberately disabled.

Explicitly NOT done yet, waiting on the no-AI baseline (Phase 3): feature
engine implementation, redundancy pruning, label construction, any model
training, backtest engine port. Building those before Phase 3 confirms the
data actually contains an edge is exactly the "start coding immediately"
trap the plan itself warns against.

### 13a. Decisions (previously open questions, now answered)

1. **Venue:** Binance USDT-M Futures stays as the data/research venue.
   Confirmed NOT a legal live-execution venue for Canadian residents —
   Binance withdrew from Canada in 2023 (existing accounts withdrawal-only)
   and Canadian regulators separately restrict retail derivatives access;
   this applies province-wide, Quebec included. Section 2 updated with the
   `ExchangeAdapter` abstraction so the execution venue is swappable later
   without touching data/features/models. Sources: [Binance Unavailable in
   Canada 2026](https://www.bitget.com/amp/academy/binance-canada-availability-regulation-guide-2026),
   [Is Binance Legal in Canada or is it Still Banned in
   2026?](https://www.savvynewcanadians.com/is-binance-legal-in-canada/) —
   verify current status yourself before relying on this for anything
   beyond architecture decisions; this is not legal advice.
2. **Label horizon:** 10 minutes stays as the working baseline (section 6),
   but is a parameter (`horizon_min`) everywhere, not a constant. Phase 3
   must run the horizon-selection experiment across
   `LABEL_HORIZON_CANDIDATES = [5, 10, 15, 30]` before any feature-tuning
   effort gets spent assuming 10 is correct.
3. **Data depth:** phased. ~12-24 months for iteration (Phases 3-7) — this
   session's 24-month BTCUSDT/ETHUSDT download is that set. Deepest
   reliable history gets pulled and walk-forward-validated once a tier's
   edge looks stable (section 8), not before.

Next step: Phase 3, the no-AI baseline — before building any feature engine
or model, check whether simple momentum/mean-reversion/breakout rules show
*any* edge on the 24-month dataset, and run the horizon-selection experiment
from decision 2 above alongside it.
