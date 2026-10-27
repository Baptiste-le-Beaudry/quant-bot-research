"""Phase 5: LOGISTIC vs RandomForest, same protocol, no hyperparameter
search. Parallel version of scripts/multi_crypto_walkforward.py's
fit_fold_model/process_fold that swaps Tier2RandomForestSignal for
quant_bot/signal/model.py's already-existing Tier1LogisticSignal -- SAME
features, SAME TRAIN-only range_pos_cut/vol_cut calibration, SAME
threshold/horizon/stops, SAME walk-forward fold construction (imported
directly, not reimplemented). Read-only reuse; nothing frozen is modified.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from scripts.multi_crypto_walkforward import (
    _load_full_cached, decide_fold_params, build_folds, TRAIN_FRACTION, VALIDATION_FRACTION,
    HORIZON, THRESHOLD, ACTIVATE_AT, TRAIL_DIST, STOP_PCT_PERCENTILE, SAFETY_MARGIN,
    MAX_LEVERAGE_CAP, FEE_PER_SIDE, BASE_SLIP_PER_SIDE, CAPITAL, RISK_PCT,
)
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades_with_mae_mfe
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier1LogisticSignal
from quant_bot.config import COST_THRESHOLD_PCT
from quant_bot.data.splits import pre_holdout, HOLDOUT_START

from common3 import MECH3_DOCS, NEW_ASSETS, ASSET_TYPE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def fit_fold_logistic(train_df: pd.DataFrame):
    train_feats = build_feature_matrix(train_df)
    train_labels = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    kept, _ = prune_redundant(train_feats, train_labels, corr_threshold=0.9)
    fit_n = min(250_000, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier1LogisticSignal(kept).fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
    return model, train_feats


def process_fold_logistic(symbol, fold_i, train_df, test_df):
    model, train_feats = fit_fold_logistic(train_df)
    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > THRESHOLD
    if int(train_selected.sum()) < 20:
        return {"fold": fold_i, "symbol": symbol, "n_trades": 0, "reason": "train pop too small"}, []
    range_pos_cut = float(train_feats.loc[train_selected, "range_pos_60"].median())
    vol_cut = float(train_feats.loc[train_selected, "realized_vol_30"].median())

    train_close = train_df["close"].to_numpy()
    train_filtered = (train_selected & (train_feats["range_pos_60"] < range_pos_cut)
                       & (train_feats["realized_vol_30"] > vol_cut)).to_numpy()
    train_trades = build_trades_with_mae_mfe(
        train_close, train_filtered, train_feats["ema_slope_20"].to_numpy(),
        train_feats["ret_1"].to_numpy(), horizon=HORIZON)
    if len(train_trades) < 10:
        return {"fold": fold_i, "symbol": symbol, "n_trades": 0, "reason": "too few train trades"}, []
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)

    test_feats = build_feature_matrix(test_df)
    test_proba = model.predict_proba(test_feats)
    test_filtered = ((test_proba > THRESHOLD) & (test_feats["range_pos_60"] < range_pos_cut)
                      & (test_feats["realized_vol_30"] > vol_cut)).to_numpy()
    test_close = test_df["close"].to_numpy()
    seq_trades = build_trades_with_mae_mfe(
        test_close, test_filtered, test_feats["ema_slope_20"].to_numpy(),
        test_feats["ret_1"].to_numpy(), horizon=HORIZON)
    if len(seq_trades) == 0:
        return {"fold": fold_i, "symbol": symbol, "n_trades": 0, "reason": "no TEST entries"}, []

    notional = CAPITAL * RISK_PCT
    pnls, mfe_mae_rows = [], []
    for t in seq_trades:
        path = t["close_path"]
        peak, activated = -np.inf, False
        raw_return = None
        for x in path:
            if x <= -protective:
                raw_return = -protective
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    raw_return = stop_level
                    break
        if raw_return is None:
            raw_return = path[-1]
        exit_ret = raw_return - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        pnls.append(exit_ret * notional * leverage)
        mfe_mae_rows.append({"mfe": t["mfe"], "mae": t["mae"], "close_path": path})

    pnls = np.array(pnls)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    mfe = np.array([r["mfe"] for r in mfe_mae_rows])
    mae = np.array([r["mae"] for r in mfe_mae_rows])
    summary = {
        "fold": fold_i, "symbol": symbol, "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "expectancy_pct_of_notional": round(float(pnls.mean() / notional * 100), 4),
        "win_rate_pct": round(float((pnls > 0).mean() * 100), 1),
        "mean_mfe_pct": round(float(mfe.mean()) * 100, 3), "mean_mae_pct": round(float(mae.mean()) * 100, 3),
        "mfe_over_abs_mae": round(float(mfe.mean() / abs(mae.mean())), 3) if mae.mean() != 0 else np.nan,
    }
    return summary, mfe_mae_rows


def run_symbol(symbol: str):
    full = _load_full_cached(symbol)
    if symbol.upper() in HOLDOUT_START:
        # This symbol has an ALREADY-FIXED, frozen HOLDOUT_START (the original 9-symbol
        # baseline) -- truncate to it explicitly rather than recomputing a fresh dynamic
        # 80%-of-current-data split, which would drift later (and cross into HOLDOUT
        # territory) now that the underlying klines CSV has grown since that boundary
        # was originally fixed. This is the critical HOLDOUT-safety fix for this sanity check.
        full = pre_holdout(full, symbol)
    n = len(full)
    data_start = full.index[0]
    safe_end = full.index[int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))] if symbol.upper() not in HOLDOUT_START \
        else full.index[-1]
    initial, test_m, step_m, adapted = decide_fold_params(data_start, safe_end)
    folds = build_folds(data_start, safe_end, initial, test_m, step_m)
    print(f"[{symbol}] {len(folds)} folds (adapted={adapted})")
    rows = []
    for i, (fstart, ftrain_end, ftest_end) in enumerate(folds, 1):
        train_df = full.loc[(full.index >= fstart) & (full.index < ftrain_end)]
        test_df = full.loc[(full.index >= ftrain_end) & (full.index < ftest_end)]
        summary, _ = process_fold_logistic(symbol, i, train_df, test_df)
        print(f"  fold {i}: {summary}")
        rows.append(summary)
    return rows


OUT_PATH = os.path.join(MECH3_DOCS, "strategy_a_phase5_logistic_results.csv")


def already_done_symbols() -> set:
    if not os.path.exists(OUT_PATH):
        return set()
    return set(pd.read_csv(OUT_PATH)["symbol"].unique())


def append_rows(rows: list):
    df = pd.DataFrame(rows)
    if os.path.exists(OUT_PATH):
        df = pd.concat([pd.read_csv(OUT_PATH), df], ignore_index=True)
    df.to_csv(OUT_PATH, index=False)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None, help="run just one symbol, checkpointed")
    args = parser.parse_args()

    if args.symbol:
        targets = [args.symbol]
    else:
        targets = [s for s in NEW_ASSETS + ["BTCUSDT", "ETHUSDT"] if s not in already_done_symbols()]

    for sym in targets:
        try:
            rows = run_symbol(sym)
        except Exception as e:
            rows = [{"fold": None, "symbol": sym, "n_trades": 0, "reason": f"ERROR: {e}"}]
        append_rows(rows)
        print(f"[{sym}] checkpointed -> {OUT_PATH}")


if __name__ == "__main__":
    main()
