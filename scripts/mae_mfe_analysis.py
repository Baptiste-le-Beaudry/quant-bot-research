"""
scripts/mae_mfe_analysis.py — the other half of scripts/diagnostic_leverage.py's
MAE study: MAE answers "how far does a trade move against us before it
resolves" (used to calibrate the stop-loss in scripts/leverage_with_stop.py).
MFE (Maximum Favorable Excursion) answers the opposite question -- "how far
does a trade move IN OUR FAVOR before it resolves" -- which nothing in this
project has measured yet. Without it there's no way to tell whether the
current dca_rescue_trend exit (fixed horizon, or wait-for-breakeven-then-
trend-confirm) is leaving profit on the table by exiting too early/late
relative to where price actually goes.

Three things computed here, all on the same filtered-entry population used
throughout this session (entry filter + horizon=10 + threshold=0.75):

1. MAE/MFE percentiles + a MAE-quartile x MFE-quartile matrix (win rate,
   avg realized return per cell) -- same "star matrix" idea as MAE-only
   analysis, but now showing which trades had lots of room to run that the
   current exit didn't capture.
2. A fixed take-profit sweep: what if, instead of dca_rescue_trend's
   fixed-horizon/rescue exit, the trade closed the instant it first touched
   a TP level (chosen from MFE percentiles)? Compared against the CURRENT
   exit's realized return on the same trades.
3. A simple trailing-stop variant (move stop to breakeven once +0.3% is
   reached, then trail by a fixed distance from the running peak) vs both
   of the above.

All three use the SAME lookahead window as dca_rescue_trend
(horizon + extension_cap) so this is an apples-to-apples comparison of exit
RULES on identical entries, not a different signal or filter.

Usage:
    python scripts/mae_mfe_analysis.py [--symbol BTCUSDT|ETHUSDT]
"""
import argparse
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
EXTENSION_CAP = 40
LOOKAHEAD = HORIZON + EXTENSION_CAP  # same window dca_rescue_trend gets, for a fair comparison
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
CAPITAL = 10_000.0
RISK_PCT = 0.01


def build_trades_with_mae_mfe(close_arr, entry_mask, ema_slope, ret_1) -> list[dict]:
    """Same dca_rescue_trend replay as diagnostic_leverage.build_trades_with_mae
    (kept self-contained here rather than imported, since this also needs the
    full per-bar path for MFE, not just the final MAE scalar) -- plus mfe,
    the path's own running max, and the offset (in bars from entry) at which
    that max was reached."""
    n = len(close_arr)
    trades = []
    i = 0
    while i < n - LOOKAHEAD - 1:
        if not entry_mask[i]:
            i += 1
            continue

        entry_price = close_arr[i]
        base_exit_price = close_arr[i + HORIZON]
        base_return = (base_exit_price / entry_price - 1.0) - COST_PCT

        full_path = close_arr[i:i + LOOKAHEAD + 1] / entry_price - 1.0
        mae = float(full_path.min())
        mfe = float(full_path.max())
        mfe_offset = int(full_path.argmax())

        if base_return >= 0:
            trades.append({"pnl_return": base_return, "mae": mae, "mfe": mfe,
                            "mfe_offset": mfe_offset, "rescued": False, "close_path": full_path,
                            "entry_idx": i})
            i += HORIZON
            continue

        target = entry_price
        leg2_opened, entry_price2 = False, None
        exit_offset = LOOKAHEAD
        exit_price = close_arr[i + exit_offset]
        rescued = False
        for j in range(HORIZON, LOOKAHEAD + 1):
            p = close_arr[i + j]
            if p >= target:
                exit_price, exit_offset, rescued = p, j, leg2_opened
                break
            if not leg2_opened and ema_slope[i + j] > 0 and ret_1[i + j] > 0:
                leg2_opened, entry_price2 = True, p
        leg1_pnl = (exit_price / entry_price - 1.0) - COST_PCT
        combined = leg1_pnl
        if leg2_opened:
            combined += (exit_price / entry_price2 - 1.0) - COST_PCT
        trades.append({"pnl_return": combined, "mae": mae, "mfe": mfe,
                        "mfe_offset": mfe_offset, "rescued": rescued, "close_path": full_path,
                        "entry_idx": i})
        i += exit_offset

    return trades


def print_mae_mfe_stats(trades: list[dict]) -> None:
    maes = np.array([t["mae"] for t in trades])
    mfes = np.array([t["mfe"] for t in trades])
    print(f"n_trades={len(trades)}")
    print(f"{'pct':>6}{'MAE (adverse)':>18}{'MFE (favorable)':>18}")
    for pct in [10, 25, 50, 75, 90, 95, 99, 100]:
        print(f"{pct:>5}%{np.percentile(maes, pct)*100:>17.3f}%{np.percentile(mfes, pct)*100:>17.3f}%")
    print(f"\nAvg MFE: {mfes.mean()*100:.3f}%  |  Avg MAE: {maes.mean()*100:.3f}%  |  "
          f"MFE/|MAE| ratio: {mfes.mean() / abs(maes.mean()):.2f}x")


def print_quartile_matrix(trades: list[dict]) -> None:
    maes = np.array([abs(t["mae"]) for t in trades])
    mfes = np.array([t["mfe"] for t in trades])
    returns = np.array([t["pnl_return"] for t in trades])
    mae_q = pd.qcut(maes, 4, labels=["Q1(low)", "Q2", "Q3", "Q4(high)"], duplicates="drop")
    mfe_q = pd.qcut(mfes, 4, labels=["Q1(low)", "Q2", "Q3", "Q4(high)"], duplicates="drop")
    df = pd.DataFrame({"mae_q": mae_q, "mfe_q": mfe_q, "ret": returns})

    print("\nMAE-quartile x MFE-quartile matrix (n / win% / avg realized return under the CURRENT exit):")
    pivot_n = df.pivot_table(index="mae_q", columns="mfe_q", values="ret", aggfunc="count")
    pivot_win = df.pivot_table(index="mae_q", columns="mfe_q", values="ret", aggfunc=lambda s: (s > 0).mean() * 100)
    pivot_ret = df.pivot_table(index="mae_q", columns="mfe_q", values="ret", aggfunc="mean") * 100
    for mae_row in pivot_n.index:
        for mfe_col in pivot_n.columns:
            n = pivot_n.loc[mae_row, mfe_col] if mfe_col in pivot_n.columns else np.nan
            if pd.isna(n):
                continue
            win = pivot_win.loc[mae_row, mfe_col]
            ret = pivot_ret.loc[mae_row, mfe_col]
            print(f"  MAE={mae_row:<9} MFE={mfe_col:<9} n={int(n):>4}  win%={win:>5.1f}  avg_ret={ret:>+7.4f}%")


def sweep_fixed_tp(trades: list[dict], tp_levels: list[float]) -> None:
    """For each candidate TP (as a fraction, e.g. 0.005 = 0.5%), replay each
    trade's own close_path and exit the instant the path first touches +TP,
    else fall back to the CURRENT exit's realized return (i.e. this only
    tests 'exit earlier via TP', never 'exit later than the current logic
    already would' -- a fair like-for-like on the same entries)."""
    print(f"\n{'TP level':>10}{'n_hit_tp':>10}{'avg_ret_all%':>14}{'PF':>8}{'win%':>8}"
          f"{'vs_baseline_avg%':>18}")
    baseline_returns = np.array([t["pnl_return"] for t in trades])
    baseline_avg = baseline_returns.mean() * 100
    for tp in tp_levels:
        rets = []
        n_hit = 0
        for t in trades:
            path = t["close_path"]
            hit_idx = np.argmax(path >= tp) if (path >= tp).any() else -1
            if hit_idx > 0 or (hit_idx == 0 and path[0] >= tp):
                rets.append(tp - COST_PCT)
                n_hit += 1
            else:
                rets.append(t["pnl_return"])
        rets = np.array(rets)
        wins, losses = rets[rets > 0], rets[rets <= 0]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
        print(f"{tp*100:>9.2f}%{n_hit:>10}{rets.mean()*100:>13.4f}%{pf:>8.3f}"
              f"{(rets>0).mean()*100:>7.1f}%{rets.mean()*100 - baseline_avg:>+17.4f}%")
    print(f"(baseline = current dca_rescue_trend exit, avg_ret={baseline_avg:+.4f}%)")


def apply_trailing_stop(trades: list[dict], activate_at: float, trail_dist: float) -> np.ndarray:
    """Once price reaches +activate_at, a trailing stop starts following
    trail_dist behind the running peak; exits the instant price pulls back
    to that stop. Falls back to the CURRENT exit's (dca_rescue_trend)
    realized return if never triggered -- same fairness rule used
    throughout this module: this only tests 'exit earlier via trailing',
    never 'hold longer than the current logic already would'."""
    rets = []
    for t in trades:
        path = t["close_path"]
        activated = False
        peak = -np.inf
        exit_ret = None
        for x in path:
            if x > peak:
                peak = x
            if not activated and peak >= activate_at:
                activated = True
            if activated:
                stop_level = max(0.0, peak - trail_dist)
                if x <= stop_level:
                    exit_ret = stop_level - COST_PCT
                    break
        rets.append(exit_ret if exit_ret is not None else t["pnl_return"])
    return np.array(rets)


def sweep_trailing_stop(trades: list[dict], activate_at: float, trail_dist_levels: list[float]) -> None:
    print(f"\nTrailing stop: activates at +{activate_at*100:.2f}%, then trails behind peak")
    print(f"{'trail_dist':>12}{'n_triggered':>13}{'avg_ret_all%':>14}{'PF':>8}{'win%':>8}")
    baseline_returns = np.array([t["pnl_return"] for t in trades])
    for trail in trail_dist_levels:
        rets = apply_trailing_stop(trades, activate_at, trail)
        n_trig = int((rets != baseline_returns).sum())
        wins, losses = rets[rets > 0], rets[rets <= 0]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
        print(f"{trail*100:>11.2f}%{n_trig:>13}{rets.mean()*100:>13.4f}%{pf:>8.3f}{(rets>0).mean()*100:>7.1f}%")
    print(f"(baseline = current dca_rescue_trend exit, avg_ret={baseline_returns.mean()*100:+.4f}%)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], default="ETHUSDT")
    args = parser.parse_args()
    SYMBOL = args.symbol

    print(f"Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min, evaluating on {SYMBOL}...")
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

    train_df_sym = load_split(SYMBOL, "train", verbose=False)
    train_feats_sym = build_feature_matrix(train_df_sym)
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
    vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

    df_val = load_split(SYMBOL, "validation", verbose=False)
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

    print("=" * 100)
    print(f"  STEP 1 — MAE/MFE percentiles, {SYMBOL} VALIDATION, filtered entries, "
          f"{LOOKAHEAD}min lookahead window")
    print("=" * 100)
    print_mae_mfe_stats(trades)

    print("\n" + "=" * 100)
    print("  STEP 2 — MAE-quartile x MFE-quartile matrix")
    print("=" * 100)
    print_quartile_matrix(trades)

    mfes = np.array([t["mfe"] for t in trades])
    tp_levels = sorted(set([round(float(np.percentile(mfes, p)), 4) for p in [25, 50, 70, 90]]
                            + [0.003, 0.005, 0.008, 0.01, 0.015]))
    tp_levels = [t for t in tp_levels if t > 0]
    print("\n" + "=" * 100)
    print("  STEP 3 — fixed take-profit sweep vs current dca_rescue_trend exit")
    print("=" * 100)
    sweep_fixed_tp(trades, tp_levels)

    print("\n" + "=" * 100)
    print("  STEP 4 — trailing stop sweep (activate at MFE p25, trail distance swept)")
    print("=" * 100)
    activate_at = max(0.001, float(np.percentile(mfes, 25)))
    sweep_trailing_stop(trades, activate_at, [0.002, 0.004, 0.006, 0.008, 0.01])


if __name__ == "__main__":
    main()
