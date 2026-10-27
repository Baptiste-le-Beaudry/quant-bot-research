# quant_bot — a research bot that did not find a tradable edge (and shows why)

*[Version française : README.fr.md](README.fr.md)*

A full crypto + equity research bot, built walk-forward by construction: feature engine,
decision-tree models (random forest, XGBoost, logistic baseline), backtest engine, honest
execution harness, paper-trading runners, and **every experiment, including the rejected ones**.

**Verdict, stated up front:** after roughly 80 experiments, **no net, executable,
forward-confirmed edge exists** for a small account. Crypto and equity are hard because the gross
edge we found (a few hundredths of a percent per trade) is the same size as realistic costs and
fill error. The repository documents how we got there so you can skip the same dead ends.

> Paper trading only. Not investment advice. No real order is ever placed.

## The headline lesson

2,549 trades, profit factor **1.38** in the research backtest. Same trades, stops filled the way an
exchange would fill them: **0.95**. Equity: 1.21 to about 1.04. See
`docs/SCIENTIFIC_VALIDATION_AUDIT.md` and the companion tool
[fill-reality-check](https://github.com/Baptiste-le-Beaudry/fill-reality-check).

## Why it is so hard to find an edge (crypto and equity)

- **Costs are the same size as the edge.** Gross edge is about 0.11 to 0.35 % per trade; realistic round-trip costs are about 0.05 to 0.25 %. Equity brokers for a small account cost about 0.46 % round trip against a 0.03 to 0.05 % gross edge (Exp 62: rejected).
- **Statistical power.** An edge of about 0.11 % per trade with about 1.6 % volatility needs roughly 1,165 trades (about 5.5 years of clean flow) to confirm.
- **Fills.** Stops checked on the close but filled at the stop level, gaps ignored, signals taken across data gaps (21 of 25 live signals in one test were data-gap artefacts).
- **Burned holdouts.** A holdout that has been seen can only reject ideas. Boundaries live in `quant_bot/data/splits.py`.
- **Solo edge is not portfolio edge.** Several strategies looked fine alone and added nothing to the portfolio.
- **Selection effects.** Many variants tested on one history; in-sample numbers are treated as rejection evidence only.

## What was tested

Full log with numbers: `docs/research_plan_status.md` (Experiments 0-36) and `scripts/agents/` (Experiments 52-82).

| Family | Result |
|---|---|
| **Strategy A**: crypto mean-reversion (dip buying), random-forest signal plus volatility filter, trailing or time exit | The most promising. An edge exists in-sample, mostly from the filter x model interaction and exit asymmetry. With realistic fills it is about 0 net. Best candidate: 50-minute time exit on SOL (+0.146 %/trade, PF 1.21 in-sample). Not confirmed forward. |
| Strategy A-Equity: same idea on 15 US equities (Dukascopy) | Real own-asset edge in walk-forward (9/15, then 12/16 on independent confirmation), but **rejected for a 500 CAD account** after broker costs. |
| Strategy B: momentum / breakout | Rejected. |
| Strategy C: QQQ/SPY order-book microstructure | Rejected; the lead reversed sign on SPY. |
| Universe expansion (ETC/TRX/DOT, TSLA/NVDA/MSTR/leveraged ETFs) | Rejected; the transfer theory was not validated. |
| Exit timing (4 approaches) | Rejected; the deployed 50-minute exit was confirmed three ways. |
| Commodities, prediction markets, daily momentum, residual dip, regime filters, label variants, tail risk, noise momentum, leveraged trend, volatility targeting | Rejected or inconclusive; see the log. |
| Funded-account challenges (backtested) | Negative once realistic fills are used. |

## The models (all in code)

- `quant_bot/signal/model.py`: logistic-regression baseline, **random forest** (shallow, regularised) and XGBoost, trained walk-forward.
- `quant_bot/features/`: feature engine and labels (labels are net of costs; a NaN-label bug is covered by a regression test).
- `quant_bot/backtest/`, `quant_bot/execution_harness/`: engines, cost model, one shared execution harness (intrabar stops, gaps, per-platform costs with sources).
- `quant_bot/forward/`, `quant_bot/live/`, `quant_bot/risk/`: paper-trading runner, guards, portfolio caps. `live_enabled=false`.
- `scripts/`: every experiment as a runnable script. `scripts/audit/`: static scanners for lookahead and NaN-boolean bug classes.

## Layout

```
SPEC.md                    original specification
quant_bot/                 library (features, signal, backtest, harness, forward, risk)
scripts/                   experiment scripts and the phase 1-7 pipeline
scripts/agents/            experiments 52-82
scripts/audit/             static bug scanners
tests/                     regression tests, including the real bugs found
docs/                      research log, audit, strategy index, exit-realism tables
```

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q
python scripts/download_data.py --symbol BTCUSDT --days 730   # public Binance data, no key
```

Data is not included. Scripts expect the layout described in `SPEC.md`; paths can be set with
environment variables such as `QB_BAR_CACHE`. This is research code: some scripts need datasets
you must download first.

## Status

Research is frozen. The next step would be a forward test long enough to have statistical power,
not another backtest. Issues and questions are welcome.

MIT licence. See `LICENSE`.
