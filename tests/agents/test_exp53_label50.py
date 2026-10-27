"""Exp 53 regression tests -- synthetic data only, isolated tmp dirs, never the real data paths."""
import numpy as np
import pandas as pd
import pytest

from quant_bot.config import COST_THRESHOLD_PCT
from quant_bot.features.pipeline import prune_redundant
from scripts.agents import exp53_label50 as E


def _close(n, seed=0):
    r = np.random.default_rng(seed).normal(0, 0.002, n)
    return 100 * np.exp(np.cumsum(r))


def test_label50_is_strictly_future_and_never_crosses_train_end():
    close = _close(1000)
    train = close[:600]
    y = E.train_labels(train, 50)
    # last 50 TRAIN rows have no target inside TRAIN -> NaN (never 0, never filled from TEST)
    assert np.isnan(y[-50:]).all() and not np.isnan(y[:-50]).any()
    fwd = train[50:] / train[:-50] - 1
    np.testing.assert_array_equal(y[:-50], (fwd > COST_THRESHOLD_PCT).astype(float))
    # changing anything after TRAIN end (or the bar itself only in the future part) leaves labels unchanged
    other = close.copy()
    other[600:] *= 3.0
    np.testing.assert_array_equal(E.train_labels(other[:600], 50), y)
    # label at t depends on close[t+50]: perturb close[t+50] only
    t = 100
    bumped = train.copy()
    bumped[t + 50] = train[t] * (1 + COST_THRESHOLD_PCT + 0.01)
    y2 = E.train_labels(bumped, 50)
    assert y2[t] == 1.0
    assert (y2[:t + 50 - 50] == y[:t]).all()  # rows before t unaffected unless their t+50 moved
    diff = np.flatnonzero(np.nan_to_num(y2, nan=-1) != np.nan_to_num(y, nan=-1))
    assert set(diff) <= {t, t + 50}  # only the label of t (fwd) and of t+50 (its own base price) may change


def test_ref_label_horizon_is_10():
    close = _close(300, 1)
    y = E.train_labels(close, E.H_REF)
    assert np.isnan(y[-10:]).all() and not np.isnan(y[:-10]).any()


def test_sample_positions_match_pandas_sample():
    df = pd.DataFrame({"a": np.arange(5000)})
    for n in (100, 5000, 9000):
        exp = df.sample(n=min(n, len(df)), random_state=42).index.to_numpy()
        np.testing.assert_array_equal(E.pandas_sample_positions(len(df), n, 42), exp)


def test_lowmem_prune_matches_pipeline():
    rng = np.random.default_rng(3)
    n = 6000
    base = rng.normal(size=(n, 6))
    X = np.column_stack([base, base[:, :3] + 0.05 * rng.normal(size=(n, 3)), rng.normal(size=(n, 15))])
    X = X.astype(np.float32)
    X[rng.choice(n, 200, replace=False), 4] = np.nan
    y = (base[:, 0] + rng.normal(size=n) > 0.5).astype(float)
    y[-30:] = np.nan
    names = [f"f{i}" for i in range(X.shape[1])]
    df = pd.DataFrame(X, columns=names)
    exp, _ = prune_redundant(df, pd.Series(y), corr_threshold=0.9, max_rows=2000)
    got = E.prune_redundant_lowmem(E.Pooled([X[:2500], X[2500:]]), y, names, max_rows=2000)
    assert got == exp
    assert len(got) < len(names)


def test_sequence_one_position_per_symbol():
    np.testing.assert_array_equal(E.sequence(np.array([0, 1, 49, 50, 51, 120, 169, 170]), 50), [0, 50, 120, 170])


def test_calibrate_threshold_matches_count_and_uses_given_arrays_only():
    rng = np.random.default_rng(5)
    train = {}
    for s in E.TRAIN_SYMS:
        p = rng.uniform(0.3, 0.95, 20000)
        train[s] = (p, rng.uniform(0, 1, 20000).astype(np.float32), rng.uniform(0, 0.01, 20000).astype(np.float32))
    target = 900
    t, c = E.calibrate_threshold(train, target)
    assert abs(c - target) <= 5
    assert E.train_signal_count(train, t) == c


def _synthetic_split(seed, n_train=8000, n_test=3000, test_shift=0.0):
    rng = np.random.default_rng(seed)
    train, test = {}, {}
    for j, s in enumerate(E.ALL_SYMS):
        n = n_train + n_test
        close = _close(n, seed + j)
        fwd10 = np.r_[close[10:] / close[:-10] - 1, np.zeros(10)]
        f = rng.normal(size=(n, len(E.FEATURES))).astype(np.float32)
        f[:, E.FEATURES.index("ret_1")] = (fwd10 * 300 + rng.normal(0, 0.5, n)).astype(np.float32)
        f[:, E.FEATURES.index("range_pos_60")] = rng.uniform(0, 1, n).astype(np.float32)
        f[:, E.FEATURES.index("realized_vol_30")] = rng.uniform(0, 0.01, n).astype(np.float32)
        f[:30] = np.nan
        times = (pd.date_range("2024-01-01", periods=n, freq="1min").tz_localize(None).to_numpy().astype("int64"))
        if s in E.TRAIN_SYMS:
            train[s] = (f[:n_train], close[:n_train])
        tf = f[n_train:].copy()
        tf += np.float32(test_shift)
        test[s] = (tf, times[n_train:])
    return train, test


def test_threshold_and_cutoffs_depend_on_train_only(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "FIT_ROWS", 5000)
    monkeypatch.setattr(E, "MI_ROWS", 3000)
    train, test_a = _synthetic_split(11)
    _, test_b = _synthetic_split(11, test_shift=0.7)  # completely different TEST features
    ra = E.run_fold(train, test_a, n_jobs=1)
    rb = E.run_fold(train, test_b, n_jobs=1)
    assert ra["info"]["thr_L50"] == rb["info"]["thr_L50"]
    assert ra["info"]["cutoffs"] == rb["info"]["cutoffs"]
    assert ra["info"]["train_signals_REF"] > 0
    # L50 threshold reproduces REF's TRAIN signal count as closely as the bisection allows
    assert abs(ra["info"]["train_signals_L50"] - ra["info"]["train_signals_REF"]) <= max(3, 0.02 * ra["info"]["train_signals_REF"])
    assert ra["info"]["thresholds"]["REF"] == 0.70 and ra["info"]["thresholds"]["L50_070"] == 0.70
    # TEST signals differ when TEST data differs (the rule is applied, not re-fitted)
    assert not all(np.array_equal(ra["signals"]["REF"][s], rb["signals"]["REF"][s]) for s in E.ALL_SYMS)
    # SOL uses the pooled BTC+ETH cutoffs
    assert ra["info"]["cutoffs"]["REF"]["SOLUSDT"] != ra["info"]["cutoffs"]["REF"]["BTCUSDT"]


def test_fold_grid_expanding_and_partial_last():
    folds = E.fold_grid(pd.Timestamp("2019-11-27 07:45", tz="UTC"), pd.Timestamp("2026-08-17 23:59", tz="UTC"))
    assert folds[0][1] == pd.Timestamp("2021-11-27 07:45", tz="UTC")
    assert all(f[0] == folds[0][0] for f in folds)
    assert all(a[2] == b[1] for a, b in zip(folds, folds[1:]))  # contiguous TEST windows
    assert folds[-1][2] == pd.Timestamp("2026-08-18 00:00", tz="UTC")
    assert all(f[1] < f[2] for f in folds)


def test_times_ns_is_resolution_independent():
    idx = pd.date_range("2024-01-01", periods=3, freq="1min", tz="UTC")
    for unit in ("ns", "us", "ms"):
        got = E.times_ns(idx.as_unit(unit))
        assert pd.DatetimeIndex(got).tz_localize("UTC").equals(idx)
