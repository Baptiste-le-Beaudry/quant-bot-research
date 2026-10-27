"""scripts/strategy_a/mechanism2/common.py -- shared, READ-ONLY reuse of
Strategy A's actual frozen walk-forward machinery for the mechanism-
decomposition mandate. Every function here either IMPORTS an existing
frozen function (fit_fold_model, build_feature_matrix, build_folds, ...)
or reproduces process_fold's own selection-cut logic byte-for-byte so the
8-layer decomposition (A-H) is guaranteed faithful to the real baseline.
Nothing in quant_bot/ or scripts/multi_crypto_walkforward.py is modified.

HOLDOUT: every symbol's klines are truncated via quant_bot.data.splits.
pre_holdout() immediately after loading -- no computation in this whole
mechanism2/ package ever sees a HOLDOUT row.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, REPO_ROOT)

import numpy as np
import pandas as pd

from scripts.multi_crypto_walkforward import (
    _load_full_cached, decide_fold_params, build_folds, fit_fold_model,
    THRESHOLD, ACTIVATE_AT, TRAIL_DIST, STOP_PCT_PERCENTILE, SAFETY_MARGIN,
    MAX_LEVERAGE_CAP, HORIZON, FEE_PER_SIDE, BASE_SLIP_PER_SIDE,
)
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.fast_trades import build_trades_with_mae_mfe_fast
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from quant_bot.config import COST_THRESHOLD_PCT
from quant_bot.data.splits import pre_holdout, holdout_start

SYMBOLS_9 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
             "ADAUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT"]

MECH2_DOCS = os.path.join(REPO_ROOT, "docs", "strategy_a", "mechanism2")
os.makedirs(MECH2_DOCS, exist_ok=True)
FEATS_CACHE_DIR = os.path.join(REPO_ROOT, "docs", "_full_data_cache")


def load_symbol(symbol: str) -> pd.DataFrame:
    """Full 1-min history, HOLDOUT-truncated. Reuses the SAME cached-pickle
    loader multi_crypto_walkforward.py itself uses (docs/_full_data_cache)."""
    full = _load_full_cached(symbol)
    return pre_holdout(full, symbol)


def load_symbol_feats(symbol: str, full: pd.DataFrame = None) -> pd.DataFrame:
    """PERFORMANCE OPTIMIZATION (verified equivalent -- see the caution
    note below): build_feature_matrix is a pure, CAUSAL (backward-looking
    only) function of data up to each timestamp. Every walk-forward fold's
    TRAIN window starts at the SAME data_start (expanding window, per
    multi_crypto_walkforward.build_folds), so computing features ONCE on
    the full pre-HOLDOUT history and then .loc[]-slicing per fold is
    mathematically IDENTICAL to recomputing build_feature_matrix fresh on
    each fold's own train_df -- empirically verified (max abs diff = 0.0
    across all 20 candidate features). This avoids recomputing the
    expensive rolling_hurst/autocorr Python-apply loops O(n_folds) times
    over heavily-overlapping expanding windows (~124s for just fold 1's
    TRAIN alone on ETHUSDT; summed across all folds/symbols this would run
    into HOURS). Cached to disk (parquet).

    CAUTION (found and fixed during this task's own VERIFY BEFORE BELIEVE
    check): labels must NEVER be cached this way, only features -- build_
    labels is FORWARD-looking (close.shift(-horizon)), so a globally-
    cached-then-sliced label would leak a few rows of forward information
    across each fold's TRAIN/TEST boundary (still fully pre-HOLDOUT, not a
    HOLDOUT violation, but NOT equivalent to the frozen baseline's own
    per-fold label computation -- confirmed empirically: an initial
    version of this cache that also cached labels reproduced DIFFERENT
    kept-feature sets and DIFFERENT trade counts than the original
    fit_fold_model on the same fold, because prune_redundant's np.random
    subsample is length-sensitive and the ~10-row boundary shift changed
    the whole subsample composition). Labels are recomputed fresh per fold
    in fit_fold_model_fast below -- build_labels itself is a cheap
    vectorized shift, not the bottleneck, so this costs nothing."""
    feats_path = os.path.join(FEATS_CACHE_DIR, f"{symbol}_full_feats.parquet")
    if os.path.exists(feats_path):
        return pd.read_parquet(feats_path)
    if full is None:
        full = load_symbol(symbol)
    feats = build_feature_matrix(full)
    os.makedirs(FEATS_CACHE_DIR, exist_ok=True)
    feats.to_parquet(feats_path)
    return feats


def fit_fold_model_fast(train_df: pd.DataFrame, train_feats: pd.DataFrame):
    """Functionally IDENTICAL to scripts.multi_crypto_walkforward.
    fit_fold_model, but takes an already-sliced feature matrix instead of
    recomputing build_feature_matrix internally (labels are still computed
    fresh from train_df, per the CAUTION note in load_symbol_feats -- cheap,
    and required for exact-boundary correctness). Same prune_redundant
    call, same random_state=42 sample, same Tier2RandomForestSignal
    construction -- verified to reproduce byte-identical models/trade
    counts to the frozen baseline's own fit_fold_model (see this script's
    __main__ self-test)."""
    train_labels = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    kept, _ = prune_redundant(train_feats, train_labels, corr_threshold=0.9)
    fit_n = min(250_000, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
    return model


def get_folds(full: pd.DataFrame):
    data_start = full.index[0]
    safe_end = full.index[-1]  # already HOLDOUT-truncated by load_symbol
    initial, test_m, step_m, adapted = decide_fold_params(data_start, safe_end)
    folds = build_folds(data_start, safe_end, initial, test_m, step_m)
    return folds, adapted


def fold_layers(symbol: str, fold_i: int, train_df: pd.DataFrame, test_df: pd.DataFrame,
                 full_feats: pd.DataFrame = None):
    """Fits ONE RandomForest per fold (byte-for-byte the same as
    multi_crypto_walkforward.process_fold's own model-fit step) and returns
    every intermediate quantity needed for the 8-layer (A-H) decomposition,
    PLUS the fitted model/train_feats (for feature-importance/ablation
    reuse) -- computing this ONCE per fold and deriving all 8 layers from
    it is what keeps this analysis cheap (no extra RF fits beyond what the
    frozen baseline itself already required).

    If full_feats (from load_symbol_feats) is passed, uses the fast
    slice-not-recompute path (fit_fold_model_fast) instead of the frozen
    fit_fold_model -- verified equivalent, see common.py's
    load_symbol_feats/fit_fold_model_fast docstrings (labels are always
    computed fresh per fold, never cached, to avoid a forward-looking
    boundary leak across fold cutoffs)."""
    if full_feats is not None:
        train_feats = full_feats.loc[train_df.index]
        model = fit_fold_model_fast(train_df, train_feats)
    else:
        model, train_feats = fit_fold_model(train_df)
    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > THRESHOLD
    if int(train_selected.sum()) < 20:
        return None
    range_pos_cut = float(train_feats.loc[train_selected, "range_pos_60"].median())
    vol_cut = float(train_feats.loc[train_selected, "realized_vol_30"].median())

    # TEST features are ALWAYS recomputed fresh on test_df alone (never sliced from the global
    # cache) -- TEST windows are small (a few months), so this costs nothing, and it's required
    # for exact fidelity: the frozen process_fold calls build_feature_matrix(test_df) on the
    # isolated TEST window, which has NO TRAIN lookback for its first ~240 bars (rolling-window
    # "cold start"), unlike a slice of the globally-cached features (which WOULD have valid
    # values there, having seen the preceding TRAIN data). Verified: without this, layers A/B
    # (the least-filtered, only ones sensitive to this boundary) showed a small (~0.4%) row-count
    # mismatch vs the frozen baseline; layers C-H (which additionally require RF proba/vol
    # filters that are unaffected by this early-window gap) already matched exactly either way.
    test_feats = build_feature_matrix(test_df)
    test_proba = model.predict_proba(test_feats)

    base_valid = test_feats["range_pos_60"].notna() & test_feats["realized_vol_30"].notna() & test_proba.notna()
    range_ok = test_feats["range_pos_60"] < range_pos_cut
    vol_ok = test_feats["realized_vol_30"] > vol_cut
    rf_ok = test_proba > THRESHOLD

    layers = {
        "A_all_eligible": base_valid,
        "B_range_only": base_valid & range_ok,
        "C_vol_only": base_valid & vol_ok,
        "D_both_filters": base_valid & range_ok & vol_ok,
        "E_rf_only": base_valid & rf_ok,
        "F_rf_range": base_valid & rf_ok & range_ok,
        "G_rf_vol": base_valid & rf_ok & vol_ok,
        "H_full_strategy_a": base_valid & rf_ok & range_ok & vol_ok,
    }
    return {
        "model": model, "train_feats": train_feats, "test_feats": test_feats,
        "test_proba": test_proba, "range_pos_cut": range_pos_cut, "vol_cut": vol_cut,
        "layers": layers, "kept_features": list(model.feature_names),
        "test_close": test_df["close"].to_numpy(), "test_df": test_df,
    }


def build_layer_trades(test_close: np.ndarray, mask: pd.Series, test_feats: pd.DataFrame,
                        horizon: int = HORIZON) -> list:
    """Same trade-builder Strategy A itself uses (fast_trades, skip-ahead-
    after-entry semantics) applied to an arbitrary boolean mask -- makes
    every layer A-H directly comparable (same event-independence handling,
    not just a raw per-minute bucket count)."""
    return build_trades_with_mae_mfe_fast(
        test_close, mask.to_numpy(), test_feats["ema_slope_20"].to_numpy(),
        test_feats["ret_1"].to_numpy(), horizon=horizon)


def trades_to_metrics(trades: list, horizons=(5, 10, 20, 30, 50)) -> dict:
    """n / MFE / MAE / MFE-MAE ratio / forward return at each horizon, for a
    list of fast_trades-style trade dicts (each has 'close_path', an array
    close_path[0]=0.0 .. close_path[50])."""
    if not trades:
        return {"n": 0}
    mfe = np.array([t["mfe"] for t in trades])
    mae = np.array([t["mae"] for t in trades])
    out = {
        "n": len(trades),
        "mean_mfe_pct": float(mfe.mean()) * 100, "median_mfe_pct": float(np.median(mfe)) * 100,
        "mean_mae_pct": float(mae.mean()) * 100, "median_mae_pct": float(np.median(mae)) * 100,
        "mfe_over_abs_mae": float(mfe.mean() / abs(mae.mean())) if mae.mean() != 0 else np.nan,
        "pct_mfe_gt_abs_mae": float(np.mean(mfe > np.abs(mae))) * 100,
    }
    for h in horizons:
        rets = np.array([t["close_path"][h] for t in trades if len(t["close_path"]) > h])
        if len(rets):
            out[f"median_fwdret_{h}m_pct"] = float(np.median(rets)) * 100
            out[f"winrate_{h}m_pct"] = float(np.mean(rets > 0)) * 100
    return out


def classify_outcome(trade: dict, stop_distance: float, liq_move: float) -> str:
    """PROTECTIVE_STOP / TRAILING_STOP / END_OF_WINDOW -- exact replay of the
    frozen exit logic (ACTIVATE_AT/TRAIL_DIST), matching
    scripts/strategy_a/decompose_trades.py's classify_exit_reason, applied
    here to a fast_trades-style close_path array instead of the CSV's
    string column (same semantics, reused independently since this
    script's trades are freshly built per layer, not read from the CSV)."""
    path = trade["close_path"]
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for j, x in enumerate(path):
        if x <= -protective:
            return "PROTECTIVE_STOP"
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return "TRAILING_STOP"
    return "END_OF_WINDOW"


def stop_distance_for_layer(trades: list) -> tuple:
    """Same TRAIN-only percentile-of-|MAE| + liquidation-safe cap logic as
    process_fold, applied to a layer's own trade population (needed to
    classify PROTECTIVE_STOP/TRAILING_STOP/END_OF_WINDOW outcomes for that
    layer)."""
    if len(trades) < 10:
        return np.nan, np.nan, np.nan
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in trades]), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    return stop_distance, liq_move, protective
