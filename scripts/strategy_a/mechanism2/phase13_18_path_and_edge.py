"""Phases 13-18: path-shape (pre/post entry), early-outcome diagnostic,
edge-source decomposition, remove-trailing descriptive test -- ALL
computed from the REAL frozen trade log (docs/multi_crypto_portfolio_
9sym_xrpp80_linkp95_trades.csv), close_path column, all 9 symbols. No new
model fits needed (close_path already reflects the real, executed
Strategy A entry selection).

Phase 14 (pre-entry path shape) needs bars BEFORE entry_time -- recomputed
from each symbol's own klines (build_feature_matrix's ret_1/ret_5/ret_15/
ret_60/range_expansion/rel_volume_20 already capture this descriptively;
no new features invented).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from common import SYMBOLS_9, MECH2_DOCS, REPO_ROOT, load_symbol, stop_distance_for_layer, classify_outcome
from quant_bot.features.build import build_feature_matrix
from quant_bot.config import TAKER_FEE_PCT, SLIPPAGE_PCT_EST

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRADES_CSV = os.path.join(REPO_ROOT, "docs", "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv")
HORIZONS = [1, 2, 5, 10, 20, 30, 50]
COST_RT = TAKER_FEE_PCT * 2 + SLIPPAGE_PCT_EST


def path_array(s: str) -> np.ndarray:
    return np.array([float(x) for x in s.split(";")])


def main():
    trades = pd.read_csv(TRADES_CSV, parse_dates=["entry_time", "exit_time"])
    print(f"Loaded {len(trades)} real Strategy A trades across {trades['symbol'].nunique()} symbols")

    # ---- Phase 15/16: post-entry path shape + early-outcome diagnostic ----
    post_rows = []
    for symbol, sub in trades.groupby("symbol"):
        paths = np.stack([path_array(s) for s in sub["close_path"]])
        # use each trade's OWN stored stop_distance/leverage_safe to get its own protective/liq_move
        outcomes = []
        for i, row in enumerate(sub.itertuples()):
            liq_move_i = 0.5 / row.leverage_safe if row.leverage_safe > 0 else np.inf
            outcomes.append(classify_outcome({"close_path": paths[i]}, row.stop_distance, liq_move_i))
        outcomes = np.array(outcomes)

        for group_name, mask in [("TRAILING_STOP", outcomes == "TRAILING_STOP"),
                                  ("PROTECTIVE_STOP", outcomes == "PROTECTIVE_STOP"),
                                  ("END_OF_WINDOW", outcomes == "END_OF_WINDOW"),
                                  ("ALL", np.ones(len(paths), dtype=bool))]:
            if mask.sum() == 0:
                continue
            group_paths = paths[mask]
            for h in HORIZONS:
                if group_paths.shape[1] > h:
                    vals = group_paths[:, h]
                    post_rows.append({"symbol": symbol, "group": group_name, "horizon_min": h,
                                       "n": int(mask.sum()), "mean_ret_pct": float(vals.mean()) * 100,
                                       "median_ret_pct": float(np.median(vals)) * 100,
                                       "std_ret_pct": float(vals.std()) * 100})
        # time-to-MFE / time-to-MAE / time-to-protective-stop / time-to-trailing-activation
        time_to_mfe = paths.argmax(axis=1)
        time_to_mae = paths.argmin(axis=1)
        post_rows.append({"symbol": symbol, "group": "ALL", "horizon_min": "time_to_mfe_median",
                           "n": len(paths), "mean_ret_pct": np.nan,
                           "median_ret_pct": float(np.median(time_to_mfe)), "std_ret_pct": float(np.std(time_to_mfe))})
        post_rows.append({"symbol": symbol, "group": "ALL", "horizon_min": "time_to_mae_median",
                           "n": len(paths), "mean_ret_pct": np.nan,
                           "median_ret_pct": float(np.median(time_to_mae)), "std_ret_pct": float(np.std(time_to_mae))})

    post_df = pd.DataFrame(post_rows)
    post_path = os.path.join(MECH2_DOCS, "strategy_a_post_entry_path_shape.csv")
    post_df.to_csv(post_path, index=False)
    print(f"Saved -> {post_path} ({len(post_df)} rows)")

    # ---- Phase 18: remove-trailing descriptive test (fixed horizon exit vs actual trailing) ----
    fixed_rows = []
    for symbol, sub in trades.groupby("symbol"):
        paths = np.stack([path_array(s) for s in sub["close_path"]])
        for h in [10, 20, 30, 50]:
            if paths.shape[1] > h:
                fixed_ret = paths[:, h] - COST_RT
                fixed_rows.append({"symbol": symbol, "exit_rule": f"fixed_{h}m", "n": len(fixed_ret),
                                    "mean_ret_pct": float(fixed_ret.mean()) * 100,
                                    "median_ret_pct": float(np.median(fixed_ret)) * 100,
                                    "winrate_pct": float(np.mean(fixed_ret > 0)) * 100,
                                    "pf": float(fixed_ret[fixed_ret > 0].sum() / -fixed_ret[fixed_ret <= 0].sum())
                                    if (fixed_ret <= 0).any() and fixed_ret[fixed_ret <= 0].sum() < 0 else np.inf})
        actual_ret = sub["raw_return"].to_numpy() - COST_RT
        fixed_rows.append({"symbol": symbol, "exit_rule": "actual_trailing_protective", "n": len(actual_ret),
                            "mean_ret_pct": float(actual_ret.mean()) * 100,
                            "median_ret_pct": float(np.median(actual_ret)) * 100,
                            "winrate_pct": float(np.mean(actual_ret > 0)) * 100,
                            "pf": float(actual_ret[actual_ret > 0].sum() / -actual_ret[actual_ret <= 0].sum())
                            if (actual_ret <= 0).any() and actual_ret[actual_ret <= 0].sum() < 0 else np.inf})
    fixed_df = pd.DataFrame(fixed_rows)
    fixed_path = os.path.join(MECH2_DOCS, "strategy_a_remove_trailing_test.csv")
    fixed_df.to_csv(fixed_path, index=False)
    print(f"Saved -> {fixed_path} ({len(fixed_df)} rows)")

    # ---- Phase 17: edge source decomposition (win rate / winner size / loss control / skew) ----
    edge_rows = []
    for symbol, sub in trades.groupby("symbol"):
        ret = sub["raw_return"].to_numpy() - COST_RT
        wins, losses = ret[ret > 0], ret[ret <= 0]
        edge_rows.append({
            "symbol": symbol, "n": len(ret), "win_rate_pct": float(np.mean(ret > 0)) * 100,
            "mean_winner_pct": float(wins.mean()) * 100 if len(wins) else np.nan,
            "mean_loser_pct": float(losses.mean()) * 100 if len(losses) else np.nan,
            "skew": float(pd.Series(ret).skew()),
            "pf": float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf,
            "expectancy_pct": float(ret.mean()) * 100,
            "pct_pnl_from_winners": float(wins.sum() / (wins.sum() - losses.sum()) * 100) if (wins.sum() - losses.sum()) != 0 else np.nan,
        })
    edge_df = pd.DataFrame(edge_rows)
    edge_path = os.path.join(MECH2_DOCS, "strategy_a_edge_source_decomposition.csv")
    edge_df.to_csv(edge_path, index=False)
    print(f"Saved -> {edge_path} ({len(edge_df)} rows)")

    # ---- Phase 14: pre-entry path shape (descriptive, from existing features only) ----
    pre_rows = []
    for symbol in SYMBOLS_9:
        sub = trades[trades["symbol"] == symbol]
        if len(sub) == 0:
            continue
        full = load_symbol(symbol)
        feats = build_feature_matrix(full)
        entry_times = sub["entry_time"]
        valid_times = entry_times[entry_times.isin(feats.index)]
        if len(valid_times) == 0:
            # entry_time may not align exactly to a bar (rare) -- use merge_asof backward instead
            feats_at_entry = pd.merge_asof(sub[["entry_time"]].sort_values("entry_time"), feats.reset_index().rename(columns={"index": "entry_time"}),
                                            on="entry_time", direction="backward")
        else:
            feats_at_entry = feats.loc[valid_times].reset_index(drop=True)
        for col in ["ret_1", "ret_5", "ret_15", "ret_60", "range_expansion", "rel_volume_20", "realized_vol_ratio"]:
            if col in feats_at_entry.columns:
                vals = feats_at_entry[col].dropna()
                if len(vals):
                    pre_rows.append({"symbol": symbol, "feature": col, "n": len(vals),
                                      "median": float(vals.median()), "mean": float(vals.mean()),
                                      "p10": float(vals.quantile(0.10)), "p90": float(vals.quantile(0.90))})
    pre_df = pd.DataFrame(pre_rows)
    pre_path = os.path.join(MECH2_DOCS, "strategy_a_pre_entry_path_shape.csv")
    pre_df.to_csv(pre_path, index=False)
    print(f"Saved -> {pre_path} ({len(pre_df)} rows)")


if __name__ == "__main__":
    main()
