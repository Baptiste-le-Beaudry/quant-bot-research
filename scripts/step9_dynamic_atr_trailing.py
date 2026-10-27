"""
scripts/step9_dynamic_atr_trailing.py — Étape 9 (dynamic trailing): V2's
trailing distance is a FIXED 0.80% regardless of market conditions at
entry. This tests trail_dist = k * atr_norm_at_entry (atr_norm = ATR/close,
already a relative measure) instead -- a trade entered during high
volatility gets a wider trail, one entered during calm conditions gets a
tighter one. Explicit hypothesis this experiment checks: does a trail that
auto-widens in high-vol conditions reduce the gap-stress fragility found
in Experiment 1 (a FIXED 0.30%, then 0.80%, trail was smaller than a
realistic fill gap)?

activate_at (+0.63%) and the protective stop (p90 MAE, TRAIN-calibrated)
are UNCHANGED -- only the trailing distance's construction changes, one
parameter at a time per the plan's rule.

Usage:
    python scripts/step9_dynamic_atr_trailing.py
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
from scripts.step1_stress_test import load_funding, funding_cost_for_window

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
ACTIVATE_AT = 0.0063
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01
K_VALUES = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
V2_FIXED_TRAIL = 0.0080


def simulate(trades_with_trail, close_arr, timestamps, funding, stop_distance, leverage,
             gap_extra: float = 0.0) -> dict:
    """trades_with_trail: list of (trade_dict, trail_dist_for_this_trade)."""
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    notional = CAPITAL * RISK_PCT
    pnls = []
    for t, trail_dist in trades_with_trail:
        i = t["entry_idx"]
        path = t["close_path"]
        peak, activated = -np.inf, False
        exit_ret, exit_offset = None, len(path) - 1
        for j, x in enumerate(path):
            if x <= -protective:
                exit_ret, exit_offset = -protective - gap_extra - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, j
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - trail_dist
                if x <= stop_level:
                    exit_ret, exit_offset = stop_level - gap_extra - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, j
                    break
        if exit_ret is None:
            exit_ret = path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        pnls.append(exit_ret * notional * leverage)
    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
            "win_rate_pct": round((pnls > 0).mean() * 100, 1)}


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
        stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
        leverage = LEVERAGE[symbol]

        val_df = load_split(symbol, "validation", verbose=False)
        val_feats = build_feature_matrix(val_df)
        val_proba = model.predict_proba(val_feats)
        val_close = val_df["close"].to_numpy()
        val_ema_slope = val_feats["ema_slope_20"].to_numpy()
        val_ret_1 = val_feats["ret_1"].to_numpy()
        val_atr_norm = val_feats["atr_norm"].to_numpy()
        val_filtered = (
            (val_proba > THRESHOLD)
            & (val_feats["range_pos_60"] < range_pos_cut)
            & (val_feats["realized_vol_30"] > vol_cut)
        ).to_numpy()
        val_trades = build_trades_with_mae_mfe(val_close, val_filtered, val_ema_slope, val_ret_1)
        funding = load_funding(symbol)
        timestamps = val_df.index

        print("=" * 100)
        print(f"  {symbol} — dynamic ATR trailing (n_entries={len(val_trades)}, stop={stop_distance*100:.2f}%)")
        print("=" * 100)

        # V2 fixed-trail baseline
        fixed_pairs = [(t, V2_FIXED_TRAIL) for t in val_trades]
        r0 = simulate(fixed_pairs, val_close, timestamps, funding, stop_distance, leverage)
        r0_gap = simulate(fixed_pairs, val_close, timestamps, funding, stop_distance, leverage, gap_extra=0.0025)
        print(f"  {'V2 fixed 0.80%':<22} n={r0.get('n_trades',0):>4} PF={r0.get('profit_factor',float('nan')):>7.3f} "
              f"ret={r0.get('total_return_pct',float('nan')):>+7.3f}%   [gap.25%: "
              f"PF={r0_gap.get('profit_factor',float('nan')):>7.3f} ret={r0_gap.get('total_return_pct',float('nan')):>+7.3f}%]")

        atr_at_entry = [val_atr_norm[t["entry_idx"]] for t in val_trades]
        print(f"  (median atr_norm at entry: {np.median(atr_at_entry)*100:.3f}%, "
              f"implies k=1.0 trail median {np.median(atr_at_entry)*100:.3f}%)")

        for k in K_VALUES:
            dyn_pairs = [(t, k * val_atr_norm[t["entry_idx"]]) for t in val_trades]
            r = simulate(dyn_pairs, val_close, timestamps, funding, stop_distance, leverage)
            r_gap = simulate(dyn_pairs, val_close, timestamps, funding, stop_distance, leverage, gap_extra=0.0025)
            avg_trail = np.mean([td for _, td in dyn_pairs])
            print(f"  {'k='+str(k)+' * ATR':<22} n={r.get('n_trades',0):>4} PF={r.get('profit_factor',float('nan')):>7.3f} "
                  f"ret={r.get('total_return_pct',float('nan')):>+7.3f}%   [gap.25%: "
                  f"PF={r_gap.get('profit_factor',float('nan')):>7.3f} ret={r_gap.get('total_return_pct',float('nan')):>+7.3f}%]"
                  f"  avg_trail={avg_trail*100:.3f}%")
            all_rows.append({"symbol": symbol, "k": k, "avg_trail_pct": avg_trail * 100,
                              "pf": r.get("profit_factor"), "ret": r.get("total_return_pct"),
                              "pf_gap25": r_gap.get("profit_factor"), "ret_gap25": r_gap.get("total_return_pct")})
        print()

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step9_dynamic_atr_raw.csv")
    pd.DataFrame(all_rows).to_csv(out_path, index=False)
    print(f"Raw results saved -> {out_path}")


if __name__ == "__main__":
    main()
