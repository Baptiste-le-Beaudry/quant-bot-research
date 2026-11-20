# Crypto volatility-filter research

Status: research only. No forward-paper runtime file, frozen bundle, or deployment package was modified.

## Isolation and Git

Requested branch: `research/crypto-volatility-gates`.

Branch creation was attempted, but the workspace exposes `.git` read-only and Git could not create `.git/HEAD.lock`. `HEAD` therefore remains on `master`. All work is isolated to new research scripts, `outputs/crypto_volatility_research/`, and this document. Once Git metadata is writable, create the branch with:

```powershell
git switch -c research/crypto-volatility-gates
```

## Historical calendar concentration

Source: adopted FIXED9 walk-forward ledger `docs/multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv`.

- 2,549 trades across 176 observed calendar weeks.
- 23 zero-trade weeks (13.1%).
- Median 6 trades/week; 75th percentile 15; 95th percentile 62.25; maximum 131.
- The busiest 10% of weeks contain 48.6% of all trades.
- Annual counts: 594 in 2022, 410 in 2023, 1,145 in 2024. The partial 2025 sample contains 367 through April 7 and must not be annualized uncritically.
- Month-of-year frequency is uneven: September has 43 trades, October 60, July 94, versus November 421 and January 337. These raw calendar differences are confounded by volatility regimes and unequal symbol history; they are descriptive, not a trading rule.
- Weekday quality is also uneven (Monday raw win rate 71.98%, Thursday 63.14%), but no weekday filter was optimized or recommended.

Conclusion: “at least one trade per week on average” was never equivalent to a stable weekly cadence. Historical activity was strongly clustered.

## Intraday and calendar observations

The entry-time audit uses UTC timestamps from the same ledger. Activity is concentrated around 13:00–18:00 UTC and 00:00–02:00 UTC. The strongest average raw returns per trade occurred around 07:00, 10:00 and 18:00 UTC; 19:00 UTC was weakest. Weekday raw win rates were highest Monday and Friday and lowest Thursday. Month counts were highest in November, January and December and lowest in September, October and July. These patterns are descriptive and heavily confounded by volatility regime; no hour/day/month filter has been adopted.

Weekly activity and quality move in opposite directions: the least-active quartile averaged 1.8 trades/week and 79.7% wins, while the most-active quartile averaged 48.9 trades/week and 68.6% wins. High-activity weeks generated more total raw PnL because they contained many more trades, not because each trade was better.

## Existing full walk-forward ablation

The existing 111-fold, nine-symbol component decomposition already gives a full-history controlled comparison:

- Full Strategy A (`RF + range + absolute vol`): 1,525 independent entries, weighted 10-minute win rate 61.97%, median fold 10-minute return 0.3763%.
- Remove volatility only (`RF + range`): 6,840 entries, weighted win rate 59.27%, median fold return 0.1879%.

Removing volatility multiplies entries by 4.49 but roughly halves the median fold forward return and lowers win rate by 2.70 percentage points. The volatility gate protects signal quality, even though its absolute form produces long inactive regimes.

## Adaptive-gate screening design

The screen uses the last two walk-forward TEST folds of every FIXED9 symbol: 18 fully out-of-sample folds. Models and range cuts are fit/calibrated on TRAIN only. The alternatives are:

- current absolute TRAIN-median cutoff;
- no volatility cutoff;
- causal rolling percentiles with windows 240, 1,440, 10,080 and 43,200 minutes and thresholds 50%, 60%, 70%, 80%;
- causal volatility/rolling-median regime ratios for the same windows, with ratio cutoffs calibrated at TRAIN-selected quantiles 25%, 50%, 75%.

This is 30 configurations. Rolling calculations use only the current and previous rows; no future values or HOLDOUT rows are used.

The controlled removal test is included explicitly as `no_vol_filter`. The existing full-history component decomposition independently confirms its effect: removing volatility produced 6,840 entries versus 1,525 for the full gate, but lowered weighted 10-minute win rate from 61.97% to 59.27% and median fold forward return from 0.3763% to 0.1879%.

## Recent-fold screen results

Current absolute gate:

- 560 independent entries;
- one zero-trade fold;
- weighted 10-minute win rate 61.07%;
- median fold 10-minute return 0.2738%.

No volatility gate:

- 2,142 entries;
- no zero-trade folds;
- weighted win rate 56.26%;
- median fold return 0.0991%.

Leading adaptive candidates:

1. Regime ratio, 240-minute median, TRAIN 75th-percentile cutoff: 701 entries, no zero folds, 63.20% win rate, 0.2594% median fold return.
2. Regime ratio, 1,440-minute median, TRAIN 75th-percentile cutoff: 739 entries, no zero folds, 61.84% win rate, 0.3194% median fold return.
3. Regime ratio, 43,200-minute median, TRAIN 75th-percentile cutoff: 592 entries, one zero fold, 61.66% win rate, 0.3700% median fold return.
4. Regime ratio, 10,080-minute median, TRAIN 75th-percentile cutoff: 669 entries, one zero fold, 61.58% win rate, 0.3443% median fold return.

Rolling-percentile gates and looser 25%/50% regime-ratio gates generally recovered many entries but diluted quality toward 56–60% win rates. They are not leading candidates.

## Decision

- Reject immediate removal of the volatility filter.
- Do not modify the current forward bot yet.
- Advance only the four TRAIN-q75 regime-ratio candidates to full-fold exit/PnL, drawdown, stress, portfolio-overlap, and recent-regime validation.
- Treat the 240-minute candidate cautiously: its strong recent-fold win rate comes with a lower MFE/MAE ratio than the current gate and may be reacting to short-lived noise.

The recent-fold screen is complete. Full exit/PnL validation of the shortlisted regime-ratio candidates has been started separately and remains research-only; no candidate has been promoted.

## Recent-fold exit/PnL validation

The 18 most recent TEST folds (two per FIXED9 symbol) were replayed with TRAIN-only stop calibration and the frozen trailing exit:

| Variant | Trades | PnL on $10k/fold | Median PF | Median max DD | Win rate |
|---|---:|---:|---:|---:|---:|
| Current absolute | 560 | $1,374 | 1.386 | -0.380% | 65.0% |
| No volatility filter | 2,142 | $571 | 1.113 | -1.163% | 54.2% |
| Regime ratio 240m / TRAIN q75 | 701 | $1,378 | 1.357 | -0.470% | 58.2% |
| Regime ratio 1,440m / TRAIN q75 | 739 | **$1,580** | **1.572** | -0.383% | 59.4% |
| Regime ratio 10,080m / TRAIN q75 | 669 | $1,225 | 1.716 | -0.403% | 60.2% |
| Regime ratio 43,200m / TRAIN q75 | 592 | $1,085 | 1.623 | -0.381% | 61.8% |

These are recent-fold research results, not a final promotion decision. The 1,440-minute ratio is the current leading candidate because it improves total PnL and PF without the drawdown expansion seen when the volatility filter is removed. It still needs the full historical fold validation before any paper-bot change.

Artifacts:

- `outputs/crypto_volatility_research/seasonality_annual.csv`
- `outputs/crypto_volatility_research/seasonality_weekly.csv`
- `outputs/crypto_volatility_research/seasonality_month_of_year.csv`
- `outputs/crypto_volatility_research/seasonality_weekday.csv`
- `outputs/crypto_volatility_research/gate_variant_recent_folds.csv`
- `outputs/crypto_volatility_research/gate_variant_recent_summary.csv`
