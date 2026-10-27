"""Resumable raw-data reproduction of the adopted pre-HOLDOUT trade exports.

Unlike the historical loaders, this reads only the preregistered first 80% of
each CSV via ``nrows``; HOLDOUT rows are never loaded into memory.
"""
import argparse
import glob
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from quant_bot.config import DATA_DIR
from quant_bot.data.splits import assert_pre_holdout, holdout_start
from scripts import multi_crypto_walkforward as multi
from scripts import multi_crypto_transfer_walkforward as transfer
from scripts import walk_forward_v3_trade_export as btceth


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "validation_reproduction"
TOTAL_BARS = {
    "BTCUSDT": 3_649_323, "ETHUSDT": 3_534_736, "BNBUSDT": 3_431_485,
    "XRPUSDT": 3_481_865, "DOGEUSDT": 3_213_986, "ADAUSDT": 3_445_885,
    "LINKUSDT": 3_466_046, "LTCUSDT": 3_477_557,
}
# The historical screen persisted HOLDOUT_START at date precision, while its
# positional 80% split can fall later within that UTC date. Subtract a full
# day from the positional count so the loader cannot cross the conservative
# midnight boundary. Walk-forward folds end on month boundaries, so this
# guard band changes no registered fold while keeping forbidden OHLCV unread.
BOUNDARY_GUARD_ROWS = 1_440


def safe_load(symbol: str) -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")))
    if not paths:
        raise FileNotFoundError(symbol)
    if symbol in TOTAL_BARS:
        nrows = int(TOTAL_BARS[symbol] * 0.80) - BOUNDARY_GUARD_ROWS
    else:
        # For newly supported symbols, derive a conservative maximum from the
        # first timestamp and the registered boundary. Missing minutes can only
        # make this under-read; the guard ensures it cannot reach HOLDOUT.
        first = pd.read_csv(paths[-1], index_col=0, parse_dates=True, nrows=1)
        first.index = pd.to_datetime(first.index, utc=True)
        nrows = int((holdout_start(symbol) - first.index[0]) / pd.Timedelta(minutes=1)) - BOUNDARY_GUARD_ROWS
    frame = pd.read_csv(paths[-1], index_col=0, parse_dates=True, nrows=nrows)
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame.sort_index()
    assert_pre_holdout(frame, symbol)
    return frame


def paths_for(tag):
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT / f"{tag}_trades.csv", OUT / f"{tag}_done_folds.txt"


def load_state(tag):
    output, marker = paths_for(tag)
    try:
        rows = pd.read_csv(output).to_dict("records") if output.exists() else []
    except pd.errors.EmptyDataError:
        rows = []
    done = {int(x) for x in marker.read_text().split()} if marker.exists() else set()
    return output, marker, rows, done


def save(output, marker, rows, done):
    pd.DataFrame(rows).to_csv(output, index=False)
    marker.write_text(" ".join(map(str, sorted(done))) + "\n", encoding="utf-8")


def reproduce_single(symbol, max_folds, stop_percentile=90):
    full = safe_load(symbol)
    # Every expanding TRAIN slice starts at full.index[0], and all features are
    # causal. Compute that prefix matrix once; slicing it is bit-identical to
    # rebuilding the same prefix for every fold. TEST slices still call the
    # historical builder independently, preserving its registered warm-up.
    original_builder = multi.build_feature_matrix
    cached_train_features = original_builder(full)

    def cached_builder(frame):
        if len(frame) and frame.index[0] == full.index[0]:
            return cached_train_features.loc[frame.index]
        return original_builder(frame)

    multi.build_feature_matrix = cached_builder
    original_stop = multi.STOP_PCT_PERCENTILE
    multi.STOP_PCT_PERCENTILE = stop_percentile
    safe_end = holdout_start(symbol)
    initial, test_m, step_m, _ = multi.decide_fold_params(full.index[0], safe_end)
    folds = multi.build_folds(full.index[0], safe_end, initial, test_m, step_m)
    output, marker, rows, done = load_state(symbol)
    processed = 0
    try:
        for fold_i, (start, train_end, test_end) in enumerate(folds, 1):
            if fold_i in done or processed >= max_folds:
                continue
            train = full[(full.index >= start) & (full.index < train_end)]
            test = full[(full.index >= train_end) & (full.index < test_end)]
            _, exports, _ = multi.process_fold(symbol, fold_i, train, test)
            rows.extend(exports or [])
            done.add(fold_i)
            save(output, marker, rows, done)
            processed += 1
            print(f"{symbol} fold {fold_i}/{len(folds)} -> {len(exports or [])} trades", flush=True)
    finally:
        multi.build_feature_matrix = original_builder
        multi.STOP_PCT_PERCENTILE = original_stop


def reproduce_sol_transfer(max_folds):
    """Rebuild adopted SOL using BTC+ETH TRAIN-only transfer calibration."""
    sources = {symbol: safe_load(symbol) for symbol in ("BTCUSDT", "ETHUSDT")}
    target = safe_load("SOLUSDT")
    original_builder = transfer.build_feature_matrix
    all_frames = {**sources, "SOLUSDT": target}
    cached = {symbol: original_builder(frame) for symbol, frame in all_frames.items()}

    def cached_builder(frame):
        for symbol, source in all_frames.items():
            if (len(frame) and frame.index[0] == source.index[0]
                    and float(frame["close"].iloc[0]) == float(source["close"].iloc[0])):
                return cached[symbol].loc[frame.index]
        return original_builder(frame)

    transfer.build_feature_matrix = cached_builder
    start = max(frame.index[0] for frame in sources.values())
    folds = transfer.build_folds(start, transfer.SAFE_END)
    output, marker, rows, done = load_state("SOLUSDT_TRANSFER")
    processed = 0
    try:
        for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
            if fold_i in done or processed >= max_folds:
                continue
            train = {s: frame[(frame.index >= t0) & (frame.index < train_end)]
                     for s, frame in sources.items()}
            test = target[(target.index >= train_end) & (target.index < test_end)]
            _, exports, _ = transfer.process_fold("SOLUSDT", fold_i, train, test)
            rows.extend(exports or [])
            done.add(fold_i)
            save(output, marker, rows, done)
            processed += 1
            print(f"SOLUSDT transfer fold {fold_i}/{len(folds)} -> {len(exports or [])} trades", flush=True)
    finally:
        transfer.build_feature_matrix = original_builder


def reproduce_btceth(max_folds):
    full = {symbol: safe_load(symbol) for symbol in ("BTCUSDT", "ETHUSDT")}
    fit_globals = btceth.fit_fold_model.__globals__
    original_train_builder = fit_globals["build_feature_matrix"]
    cached_train_features = {symbol: original_train_builder(frame) for symbol, frame in full.items()}

    def cached_joint_builder(frame):
        for symbol, source in full.items():
            if (len(frame) and frame.index[0] == source.index[0]
                    and float(frame["close"].iloc[0]) == float(source["close"].iloc[0])):
                return cached_train_features[symbol].loc[frame.index]
        return original_train_builder(frame)

    fit_globals["build_feature_matrix"] = cached_joint_builder
    start = max(frame.index[0] for frame in full.values())
    safe_end = min(holdout_start("BTCUSDT"), holdout_start("ETHUSDT"))
    folds = btceth.build_folds(start, safe_end)
    output, marker, rows, done = load_state("BTCETH")
    processed = 0
    try:
        for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
            if fold_i in done or processed >= max_folds:
                continue
            train = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in full}
            test = {s: full[s][(full[s].index >= train_end) & (full[s].index < test_end)] for s in full}
            model, train_features = btceth.fit_fold_model(train)
            exports = []
            for symbol in full:
                exports.extend(btceth.export_fold_symbol(symbol, train[symbol], test[symbol], model, train_features[symbol], fold_i))
            rows.extend(exports)
            done.add(fold_i)
            save(output, marker, rows, done)
            processed += 1
            print(f"BTCETH fold {fold_i}/{len(folds)} -> {len(exports)} trades", flush=True)
    finally:
        fit_globals["build_feature_matrix"] = original_train_builder


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True, choices=["BTCETH", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT_TRANSFER"])
    parser.add_argument("--max-folds", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, default=OUT)
    parser.add_argument("--stop-pct", type=int, default=None)
    args = parser.parse_args()
    OUT = args.out_dir
    if args.symbol == "BTCETH":
        reproduce_btceth(args.max_folds)
    elif args.symbol == "SOLUSDT_TRANSFER":
        reproduce_sol_transfer(args.max_folds)
    else:
        expected = 80 if args.symbol == "XRPUSDT" else 95 if args.symbol == "LINKUSDT" else 90
        stop = expected if args.stop_pct is None else args.stop_pct
        reproduce_single(args.symbol, args.max_folds, stop)


if __name__ == "__main__":
    main()
