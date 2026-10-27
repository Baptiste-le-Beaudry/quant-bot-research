"""
scripts/step18_btc_eth_portfolio.py — Étape 18: combine BTC and ETH's
BASELINE_CANDIDATE_V2 (unchanged, no EV filter -- that wasn't promoted,
Experiment 12) trades into ONE portfolio equity curve, interleaved by real
timestamp, rather than running each symbol as its own isolated $10,000
book. Directly motivated by Experiment 13: BTC and ETH have measurably
different stress/volatility profiles on this window, so their trade
outcomes are plausibly not perfectly correlated -- if true, a combined
book should show better risk-adjusted return (Sharpe, max DD) than either
symbol alone, even if neither symbol's own PF improves.

A prior session ran a similar H3 test (docs/autonomous_session_plan.md)
on the OLD 2yr data with the OLD dca_rescue_trend exit and found only a
"modest PF lift on 3 BTC trades, not reliable." This redoes it properly
on the CURRENT V2 architecture (7yr TRAIN, trailing+stop+time exit,
leverage), which has never been portfolio-tested this session.

Usage:
    python scripts/step18_btc_eth_portfolio.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL_PER_BOOK = 10_000.0
RISK_PCT = 0.01


def resolve(path, stop_distance, leverage):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2


def sharpe_sortino(pnls: np.ndarray, capital: float):
    per_trade = pnls / capital
    sharpe = per_trade.mean() / (per_trade.std() + 1e-12)
    downside = per_trade[per_trade < 0]
    sortino = per_trade.mean() / (downside.std() + 1e-12) if len(downside) > 1 else float("nan")
    return float(sharpe), float(sortino)


def max_dd(eq: np.ndarray, capital: float):
    running_max = np.maximum.accumulate(np.concatenate([[capital], eq]))
    dd = (np.concatenate([[capital], eq]) - running_max) / running_max
    return float(dd.min() * 100)


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min...")
    train_feats_all, train_labels_all = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats_all[symbol] = build_feature_matrix(df)
        train_labels_all[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train = pd.concat(train_labels_all.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.\n")

    per_symbol_trades = {}
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df = load_split(symbol, "train", verbose=False)
        train_feats = build_feature_matrix(train_df)
        train_proba = model.predict_proba(train_feats)
        train_selected = train_proba > THRESHOLD
        range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
        vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()
        train_close = train_df["close"].to_numpy()
        train_ema_slope = train_feats["ema_slope_20"].to_numpy()
        train_ret_1 = train_feats["ret_1"].to_numpy()
        train_filtered = (
            (train_proba > THRESHOLD)
            & (train_feats["range_pos_60"] < range_pos_cut)
            & (train_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        train_trades = build_trades_with_mae_mfe(train_close, train_filtered, train_ema_slope, train_ret_1)
        stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
        leverage = LEVERAGE[symbol]

        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()
        val_filtered = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        val_trades = build_trades_with_mae_mfe(val_close, val_filtered, val_ema_slope, val_ret_1)
        timestamps = val_df.index

        rows = []
        for t in val_trades:
            ret = resolve(t["close_path"], stop_distance, leverage)
            entry_ts = timestamps[t["entry_idx"]]
            pnl = ret * CAPITAL_PER_BOOK * RISK_PCT * leverage
            rows.append({"symbol": symbol, "entry_time": entry_ts, "pnl": pnl})
        per_symbol_trades[symbol] = pd.DataFrame(rows)
        print(f"{symbol}: {len(rows)} VALIDATION trades")

    print()
    print("=" * 100)
    print("  SOLO vs COMBINED PORTFOLIO (each symbol keeps its own registered leverage/config)")
    print("=" * 100)

    for symbol, df_t in per_symbol_trades.items():
        pnls = df_t["pnl"].to_numpy()
        eq = CAPITAL_PER_BOOK + np.cumsum(pnls)
        sharpe, sortino = sharpe_sortino(pnls, CAPITAL_PER_BOOK)
        dd = max_dd(eq, CAPITAL_PER_BOOK)
        wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
        print(f"  {symbol:<10} SOLO (${CAPITAL_PER_BOOK:,.0f} book): n={len(pnls):>3} PF={pf:>7.3f} "
              f"ret={pnls.sum()/CAPITAL_PER_BOOK*100:>+7.3f}% maxDD={dd:>+7.3f}% "
              f"sharpe={sharpe:>7.4f} sortino={sortino:>7.4f}")

    # Combined: 2x capital base (one book per symbol, run simultaneously -- NOT capital-shared/competing).
    combined = pd.concat([per_symbol_trades["ETHUSDT"], per_symbol_trades["BTCUSDT"]], ignore_index=True)
    combined = combined.sort_values("entry_time")
    combined_capital = CAPITAL_PER_BOOK * 2
    pnls_c = combined["pnl"].to_numpy()
    eq_c = combined_capital + np.cumsum(pnls_c)
    sharpe_c, sortino_c = sharpe_sortino(pnls_c, combined_capital)
    dd_c = max_dd(eq_c, combined_capital)
    wins_c, losses_c = pnls_c[pnls_c > 0], pnls_c[pnls_c <= 0]
    pf_c = float(wins_c.sum() / -losses_c.sum()) if losses_c.sum() < 0 else float("inf")
    print(f"\n  {'COMBINED':<10} (${combined_capital:,.0f} book, 2x capital, one book per symbol): "
          f"n={len(pnls_c):>3} PF={pf_c:>7.3f} ret={pnls_c.sum()/combined_capital*100:>+7.3f}% "
          f"maxDD={dd_c:>+7.3f}% sharpe={sharpe_c:>7.4f} sortino={sortino_c:>7.4f}")

    # Correlation of daily-binned PnL between symbols (rough diversification signal)
    eth_daily = per_symbol_trades["ETHUSDT"].set_index("entry_time")["pnl"].resample("1D").sum()
    btc_daily = per_symbol_trades["BTCUSDT"].set_index("entry_time")["pnl"].resample("1D").sum()
    aligned = pd.DataFrame({"eth": eth_daily, "btc": btc_daily}).fillna(0.0)
    corr = aligned["eth"].corr(aligned["btc"])
    print(f"\n  Daily PnL correlation (ETH vs BTC, days both/either had a trade): {corr:.3f}")
    print("  (near 0 or negative = real diversification benefit; near 1 = same risk, just doubled)")


if __name__ == "__main__":
    main()
