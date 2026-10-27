"""
scripts/step14_ev_filter.py — Étape 14: build EV = P(win)*avg_win -
P(loss)*avg_loss - costs per entry, and test whether trading only when
EV > 0 (calibrated on TRAIN) improves on BASELINE_CANDIDATE_V2.

Because the classifier's own probability has almost no usable spread on
this filtered population (established this session: TRAIN-selected probas
cluster tightly just above threshold, confirmed again in
step3_bucket_analysis.py where ALL 131 trades sat in one probability
bucket), P(win)/avg_win/avg_loss are instead estimated PER CELL of a
2-D bucket grid -- realized_vol_30 tercile x hour-of-day quadrant -- built
from TRAIN's own trades (the two dimensions Experiment/Étape-3's bucket
analysis found the most real-looking variation along). This is a genuine
EV framework grounded in already-validated signal, not new untested
dimensions invented for this experiment alone.

Usage:
    python scripts/step14_ev_filter.py
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
CAPITAL = 10_000.0
RISK_PCT = 0.01


def resolve_exit_return(path: np.ndarray, stop_distance: float, leverage: float) -> float:
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    exit_ret = None
    for x in path:
        if x <= -protective:
            exit_ret = -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
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
    return exit_ret


def simulate_from_returns(returns, leverage) -> dict:
    pnls = np.array(returns) * CAPITAL * RISK_PCT * leverage
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

        # Build TRAIN EV table: realized_vol_30 tercile x hour-of-day quadrant.
        train_vol = train_feats["realized_vol_30"].to_numpy()
        train_hour = train_df.index.hour.to_numpy()
        vol_tertiles = np.nanpercentile(train_vol[[t["entry_idx"] for t in train_trades]], [33.3, 66.7])

        def cell_key(entry_idx):
            v = train_vol[entry_idx]
            vol_bucket = 0 if v <= vol_tertiles[0] else (1 if v <= vol_tertiles[1] else 2)
            h = train_hour[entry_idx]
            hour_bucket = h // 6  # 0-6,6-12,12-18,18-24
            return (vol_bucket, hour_bucket)

        train_returns_by_cell = {}
        for t in train_trades:
            ret = resolve_exit_return(t["close_path"], stop_distance, leverage)
            k = cell_key(t["entry_idx"])
            train_returns_by_cell.setdefault(k, []).append(ret)

        ev_table = {}
        for k, rets in train_returns_by_cell.items():
            rets = np.array(rets)
            wins, losses = rets[rets > 0], rets[rets <= 0]
            p_win = len(wins) / len(rets)
            avg_win = wins.mean() if len(wins) else 0.0
            avg_loss = -losses.mean() if len(losses) else 0.0
            ev = p_win * avg_win - (1 - p_win) * avg_loss
            ev_table[k] = {"ev": ev, "n": len(rets), "p_win": p_win}

        print("=" * 100)
        print(f"  {symbol} — EV table (TRAIN, vol_tercile x hour_quadrant), n_cells={len(ev_table)}")
        print("=" * 100)
        for k in sorted(ev_table):
            v = ev_table[k]
            print(f"  vol_tertile={k[0]} hour_q={k[1]}: n={v['n']:>4} p_win={v['p_win']*100:>5.1f}% "
                  f"EV={v['ev']*100:>+8.4f}%")

        # Apply to VALIDATION
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
        val_hour = val_df.index.hour.to_numpy()
        val_vol = val_feats["realized_vol_30"].to_numpy()

        def val_cell_key(entry_idx):
            v = val_vol[entry_idx]
            vol_bucket = 0 if v <= vol_tertiles[0] else (1 if v <= vol_tertiles[1] else 2)
            h = val_hour[entry_idx]
            hour_bucket = h // 6
            return (vol_bucket, hour_bucket)

        baseline_returns = [resolve_exit_return(t["close_path"], stop_distance, leverage) for t in val_trades]
        r_base = simulate_from_returns(baseline_returns, leverage)
        print(f"\n  BASELINE (no EV filter): n={r_base.get('n_trades',0)} "
              f"PF={r_base.get('profit_factor',float('nan')):.3f} "
              f"ret={r_base.get('total_return_pct',float('nan')):+.3f}%")

        for ev_cut in [0.0, 0.001, 0.002]:
            kept_returns = []
            for t, ret in zip(val_trades, baseline_returns):
                k = val_cell_key(t["entry_idx"])
                cell = ev_table.get(k)
                if cell is not None and cell["ev"] > ev_cut and cell["n"] >= 10:
                    kept_returns.append(ret)
            r = simulate_from_returns(kept_returns, leverage)
            print(f"  + EV filter (cell EV > {ev_cut*100:.2f}%, TRAIN n>=10): n={r.get('n_trades',0)} "
                  f"PF={r.get('profit_factor',float('nan')):.3f} "
                  f"ret={r.get('total_return_pct',float('nan')):+.3f}%")
        print()


if __name__ == "__main__":
    main()
