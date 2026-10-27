"""
scripts/step17_portfolio_leverage.py — Étape 17, direct follow-up to
Experiment 14: the combined BTC+ETH portfolio's max drawdown (-0.73%) beat
BOTH solo legs (-1.11% ETH, -1.05% BTC), thanks to a mildly negative daily
P&L correlation. This tests whether a UNIFORM leverage multiplier (applied
identically to both symbols' already-registered leverage, 12.1x/9.9x --
NOT a new per-asset tuning decision) can bring the combined book's
drawdown back up to roughly a single solo leg's level while capturing
more return, i.e. spending the diversification benefit rather than just
banking it as idle risk headroom.

Multiplier swept: 1.0 (baseline), 1.1, 1.2, 1.3, 1.5, 1.75, 2.0. Forced-
liquidation count is tracked at each level, since higher leverage
eventually collides with the protective stop the same way it always has
this session (STOP_OUT_FRACTION/leverage vs stop_distance).

Usage:
    python scripts/step17_portfolio_leverage.py
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
BASE_LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL_PER_BOOK = 10_000.0
RISK_PCT = 0.01
MULTIPLIERS = [1.0, 1.1, 1.2, 1.3, 1.5, 1.75, 2.0]


def resolve(path, stop_distance, leverage):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    forced = liq_move <= stop_distance
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, forced
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, False
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, False


def max_dd(eq, capital):
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

    per_symbol = {}
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
        per_symbol[symbol] = {"trades": val_trades, "timestamps": timestamps, "stop_distance": stop_distance}
        print(f"{symbol}: {len(val_trades)} VALIDATION trades, stop={stop_distance*100:.2f}%")

    print("\n" + "=" * 100)
    print("  Combined-portfolio leverage multiplier sweep (uniform across both symbols)")
    print("=" * 100)
    print(f"  {'mult':>6}{'ETH lev':>10}{'BTC lev':>10}{'n':>5}{'PF':>9}{'ret%':>9}{'maxDD%':>9}{'forced_liq':>12}")

    combined_capital = CAPITAL_PER_BOOK * 2
    for mult in MULTIPLIERS:
        rows = []
        total_forced = 0
        for symbol, data in per_symbol.items():
            leverage = BASE_LEVERAGE[symbol] * mult
            for t in data["trades"]:
                ret, forced = resolve(t["close_path"], data["stop_distance"], leverage)
                pnl = ret * CAPITAL_PER_BOOK * RISK_PCT * leverage
                entry_ts = data["timestamps"][t["entry_idx"]]
                rows.append({"symbol": symbol, "entry_time": entry_ts, "pnl": pnl})
                total_forced += int(forced)
        df_c = pd.DataFrame(rows).sort_values("entry_time")
        pnls = df_c["pnl"].to_numpy()
        eq = combined_capital + np.cumsum(pnls)
        dd = max_dd(eq, combined_capital)
        wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
        eth_lev = BASE_LEVERAGE["ETHUSDT"] * mult
        btc_lev = BASE_LEVERAGE["BTCUSDT"] * mult
        marker = "  <-- baseline" if mult == 1.0 else ""
        print(f"  {mult:>5.2f}x{eth_lev:>9.1f}x{btc_lev:>9.1f}x{len(pnls):>5}{pf:>9.3f}"
              f"{pnls.sum()/combined_capital*100:>+9.3f}{dd:>+9.3f}{total_forced:>12}{marker}")


if __name__ == "__main__":
    main()
