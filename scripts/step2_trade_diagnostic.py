"""
scripts/step2_trade_diagnostic.py — Étape 2 of the research plan: a full
per-trade diagnostic dataset (not just aggregate PF/return numbers), so
Étape 3 (where does the edge actually live?) can bucket trades by any of
these dimensions without re-simulating. Runs BASELINE_CANDIDATE_V1's exact
exit logic (protective stop p90 + frozen trailing + time-exit,
docs/research_plan_status.md) on every filtered VALIDATION entry for both
symbols, at 1x (leverage is a config knob applied on top of these
per-trade returns at analysis time, not something that changes which
exit fires).

One row per trade, columns:
  timestamp, symbol, entry_price, exit_price, gross_return, net_return,
  mfe, mae, time_to_mfe, time_to_mae, exit_reason, holding_time_min,
  signal_probability, range_pos_60, realized_vol_30, atr_norm,
  dist_ema20_atr, ema_slope_20, rel_volume_20, volume_accel,
  btc_ret_60, btc_dist_ema50_atr (cross-asset regime context, via as-of
  join on BTCUSDT's own features -- included for BOTH symbols, so ETH
  trades get real BTC context and BTC trades get a self-referential
  sanity check), leverage_configured, funding_cost, slippage_cost.

Usage:
    python scripts/step2_trade_diagnostic.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import DATA_DIR, COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.step1_stress_test import historical_mae_stop_distance, get_sequential_trades

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
EXTENSION_CAP = 40
LOOKAHEAD = HORIZON + EXTENSION_CAP
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080  # BASELINE_CANDIDATE_V2 (docs/research_plan_status.md, Experiment 1b)
STOP_PCT_PERCENTILE = 90
LEVERAGE = {"ETHUSDT": 12.1, "BTCUSDT": 9.9}
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0

FUNDING_FILES = {
    "BTCUSDT": os.path.join(DATA_DIR, "BTCUSDT_funding_20230506_20260818.csv"),
    "ETHUSDT": os.path.join(DATA_DIR, "ETHUSDT_funding_20230506_20260818.csv"),
}


def load_funding(symbol: str) -> pd.Series:
    df = pd.read_csv(FUNDING_FILES[symbol])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    return df.set_index("timestamp")["fundingRate"].sort_index()


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
    print(f"{len(kept)} features kept.\n")

    # BTC context series (own features) for the whole span both VALIDATION windows fall in.
    btc_val_full = load_split("BTCUSDT", "validation", verbose=False)
    btc_feats_full = build_feature_matrix(btc_val_full)
    btc_context = btc_feats_full[["ret_60", "dist_ema50_atr"]].rename(
        columns={"ret_60": "btc_ret_60", "dist_ema50_atr": "btc_dist_ema50_atr"})

    all_trades = []
    for symbol in ["ETHUSDT", "BTCUSDT"]:
        train_df_sym = load_split(symbol, "train", verbose=False)
        train_feats_sym = build_feature_matrix(train_df_sym)
        train_proba_sym = model.predict_proba(train_feats_sym)
        train_selected_sym = train_proba_sym > THRESHOLD
        range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
        vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

        df_val = load_split(symbol, "validation", verbose=False)
        feats_val = build_feature_matrix(df_val)
        proba = model.predict_proba(feats_val)
        filtered_mask = (
            (proba > THRESHOLD)
            & (feats_val["range_pos_60"] < range_pos_cut)
            & (feats_val["realized_vol_30"] > vol_cut)
        ).to_numpy()
        ema_slope_arr = feats_val["ema_slope_20"].to_numpy()
        ret_1_arr = feats_val["ret_1"].to_numpy()

        close_arr = df_val["close"].to_numpy()
        timestamps = df_val.index
        funding = load_funding(symbol)
        n = len(close_arr)
        # ONE POSITION AT A TIME entry selection (SPEC.md section 11) -- reuses the
        # established sequential walk instead of treating every filtered_mask=True
        # index as an independent trade (that allows overlapping positions and
        # silently inflates n, see scripts/step1_stress_test.py's docstring).
        seq_trades = get_sequential_trades(df_val, filtered_mask, ema_slope_arr, ret_1_arr)
        idx = [t["entry_idx"] for t in seq_trades]
        stop_distance = historical_mae_stop_distance(seq_trades)
        print(f"{symbol}: {len(idx)} sequential entries, p{STOP_PCT_PERCENTILE} stop={stop_distance*100:.3f}%, "
              f"building diagnostic rows...")

        for i in idx:
            if i >= n - LOOKAHEAD - 1:
                continue
            entry_price = close_arr[i]
            entry_ts = timestamps[i]
            path = close_arr[i:i + LOOKAHEAD + 1] / entry_price - 1.0

            mae = float(path.min())
            time_to_mae = int(path.argmin())
            mfe = float(path.max())
            time_to_mfe = int(path.argmax())

            liq_move = STOP_OUT_FRACTION / LEVERAGE[symbol]
            protective = min(stop_distance, liq_move)

            peak, activated = -np.inf, False
            exit_ret, exit_offset, exit_reason = None, LOOKAHEAD, "time"
            for j, x in enumerate(path):
                if x <= -protective:
                    exit_ret, exit_offset, exit_reason = x, j, "stop"
                    break
                if x > peak:
                    peak = x
                if not activated and peak >= ACTIVATE_AT:
                    activated = True
                if activated:
                    stop_level = peak - TRAIL_DIST
                    if x <= stop_level:
                        exit_ret, exit_offset, exit_reason = stop_level, j, "trailing"
                        break
            if exit_ret is None:
                exit_ret, exit_reason = path[-1], "time"

            cost_entry = FEE_PER_SIDE + BASE_SLIP_PER_SIDE
            cost_exit = FEE_PER_SIDE + BASE_SLIP_PER_SIDE
            gross_return = exit_ret
            slippage_cost = 2 * BASE_SLIP_PER_SIDE
            exit_ts = timestamps[min(i + exit_offset, n - 1)]
            fcost = float(funding.loc[(funding.index > entry_ts) & (funding.index <= exit_ts)].sum())
            net_return = gross_return - cost_entry - cost_exit - fcost

            row = {
                "timestamp": entry_ts, "symbol": symbol,
                "entry_price": entry_price, "exit_price": close_arr[min(i + exit_offset, n - 1)],
                "gross_return": gross_return, "net_return": net_return,
                "mfe": mfe, "mae": mae, "time_to_mfe_min": time_to_mfe, "time_to_mae_min": time_to_mae,
                "exit_reason": exit_reason, "holding_time_min": exit_offset,
                "signal_probability": float(proba.iloc[i]),
                "range_pos_60": float(feats_val["range_pos_60"].iloc[i]),
                "realized_vol_30": float(feats_val["realized_vol_30"].iloc[i]),
                "atr_norm": float(feats_val["atr_norm"].iloc[i]),
                "dist_ema20_atr": float(feats_val["dist_ema20_atr"].iloc[i]),
                "ema_slope_20": float(feats_val["ema_slope_20"].iloc[i]),
                "rel_volume_20": float(feats_val["rel_volume_20"].iloc[i]),
                "volume_accel": float(feats_val["volume_accel"].iloc[i]),
                "leverage_configured": LEVERAGE[symbol],
                "funding_cost": fcost, "slippage_cost": slippage_cost,
            }
            all_trades.append(row)

    trades_df = pd.DataFrame(all_trades)
    # as-of join BTC context onto every trade (both symbols) by nearest prior BTC timestamp
    trades_df = trades_df.sort_values("timestamp")
    btc_context_sorted = btc_context.sort_index()
    trades_df = pd.merge_asof(trades_df, btc_context_sorted, left_on="timestamp", right_index=True, direction="backward")

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "step2_trade_diagnostic.csv")
    trades_df.to_csv(out_path, index=False)
    print(f"\n{len(trades_df)} total trades written -> {out_path}")
    print(trades_df.groupby("symbol").agg(n=("net_return", "count"),
                                           win_rate=("net_return", lambda s: (s > 0).mean() * 100),
                                           avg_net_return=("net_return", "mean")))
    print("\nExit reason breakdown:")
    print(trades_df.groupby(["symbol", "exit_reason"]).size())


if __name__ == "__main__":
    main()
