"""
scripts/diagnostic_patterns.py — two questions about the trade sequence
that hadn't been checked: (1) is there autocorrelation in win/loss outcomes
(streaks), and specifically would reversing direction after N consecutive
losses/wins help? (2) is there a feature-level pattern common to winners vs
losers, beyond the aggregate PF/win-rate numbers already reported?

Uses the h=10min, threshold=0.75 configuration (docs/diagnostic_waterfall
result — the clearest "real gross edge, eaten by costs" case, n=314 on
VALIDATION) for the feature analysis, and threshold=0.65 (n=16279, more
statistical power for streak counting) for the streak analysis.

Usage:
    python scripts/diagnostic_patterns.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.backtest.engine import simulate
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOL = "ETHUSDT"
TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST


def streak_analysis(returns: np.ndarray, max_streak: int = 5) -> None:
    wins = returns > 0
    n = len(wins)
    overall_win_rate = wins.mean()
    print(f"Overall win rate: {overall_win_rate*100:.1f}% (n={n})\n")

    print("Autocorrelation of win/loss outcome sequence (lag 1-5):")
    outcomes = wins.astype(float)
    for lag in range(1, 6):
        if n > lag + 10:
            ac = np.corrcoef(outcomes[:-lag], outcomes[lag:])[0, 1]
            print(f"  lag {lag}: {ac:+.4f}")
    print("  (near 0 = no streakiness either way; positive = wins cluster with wins;")
    print("   negative = wins tend to follow losses and vice versa)\n")

    print("Conditional win rate after a streak (vs. overall baseline):")
    for streak_len in range(2, max_streak + 1):
        after_losses, after_wins = [], []
        for i in range(streak_len, n):
            window = wins[i - streak_len:i]
            if (~window).all():
                after_losses.append(wins[i])
            elif window.all():
                after_wins.append(wins[i])
        al_rate = np.mean(after_losses) * 100 if after_losses else float("nan")
        aw_rate = np.mean(after_wins) * 100 if after_wins else float("nan")
        print(f"  after {streak_len} losses in a row (n={len(after_losses)}): "
              f"win rate = {al_rate:.1f}%  |  "
              f"after {streak_len} wins in a row (n={len(after_wins)}): win rate = {aw_rate:.1f}%")

    print(f"\nExplicit test: reverse direction after a {max_streak}-loss or {max_streak}-win streak")
    print(f"(reversed_return = -original_return - 2*cost, since cost is paid either way):")
    baseline_pf = _pf(returns)
    modified = returns.copy()
    n_reversed = 0
    for i in range(max_streak, n):
        window = wins[i - max_streak:i]
        if window.all() or (~window).all():
            modified[i] = -returns[i] - 2 * COST_PCT
            n_reversed += 1
    modified_pf = _pf(modified)
    print(f"  {n_reversed} of {n} trades would have been reversed")
    print(f"  Baseline PF: {baseline_pf:.3f} | With reversal rule: {modified_pf:.3f}")
    print(f"  Baseline total return (sum): {returns.sum()*100:.3f}% | "
          f"With reversal: {modified.sum()*100:.3f}%")


def _pf(returns: np.ndarray) -> float:
    wins, losses = returns[returns > 0], returns[returns <= 0]
    gl = -losses.sum()
    return float(wins.sum() / gl) if gl > 0 else float("inf")


def feature_pattern_analysis(feats: pd.DataFrame, entry_times: list, returns: np.ndarray) -> None:
    entry_feats = feats.loc[feats.index.isin(entry_times)].reindex(entry_times)
    wins_mask = returns > 0

    print(f"\nFeature comparison: winners (n={wins_mask.sum()}) vs losers (n={(~wins_mask).sum()})")
    winners_mean = entry_feats.loc[wins_mask].mean()
    losers_mean = entry_feats.loc[~wins_mask].mean()
    winners_std = entry_feats.loc[wins_mask].std()
    losers_std = entry_feats.loc[~wins_mask].std()
    gap = (winners_mean - losers_mean)
    pooled_std = np.sqrt((winners_std**2 + losers_std**2) / 2).replace(0, np.nan)
    standardized_gap = (gap / pooled_std).sort_values(key=abs, ascending=False)

    print(f"\n{'feature':<24}{'winners_mean':>14}{'losers_mean':>14}{'gap(std units)':>16}")
    for feat in standardized_gap.index:
        print(f"{feat:<24}{winners_mean[feat]:>14.4f}{losers_mean[feat]:>14.4f}{standardized_gap[feat]:>16.3f}")
    print("\n(gap in standard-deviation units -- >0.2 or so is worth a look, this is a")
    print(" small sample so treat as directional, not confirmatory)")


def main():
    print("Fitting tier-2 classifier, horizon=10min (the clearest gross-edge case)...")
    train_feats, train_labels = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.\n")

    df_val = load_split(SYMBOL, "validation", verbose=False)
    feats_val = build_feature_matrix(df_val)
    close_val = df_val["close"]
    proba = model.predict_proba(feats_val)

    print("=" * 70)
    print("  PART 1: streak / autocorrelation analysis (threshold=0.65, more data)")
    print("=" * 70)
    m65 = simulate(close_val, proba, HORIZON, 0.65, capital=10_000.0, risk_pct=0.01, cost_pct=COST_PCT)
    streak_analysis(m65["trade_returns"], max_streak=5)

    print("\n" + "=" * 70)
    print("  PART 2: feature pattern in winners vs losers (threshold=0.75, the")
    print("  configuration with a real measured gross edge)")
    print("=" * 70)
    m75 = simulate(close_val, proba, HORIZON, 0.75, capital=10_000.0, risk_pct=0.01, cost_pct=COST_PCT)
    print(f"n_trades={m75['n_trades']}, win_rate={m75['win_rate_pct']}%, PF={m75['profit_factor']}")
    feature_pattern_analysis(feats_val, m75["trade_entry_times"], m75["trade_returns"])


if __name__ == "__main__":
    main()
