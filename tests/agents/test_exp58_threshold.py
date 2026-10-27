"""Exp 58 regression tests -- synthetic in-memory data only."""
import numpy as np
import pandas as pd

from scripts.agents import exp58_threshold as E


def _arrays(n, seed):
    g = np.random.default_rng(seed)
    return g.uniform(0, 1, n), g.uniform(0, 1, n).astype(np.float32), g.uniform(0, 0.01, n).astype(np.float32)


def test_cutoffs_recomputed_per_threshold_on_train_only():
    tr = {s: _arrays(5000, i) for i, s in enumerate(("BTCUSDT", "ETHUSDT"))}
    te = {s: _arrays(800, 10 + i) for i, s in enumerate(("SOLUSDT", "BTCUSDT", "ETHUSDT"))}
    times = {s: np.arange(800, dtype=np.int64) * 60_000_000_000 for s in te}
    args = ({s: v[0] for s, v in tr.items()}, {s: v[1] for s, v in tr.items()}, {s: v[2] for s, v in tr.items()},
            {s: v[0] for s, v in te.items()}, {s: v[1] for s, v in te.items()}, {s: v[2] for s, v in te.items()}, times)
    out = E.threshold_signals(*args, thresholds=(0.6, 0.8))
    for key, t in (("0.60", 0.6), ("0.80", 0.8)):
        p, rng, vol = tr["BTCUSDT"]
        sel = p > t
        assert out[key]["cutoffs"]["BTCUSDT"] == (float(np.median(rng[sel].astype(np.float64))), float(np.median(vol[sel].astype(np.float64))))
        sel_all = np.concatenate([tr[s][0] for s in tr]) > t
        assert np.isclose(out[key]["cutoffs"]["SOLUSDT"][0], np.median(np.concatenate([tr[s][1] for s in tr])[sel_all]))
    assert out["0.60"]["cutoffs"]["BTCUSDT"] != out["0.80"]["cutoffs"]["BTCUSDT"]
    # TEST data never moves the cutoffs
    te2 = {s: (v[0], v[1] * 0 + 0.5, v[2] * 3) for s, v in te.items()}
    args2 = args[:3] + ({s: v[0] for s, v in te2.items()}, {s: v[1] for s, v in te2.items()},
                        {s: v[2] for s, v in te2.items()}, times)
    out2 = E.threshold_signals(*args2, thresholds=(0.6,))
    assert out2["0.60"]["cutoffs"] == out["0.60"]["cutoffs"]


def test_reading_rule():
    base = {"0.70": 0.10}
    stable = {p: {**base, "0.65": 0.12, "0.75": 0.08} for p in ("P1", "P2")}
    assert E.reading(stable)["reading"] == "STABLE"
    frag = {"P1": {**base, "0.65": 0.12, "0.75": 0.08}, "P2": {**base, "0.65": -0.01, "0.75": 0.10}}
    assert E.reading(frag)["reading"] == "FRAGILE"
    mid = {p: {**base, "0.65": 0.17, "0.75": 0.10} for p in ("P1", "P2")}
    assert E.reading(mid)["reading"] == "INTERMEDIAIRE"
    und = {"P1": {**base, "0.65": 0.12, "0.75": float("nan")}, "P2": {**base, "0.65": 0.12, "0.75": 0.08}}
    assert E.reading(und)["reading"] == "INDETERMINE"
    und_frag = {"P1": {**base, "0.65": -0.12, "0.75": float("nan")}, "P2": {**base, "0.65": 0.12, "0.75": 0.08}}
    assert E.reading(und_frag)["reading"] == "FRAGILE"


def test_fold_of():
    folds = [["a", "2022-01-01 00:00+00:00", "x"], ["a", "2022-04-01 00:00+00:00", "x"]]
    t = pd.Series(pd.to_datetime(["2022-01-01 00:00", "2022-03-31 23:59", "2022-04-01 00:00"], utc=True))
    assert list(E.fold_of(t, folds)) == [1, 1, 2]
