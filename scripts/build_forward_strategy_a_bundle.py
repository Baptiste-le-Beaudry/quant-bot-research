"""Fit the frozen Strategy-A inference bundle using pre-HOLDOUT data only.

This finalizes already-adopted parameters for forward paper; it performs no
parameter search and never reads rows at or after each registered boundary.
"""
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quant_bot.config import COST_THRESHOLD_PCT, DATA_DIR
from quant_bot.data.splits import assert_pre_holdout, holdout_start
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.forward.signal_engine import FrozenStrategyBundle, FrozenSymbolConfig, save_bundle
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.fast_trades import build_trades_with_mae_mfe_fast


ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT")
STOP_PERCENTILE = {symbol: 90 for symbol in SYMBOLS} | {"XRPUSDT": 80, "LINKUSDT": 95}
THRESHOLD, HORIZON = 0.70, 10
SAFETY_MARGIN, STOP_OUT_FRACTION, MAX_LEVERAGE = 0.75, 0.5, 30.0
GUARD_ROWS = 1_440


def safe_load(symbol: str) -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")))
    if not paths:
        raise FileNotFoundError(symbol)
    first = pd.read_csv(paths[-1], usecols=["timestamp"], parse_dates=["timestamp"], nrows=1)
    start = pd.to_datetime(first.iloc[0, 0], utc=True)
    nrows = int((holdout_start(symbol) - start) / pd.Timedelta(minutes=1)) - GUARD_ROWS
    frame = pd.read_csv(paths[-1], index_col=0, parse_dates=True, nrows=nrows)
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame.sort_index()
    assert_pre_holdout(frame, symbol)
    return frame


def fit_model(frames: list[pd.DataFrame]):
    features, labels = [], []
    for frame in frames:
        features.append(build_feature_matrix(frame))
        labels.append(build_labels(frame["close"], HORIZON, COST_THRESHOLD_PCT))
    X = pd.concat(features, ignore_index=True)
    y = pd.concat(labels, ignore_index=True)
    kept, _ = prune_redundant(X, y, corr_threshold=0.9)
    fit_n = min(250_000, len(X))
    sampled = X.sample(n=fit_n, random_state=42).index
    return Tier2RandomForestSignal(kept, n_estimators=100).fit(X.loc[sampled], y.loc[sampled])


def calibrate(model, frames: list[pd.DataFrame], stop_percentile: int):
    prepared = [(frame, build_feature_matrix(frame)) for frame in frames]
    probabilities = [model.predict_proba(features) for _, features in prepared]
    selected_features = pd.concat(
        [features.loc[probability > THRESHOLD] for (_, features), probability in zip(prepared, probabilities)],
        ignore_index=True,
    )
    range_cut = float(selected_features["range_pos_60"].median())
    vol_cut = float(selected_features["realized_vol_30"].median())
    trades = []
    for (frame, features), probability in zip(prepared, probabilities):
        selected = ((probability > THRESHOLD)
                    & (features["range_pos_60"] < range_cut)
                    & (features["realized_vol_30"] > vol_cut)).to_numpy()
        trades.extend(build_trades_with_mae_mfe_fast(
            frame["close"].to_numpy(), selected,
            features["ema_slope_20"].to_numpy(), features["ret_1"].to_numpy(),
            horizon=HORIZON))
    if len(trades) < 10:
        raise RuntimeError("insufficient calibration trades")
    stop = float(np.percentile(np.abs([trade["mae"] for trade in trades]), stop_percentile))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop, MAX_LEVERAGE)
    return range_cut, vol_cut, stop, leverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "forward_paper" / "strategy_a_bundle.pkl")
    args = parser.parse_args()
    frames = {symbol: safe_load(symbol) for symbol in SYMBOLS}
    configs = {}

    joint_model = fit_model([frames["BTCUSDT"], frames["ETHUSDT"]])
    for symbol in ("BTCUSDT", "ETHUSDT"):
        range_cut, vol_cut, stop, leverage = calibrate(
            joint_model, [frames[symbol]], STOP_PERCENTILE[symbol])
        configs[symbol] = FrozenSymbolConfig(symbol, joint_model, THRESHOLD,
                                              range_cut, vol_cut, stop, leverage)

    for symbol in ("BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
                   "LINKUSDT", "LTCUSDT"):
        model = fit_model([frames[symbol]])
        range_cut, vol_cut, stop, leverage = calibrate(
            model, [frames[symbol]], STOP_PERCENTILE[symbol])
        configs[symbol] = FrozenSymbolConfig(symbol, model, THRESHOLD,
                                              range_cut, vol_cut, stop, leverage)

    # SOL transfer mode: BTC+ETH model and pooled BTC+ETH TRAIN calibration.
    range_cut, vol_cut, stop, leverage = calibrate(
        joint_model, [frames["BTCUSDT"], frames["ETHUSDT"]], 90)
    configs["SOLUSDT"] = FrozenSymbolConfig("SOLUSDT", joint_model, THRESHOLD,
                                             range_cut, vol_cut, stop, leverage)
    boundary = min(holdout_start(symbol) for symbol in SYMBOLS).isoformat()
    bundle = FrozenStrategyBundle(
        strategy_id="STRATEGY_A_9SYM_XRP80_LINK95",
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        training_boundary=boundary, configs=configs, live_enabled=False,
    )
    save_bundle(bundle, args.out)
    print(f"bundle -> {args.out}")
    for symbol, config in configs.items():
        print(symbol, config.stop_distance, config.leverage_safe,
              config.range_pos_cut, config.realized_vol_cut)


if __name__ == "__main__":
    main()
