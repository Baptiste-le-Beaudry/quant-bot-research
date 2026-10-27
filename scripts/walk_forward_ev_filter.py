"""
scripts/walk_forward_ev_filter.py — walk-forward validation of Experiment
12's EV filter (docs/research_plan_status.md), the strongest candidate
found this session: a TRAIN-calibrated, 2-D (realized_vol_30 tercile x
hour-of-day quadrant) expected-value gate that improved both symbols on
VALIDATION, frictionless AND under gap stress, without the ETH-fragile/
BTC-robust divergence every other lead this session showed.

Reuses scripts/walk_forward_engine.py's fold structure (13 expanding
TRAIN / 3mo TEST folds, 2019-11-27 -> 2025-03-28, HOLDOUT never touched)
and adds the EV table, calibrated PER FOLD from that fold's own TRAIN
filtered trades only (never TEST) -- same no-leakage discipline as the
protective-stop percentile already has in walk_forward_engine.py. Reports
BOTH baseline (no EV gate) and EV>0%-filtered results side by side for
every fold, so the aggregate comparison is apples-to-apples on identical
folds.

EV table needs a reasonable TRAIN population to be meaningful across 12
cells -- folds with fewer than MIN_TRAIN_FOR_EV filtered TRAIN trades skip
the EV gate for that fold (falls back to reporting baseline twice) rather
than fitting a noisy table on a handful of points.

Usage:
    python scripts/walk_forward_ev_filter.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe
from scripts.walk_forward_engine import (
    SYMBOLS, THRESHOLD, ACTIVATE_AT, TRAIL_DIST, STOP_PCT_PERCENTILE, LEVERAGE,
    FEE_PER_SIDE, BASE_SLIP_PER_SIDE, CAPITAL, RISK_PCT, SAFE_END,
    build_folds, fit_fold_model,
)
from scripts.phase3_baseline import _load_full

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MIN_TRAIN_FOR_EV = 60  # ~5 trades/cell average across 12 cells, a floor not a guarantee of quality


def cell_of(entry_idx, vol_arr, hour_arr, vol_tertiles):
    v = vol_arr[entry_idx]
    vol_bucket = 0 if v <= vol_tertiles[0] else (1 if v <= vol_tertiles[1] else 2)
    h = hour_arr[entry_idx]
    return (vol_bucket, h // 6)


def resolve_return(path, stop_distance, leverage):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, True
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, False
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2, False


def simulate(returns, leverage) -> dict:
    pnls = np.array(returns) * CAPITAL * RISK_PCT * leverage
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3)}


def run_fold_symbol_ev(symbol, train_df, test_df, model, train_feats_sym):
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    if train_selected_sym.sum() < 20:
        return {"n_trades": 0, "reason": "train-selected population < 20"}, None
    range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
    vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

    train_close = train_df["close"].to_numpy()
    train_filtered = (
        (train_proba_sym > THRESHOLD)
        & (train_feats_sym["range_pos_60"] < range_pos_cut)
        & (train_feats_sym["realized_vol_30"] > vol_cut)
    ).to_numpy()
    train_ema_slope = train_feats_sym["ema_slope_20"].to_numpy()
    train_ret_1 = train_feats_sym["ret_1"].to_numpy()
    train_trades = build_trades_with_mae_mfe(train_close, train_filtered, train_ema_slope, train_ret_1)
    if len(train_trades) < 10:
        return {"n_trades": 0, "reason": "too few TRAIN trades to calibrate stop"}, None
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
    leverage = LEVERAGE[symbol]

    test_feats = build_feature_matrix(test_df)
    test_proba = model.predict_proba(test_feats)
    test_filtered = (
        (test_proba > THRESHOLD)
        & (test_feats["range_pos_60"] < range_pos_cut)
        & (test_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    test_ema_slope = test_feats["ema_slope_20"].to_numpy()
    test_ret_1 = test_feats["ret_1"].to_numpy()
    test_close = test_df["close"].to_numpy()
    seq_trades = build_trades_with_mae_mfe(test_close, test_filtered, test_ema_slope, test_ret_1)
    if len(seq_trades) == 0:
        return {"n_trades": 0, "reason": "no TEST entries"}, None

    baseline_returns = [resolve_return(t["close_path"], stop_distance, leverage)[0] for t in seq_trades]
    r_base = simulate(baseline_returns, leverage)
    r_base["stop_distance_pct"] = round(stop_distance * 100, 3)

    if len(train_trades) < MIN_TRAIN_FOR_EV:
        return r_base, {"n_trades": r_base["n_trades"], "profit_factor": r_base.get("profit_factor"),
                         "total_return_pct": r_base.get("total_return_pct"), "reason": "EV skipped, TRAIN too small"}

    train_vol = train_feats_sym["realized_vol_30"].to_numpy()
    train_hour = train_df.index.hour.to_numpy()
    vol_tertiles = np.nanpercentile(train_vol[[t["entry_idx"] for t in train_trades]], [33.3, 66.7])
    cell_rets = {}
    for t in train_trades:
        ret, _ = resolve_return(t["close_path"], stop_distance, leverage)
        k = cell_of(t["entry_idx"], train_vol, train_hour, vol_tertiles)
        cell_rets.setdefault(k, []).append(ret)
    ev_table = {}
    for k, rets in cell_rets.items():
        rets = np.array(rets)
        wins, losses = rets[rets > 0], rets[rets <= 0]
        p_win = len(wins) / len(rets)
        avg_win = wins.mean() if len(wins) else 0.0
        avg_loss = -losses.mean() if len(losses) else 0.0
        ev_table[k] = p_win * avg_win - (1 - p_win) * avg_loss
    good_cells = {k for k, ev in ev_table.items() if ev > 0}

    test_vol = test_feats["realized_vol_30"].to_numpy()
    test_hour = test_df.index.hour.to_numpy()
    ev_returns = [ret for t, ret in zip(seq_trades, baseline_returns)
                  if cell_of(t["entry_idx"], test_vol, test_hour, vol_tertiles) in good_cells]
    r_ev = simulate(ev_returns, leverage)
    return r_base, r_ev


def main():
    print("Loading full 1-min history for BTCUSDT/ETHUSDT...")
    full = {s: _load_full(s) for s in SYMBOLS}
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)
    print(f"{len(folds)} walk-forward folds\n")

    all_rows = []
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        print("=" * 100)
        print(f"  FOLD {fold_i}/{len(folds)}: TRAIN [{t0:%Y-%m-%d} -> {train_end:%Y-%m-%d}]  "
              f"TEST [{train_end:%Y-%m-%d} -> {test_end:%Y-%m-%d}]")
        print("=" * 100)
        train_slices = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in SYMBOLS}
        test_slices = {s: full[s][(full[s].index >= train_end) & (full[s].index < test_end)] for s in SYMBOLS}
        model, train_feats = fit_fold_model(train_slices)

        for symbol in SYMBOLS:
            r_base, r_ev = run_fold_symbol_ev(symbol, train_slices[symbol], test_slices[symbol],
                                               model, train_feats[symbol])
            if r_base.get("n_trades", 0) == 0:
                print(f"  {symbol}: {r_base.get('reason', 'no trades')}")
            else:
                base_str = f"n={r_base['n_trades']:>3} PF={r_base['profit_factor']:>7.3f} ret={r_base['total_return_pct']:>+7.3f}%"
                if r_ev and r_ev.get("n_trades", 0) > 0:
                    ev_str = f"n={r_ev['n_trades']:>3} PF={r_ev['profit_factor']:>7.3f} ret={r_ev['total_return_pct']:>+7.3f}%"
                else:
                    ev_str = r_ev.get("reason", "no EV-filtered trades") if r_ev else "n/a"
                print(f"  {symbol}: BASELINE {base_str}  |  EV>0% {ev_str}")
            all_rows.append({"fold": fold_i, "symbol": symbol,
                              "base_n": r_base.get("n_trades", 0), "base_pf": r_base.get("profit_factor"),
                              "base_ret": r_base.get("total_return_pct"),
                              "ev_n": (r_ev or {}).get("n_trades", 0), "ev_pf": (r_ev or {}).get("profit_factor"),
                              "ev_ret": (r_ev or {}).get("total_return_pct")})
        print()

    df_res = pd.DataFrame(all_rows)
    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_ev_raw.csv")
    df_res.to_csv(out_path, index=False)

    print("=" * 100)
    print("  WALK-FORWARD SUMMARY: baseline vs EV>0% filter")
    print("=" * 100)
    for symbol in SYMBOLS:
        sub = df_res[(df_res["symbol"] == symbol) & (df_res["base_n"] > 0)]
        sub_ev = sub[sub["ev_n"] > 0]
        print(f"\n{symbol}: {len(sub)}/{len(folds)} folds with baseline trades, "
              f"{len(sub_ev)}/{len(sub)} of those also had EV-filtered trades")
        if len(sub):
            bpf = sub["base_pf"].replace([np.inf], np.nan)
            print(f"  BASELINE:  mean PF={bpf.mean():.3f} median PF={bpf.median():.3f} "
                  f"%%folds PF>1={ (sub['base_pf']>1).mean()*100:.1f}%  total_ret_summed={sub['base_ret'].sum():+.2f}%")
        if len(sub_ev):
            epf = sub_ev["ev_pf"].replace([np.inf], np.nan)
            print(f"  EV>0%:     mean PF={epf.mean():.3f} median PF={epf.median():.3f} "
                  f"%%folds PF>1={ (sub_ev['ev_pf']>1).mean()*100:.1f}%  total_ret_summed={sub_ev['ev_ret'].sum():+.2f}%")

    print(f"\nRaw per-fold results saved -> {out_path}")


if __name__ == "__main__":
    main()
