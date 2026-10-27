# Final crypto volatility-filter report

This report compares the untouched frozen Strategy A gate with the shortlisted 1,440-minute regime-ratio gate. The forward bot and frozen bundle were not modified.

## Current gate

The current signal requires all three conditions:

1. model probability > 0.70;
2. `range_pos_60` below the TRAIN-selected median cutoff;
3. absolute `realized_vol_30` above the TRAIN-selected median cutoff.

## Candidate gate

The candidate keeps conditions 1 and 2. It replaces condition 3 with:

`realized_vol_30 / causal rolling median(realized_vol_30, 1440 minutes) > TRAIN 75th-percentile ratio cutoff`.

The rolling median uses only current and past observations. The ratio cutoff, protective stop and leverage are calibrated only on TRAIN. Each TEST fold is evaluated once, chronologically, with the frozen trailing exit and execution costs.

## Complete 111-fold result

| Variant | Folds | Trades | Zero-trade folds | Summed independent-fold PnL | Median PF | Folds PF > 1 | Median fold DD | Weighted win rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Current absolute gate | 111 | 1,525 | 6 | $2,774.57 | 1.285 | 79 | -0.218% | 63.61% |
| Regime ratio 1,440m / TRAIN q75 | 111 | 2,815 | 1 | $1,196.64 | 1.060 | 67 | -0.391% | 58.12% |

The PnL column is a sum of independent $10,000-per-fold simulations, not a compounded live-account return. It is valid for comparing variants under identical folds and costs.

## Interpretation

The candidate does solve the inactivity problem: 1 zero-trade fold instead of 6 and 84.6% more entries. However, across the full historical walk-forward it materially reduces trade quality:

- PnL is 56.9% lower than the current gate;
- median profit factor falls from 1.285 to 1.060;
- weighted win rate falls from 63.61% to 58.12%;
- median fold drawdown is worse.

The recent-fold advantage was therefore regime-specific and does not survive the complete history. The 1,440-minute ratio must be rejected as a replacement. The no-volatility variant was also already rejected: the existing full decomposition showed 6,840 entries but lower forward quality than the current gate.

## Decision

Keep the current frozen filter. Do not change the live or paper runtime based on the adaptive-ratio experiment. The research does reveal a real design tradeoff: the absolute volatility gate creates inactive low-volatility regimes, but relaxing it historically admits many lower-quality trades. If cadence is a product requirement, the next research direction should be a separately trained low-volatility model or an explicitly regime-conditioned strategy, not simply a looser gate.

Artifacts:

- [candidate_pnl_full_1440.csv](../outputs/crypto_volatility_research/candidate_pnl_full_1440.csv)
- [candidate_pnl_full_1440_summary.csv](../outputs/crypto_volatility_research/candidate_pnl_full_1440_summary.csv)
- [CRYPTO_VOLATILITY_FILTER_RESEARCH.md](CRYPTO_VOLATILITY_FILTER_RESEARCH.md)
