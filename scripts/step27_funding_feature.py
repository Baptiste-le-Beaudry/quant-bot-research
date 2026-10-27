"""
scripts/step27_funding_feature.py — Étape 27/28: does the funding rate,
used as a PREDICTIVE FEATURE (not just a cost, its only role all session
so far) improve the classifier? Funding regime (persistently positive =
crowded longs paying shorts, often preceding mean-reversion; persistently
negative = crowded shorts) is a classic crypto momentum/reversal signal
that this project's feature set has never included.

Full-history funding data was just downloaded back to 2019-03-28 for both
symbols (previously only had 2023-05+, which didn't cover TRAIN at all --
would have made this experiment impossible before). Feature added:
funding_ma_3 = rolling mean of the last 3 funding settlements (~24h) as of
each 1-min bar, via merge_asof (no lookahead: only settlements STRICTLY
before the bar's own timestamp are used).

Compares: (1) classifier AUC with vs without the funding feature, (2)
whether it's kept or dropped by prune_redundant and its importance rank if
kept, (3) trading result (n/PF/return) with vs without, same entry
filter/exit pipeline as BASELINE_CANDIDATE_V2 otherwise unchanged.

Usage:
    python scripts/step27_funding_feature.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from quant_bot.config import DATA_DIR, COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
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

FUNDING_FILES = {
    "BTCUSDT": os.path.join(DATA_DIR, "BTCUSDT_funding_20190328_20260818.csv"),
    "ETHUSDT": os.path.join(DATA_DIR, "ETHUSDT_funding_20190328_20260818.csv"),
}


def load_funding_full(symbol: str) -> pd.Series:
    df = pd.read_csv(FUNDING_FILES[symbol])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    return df.set_index("timestamp")["fundingRate"].sort_index()


def add_funding_feature(feats: pd.DataFrame, funding: pd.Series) -> pd.DataFrame:
    funding_ma3 = funding.rolling(3).mean()
    funding_ma3.name = "funding_ma_3"
    out = feats.copy()
    merged = pd.merge_asof(
        pd.DataFrame(index=feats.index).reset_index().rename(columns={"index": "ts", "timestamp": "ts"}),
        funding_ma3.reset_index().rename(columns={"timestamp": "ts"}),
        on="ts", direction="backward",
    )
    out["funding_ma_3"] = merged["funding_ma_3"].to_numpy()
    out["funding_ma_3"] = out["funding_ma_3"].fillna(0.0)
    return out


def resolve(path, stop_distance, leverage):
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2


def simulate(trades, stop_distance, leverage) -> dict:
    pnls = np.array([resolve(t["close_path"], stop_distance, leverage) for t in trades]) * CAPITAL * RISK_PCT * leverage
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    return {"n_trades": len(pnls), "profit_factor": round(pf, 3),
            "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3)}


def fit_and_eval(use_funding: bool):
    train_feats_all, train_labels_all = {}, {}
    funding_series = {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        feats = build_feature_matrix(df)
        funding_series[symbol] = load_funding_full(symbol)
        if use_funding:
            feats = add_funding_feature(feats, funding_series[symbol])
        train_feats_all[symbol] = feats
        train_labels_all[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats_all.values(), ignore_index=True)
    y_train = pd.concat(train_labels_all.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    return model, kept, funding_series


def main():
    for use_funding in [False, True]:
        label = "WITH funding_ma_3 feature" if use_funding else "WITHOUT funding feature (baseline)"
        print("=" * 100)
        print(f"  {label}")
        print("=" * 100)
        model, kept, funding_series = fit_and_eval(use_funding)
        print(f"  {len(kept)} features kept: {'funding_ma_3 KEPT' if 'funding_ma_3' in kept else 'funding_ma_3 not in feature set' if use_funding else '(n/a)'}")
        if use_funding and "funding_ma_3" in kept:
            imp = model.feature_importance()
            rank = list(imp.index).index("funding_ma_3") + 1
            print(f"  funding_ma_3 importance={imp['funding_ma_3']:.4f} (rank {rank}/{len(kept)})")

        for symbol in ["ETHUSDT", "BTCUSDT"]:
            train_df = load_split(symbol, "train", verbose=False)
            train_feats = build_feature_matrix(train_df)
            if use_funding:
                train_feats = add_funding_feature(train_feats, funding_series[symbol])
            train_proba = model.predict_proba(train_feats)
            train_selected = train_proba > THRESHOLD
            if train_selected.sum() < 20:
                print(f"  {symbol}: train-selected population < 20, skipping")
                continue
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
            if use_funding:
                val_feats = add_funding_feature(val_feats, funding_series[symbol])
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
            val_label = build_labels(val_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
            valid = val_proba.notna() & val_label.notna()
            auc = roc_auc_score(val_label[valid], val_proba[valid])

            r = simulate(val_trades, stop_distance, leverage)
            print(f"  {symbol}: AUC={auc:.4f}  n={r.get('n_trades',0):>4} "
                  f"PF={r.get('profit_factor',float('nan')):>7.3f} "
                  f"ret={r.get('total_return_pct',float('nan')):>+7.3f}%")
        print()


if __name__ == "__main__":
    main()
