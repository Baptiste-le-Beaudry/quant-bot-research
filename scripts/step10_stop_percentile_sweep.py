"""
scripts/step10_stop_percentile_sweep.py — Étape 10: sweep the protective
stop's MAE percentile (p70-p97.5) on top of BASELINE_CANDIDATE_V2's
threshold=0.75 and trailing rule. For each percentile, leverage is
RE-DERIVED (not held at the registered 12.1x/9.9x) -- a wider stop implies
a lower safe leverage ceiling, a tighter stop allows more leverage but cuts
more trades prematurely, exactly the tension the plan wants quantified.

The plan's specific ask for this step: for each stop percentile, also
report what fraction of the trades that GOT STOPPED would have ended up
WINNING if the stop hadn't existed (i.e. if only trailing+time-exit had
resolved them) -- this is computed by running a second, stop-free
simulation on the SAME entries and comparing outcomes trade-by-trade.

Usage:
    python scripts/step10_stop_percentile_sweep.py
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
THRESHOLD = 0.75  # registered, unchanged from Experiment 5's ETH-confirmed optimum
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080  # V2
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01
SAFETY_MARGIN = 0.75
# CORRECTION (found while running this sweep): the registered V2 leverage
# (ETH 12.1x, BTC 9.9x) is the DIRECT formula value (SAFETY_MARGIN*STOP_OUT_FRACTION/
# stop_distance), i.e. CEILING_MULT=1.0 -- NOT "2x the ceiling" as
# docs/research_plan_status.md incorrectly stated before this fix. 2x that
# value is mathematically guaranteed to put liquidation INSIDE the stop
# (liq_move = 0.5*stop_distance/0.75 * 1/CEILING_MULT... at mult=2,
# liq_move=0.667*stop_distance < stop_distance ALWAYS), i.e. every "stop"
# becomes a forced liquidation, not a controlled one -- confirmed by this
# script's own first (buggy) run showing n_stop==n_forced at every row.
CEILING_MULT = 1.0

PERCENTILES = [70, 75, 80, 85, 90, 92.5, 95, 97.5]


def simulate_with_stop(trades, leverage, stop_distance):
    """Returns (per-trade results list, aggregate dict). Each per-trade
    result records whether the protective stop fired for that trade."""
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = CAPITAL * RISK_PCT
    per_trade = []
    for t in trades:
        path = t["close_path"]
        peak, activated = -np.inf, False
        exit_ret, stopped, forced = None, False, False
        for x in path:
            if x <= -protective:
                exit_ret = -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                stopped, forced = True, liq_move <= stop_distance
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    exit_ret = stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                    break
        if exit_ret is None:
            exit_ret = path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        per_trade.append({"pnl": exit_ret * notional * leverage, "stopped": stopped, "forced": forced})

    pnls = np.array([p["pnl"] for p in per_trade])
    if len(pnls) == 0:
        return per_trade, {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    return per_trade, {
        "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
        "max_dd_pct": round(float(dd.min() * 100), 3),
        "win_rate_pct": round((pnls > 0).mean() * 100, 1),
        "n_stopped": sum(p["stopped"] for p in per_trade),
        "n_forced_liq": sum(p["forced"] for p in per_trade),
    }


def simulate_no_stop(trades, leverage):
    """Counterfactual: trailing + time-exit only, no protective stop at all."""
    notional = CAPITAL * RISK_PCT
    outcomes = []
    for t in trades:
        path = t["close_path"]
        peak, activated = -np.inf, False
        exit_ret = None
        for x in path:
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    exit_ret = stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
                    break
        if exit_ret is None:
            exit_ret = path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        outcomes.append(exit_ret * notional * leverage)
    return outcomes


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

    all_rows = []
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
        train_maes = np.abs([t["mae"] for t in train_trades])

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

        print("=" * 115)
        print(f"  {symbol} — protective-stop percentile sweep (thr=0.75, n_entries={len(val_trades)})")
        print("=" * 115)
        print(f"  {'pctl':>6}{'stop%':>8}{'lev':>7}{'n':>5}{'PF':>9}{'ret%':>9}{'maxDD%':>9}{'n_stop':>8}"
              f"{'forced':>8}{'%cut_wouldve_won':>18}")

        no_stop_outcomes = simulate_no_stop(val_trades, 1.0)  # leverage=1 for the counterfactual comparison sign only

        for pctl in PERCENTILES:
            stop_distance = float(np.percentile(train_maes, pctl))
            leverage = SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance * CEILING_MULT
            per_trade, agg = simulate_with_stop(val_trades, leverage, stop_distance)
            if agg.get("n_trades", 0) == 0:
                continue
            stopped_idx = [i for i, p in enumerate(per_trade) if p["stopped"]]
            if stopped_idx:
                wouldve_won = sum(1 for i in stopped_idx if no_stop_outcomes[i] > 0)
                pct_wouldve_won = wouldve_won / len(stopped_idx) * 100
            else:
                pct_wouldve_won = float("nan")
            print(f"  p{pctl:<5.1f}{stop_distance*100:>7.2f}%{leverage:>7.1f}x{agg['n_trades']:>5}"
                  f"{agg['profit_factor']:>9.3f}{agg['total_return_pct']:>+9.3f}{agg['max_dd_pct']:>+9.3f}"
                  f"{agg['n_stopped']:>8}{agg['n_forced_liq']:>8}{pct_wouldve_won:>17.1f}%")
            all_rows.append({"symbol": symbol, "percentile": pctl, "stop_distance": stop_distance,
                              "leverage": leverage, "pct_stopped_wouldve_won": pct_wouldve_won, **agg})
        print()

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step10_stop_sweep_raw.csv")
    pd.DataFrame(all_rows).to_csv(out_path, index=False)
    print(f"Raw results saved -> {out_path}")


if __name__ == "__main__":
    main()
