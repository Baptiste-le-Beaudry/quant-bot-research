"""
scripts/leverage_trailing_combined.py — step 3 of the trailing-stop
follow-up: the leverage/protective-stop calibration in
scripts/leverage_with_stop.py was built around dca_rescue_trend as the
profit-taking exit. scripts/trailing_stop_oos_test.py just showed a FROZEN
trailing-stop exit (activate at +0.63%, trail 0.30% behind peak, derived on
ETHUSDT only) beats dca_rescue_trend out-of-sample on BOTH ETH and BTC. That
changes when/how trades exit, so the leverage/stop calibration needs
redoing on top of it rather than just being layered underneath unchanged.

Two DIFFERENT stop mechanisms now coexist, and it matters that they don't
fight each other:
  - PROTECTIVE stop: guards against catastrophic loss BEFORE any profit is
    locked in. Distance calibrated from the historical MAE percentile
    (p80/p90/p95), same idea as scripts/leverage_with_stop.py -- this measures
    how far the price path moves against the entry, which is a property of
    the entry + price path, not of which exit rule eventually closes the
    trade, so the MAE distribution from mae_mfe_analysis.py's trades is
    still the right input.
  - TRAILING stop: activates once price is +0.63% in profit, then locks in
    gains by trailing 0.30% behind the peak. This is what actually closes
    most winning trades now, before the protective stop would ever be
    relevant to them.

Leverage is sized the same way as before: the exchange's liquidation move
(STOP_OUT_FRACTION / leverage) must sit safely beyond the protective stop's
distance, controlled by SAFETY_MARGIN.

Usage:
    python scripts/leverage_trailing_combined.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.diagnostic_leverage import STOP_OUT_FRACTION

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
CAPITAL = 10_000.0
RISK_PCT = 0.01

# FROZEN trailing rule, derived on ETHUSDT only (scripts/mae_mfe_analysis.py) -- unchanged here.
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0030

STOP_PERCENTILES = [80, 90, 95]
SAFETY_MARGIN = 0.75


def apply_stop_and_trailing_leveraged(trades: list[dict], stop_distance: float, leverage: float) -> list[dict]:
    """Combined exit: whichever of (protective stop, liquidation, trailing
    stop) is breached FIRST along the path closes the trade; if none
    trigger within the lookahead window, closes at the window's last price
    (time exit). effective_stop = min(stop_distance, liq_move) since
    liquidation can be tighter than the voluntary stop at high leverage --
    tracked separately so forced liquidations are still visible in the
    report, exactly like leverage_with_stop.py."""
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    is_liquidation = liq_move <= stop_distance

    results = []
    for t in trades:
        path = t["close_path"]
        peak = -np.inf
        activated = False
        exit_ret, forced_liq = None, False
        for x in path:
            if x <= -protective:
                exit_ret, forced_liq = -protective - COST_PCT, is_liquidation
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    exit_ret = stop_level - COST_PCT
                    break
        if exit_ret is None:
            exit_ret = path[-1] - COST_PCT
        results.append({"pnl_return": exit_ret, "forced_liquidation": forced_liq})
    return results


def report(symbol: str, results: list[dict], leverage: float, stop_distance: float, label: str) -> dict:
    notional_1x = CAPITAL * RISK_PCT
    returns = np.array([r["pnl_return"] for r in results])
    pnl_dollars = returns * notional_1x * leverage
    wins, losses = pnl_dollars[pnl_dollars > 0], pnl_dollars[pnl_dollars <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    n_forced = sum(r["forced_liquidation"] for r in results)

    eq = CAPITAL + np.cumsum(pnl_dollars)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    max_dd_pct = float(dd.min() * 100)

    print(f"  {symbol:<8} {label:<10} lev={leverage:>5.1f}x stop={stop_distance*100:>5.2f}%  "
          f"n={len(results):>4} win%={((pnl_dollars>0).mean()*100):>5.1f} PF={pf:>7.3f} "
          f"total_ret={pnl_dollars.sum()/CAPITAL*100:>+7.2f}% max_DD={max_dd_pct:>+7.2f}% "
          f"forced_liq={n_forced}")
    return {"symbol": symbol, "leverage": leverage, "stop_distance": stop_distance,
            "profit_factor": round(pf, 3), "total_return_pct": round(pnl_dollars.sum() / CAPITAL * 100, 3),
            "n_forced_liq": n_forced}


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min...")
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
    print(f"{len(kept)} features kept.")
    print(f"Frozen trailing rule: activate at +{ACTIVATE_AT*100:.2f}%, trail {TRAIL_DIST*100:.2f}% behind peak.\n")

    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df_sym = load_split(symbol, "train", verbose=False)
        train_feats_sym = build_feature_matrix(train_df_sym)
        train_proba_sym = model.predict_proba(train_feats_sym)
        train_selected_sym = train_proba_sym > THRESHOLD
        range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
        vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

        df_val = load_split(symbol, "validation", verbose=False)
        feats_val = build_feature_matrix(df_val)
        close_val = df_val["close"]
        proba = model.predict_proba(feats_val)
        filtered_mask = (
            (proba > THRESHOLD)
            & (feats_val["range_pos_60"] < range_pos_cut)
            & (feats_val["realized_vol_30"] > vol_cut)
        ).to_numpy()
        close_arr = close_val.to_numpy()
        ema_slope_arr = feats_val["ema_slope_20"].to_numpy()
        ret_1_arr = feats_val["ret_1"].to_numpy()

        trades = build_trades_with_mae_mfe(close_arr, filtered_mask, ema_slope_arr, ret_1_arr)
        leg_maes = np.array([abs(t["mae"]) for t in trades])

        print("=" * 100)
        print(f"  {symbol} — protective-stop + frozen-trailing, leverage sweep (n={len(trades)} entries)")
        print("=" * 100)

        results_1x = apply_stop_and_trailing_leveraged(trades, stop_distance=1.0, leverage=1.0)
        report(symbol, results_1x, 1.0, 1.0, "1x")

        for pct in STOP_PERCENTILES:
            stop_distance = float(np.percentile(leg_maes, pct))
            max_lev = SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance
            for lev in sorted(set([round(max_lev, 1), round(max_lev * 0.5, 1), round(max_lev * 2, 1)])):
                if lev < 1:
                    continue
                results = apply_stop_and_trailing_leveraged(trades, stop_distance, lev)
                report(symbol, results, lev, stop_distance, f"p{pct}")
        print()


if __name__ == "__main__":
    main()
