"""Regression tests for scripts/agents/exp54_commodities.py (Exp 54).
Synthetic fixtures only (in memory / pytest tmp_path), never real data paths."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

import exp54_commodities as e  # noqa: E402
from quant_bot.features.build import build_feature_matrix  # noqa: E402


def _bars(n, start="2025-09-01", freq="1min", seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 1e-3, n)))
    op = np.r_[close[0], close[:-1]]
    df = pd.DataFrame({"open": op, "high": np.maximum(op, close) * 1.0005,
                       "low": np.minimum(op, close) * 0.9995, "close": close,
                       "volume": rng.integers(1, 100, n).astype(float)}, index=idx)
    return df


def _write_raw(root, name, df, spread=0.01):
    for side, add in (("BID", 0.0), ("ASK", spread)):
        d = root / f"{name}_{side}"
        d.mkdir(parents=True, exist_ok=True)
        x = df.copy()
        x[["open", "high", "low", "close"]] += add
        for m, g in x.groupby(x.index.strftime("%Y-%m")):
            g.to_pickle(d / f"{m}.pkl")


def test_load_drops_holdout_and_never_opens_holdout_months(tmp_path):
    df = _bars(60 * 24 * 45, start="2025-08-20")  # runs into October 2025
    _write_raw(tmp_path, "XAUUSD", df)
    # a corrupt HOLDOUT month file must not even be opened
    (tmp_path / "XAUUSD_BID" / "2025-10.pkl").write_bytes(b"not a pickle")
    (tmp_path / "XAUUSD_ASK" / "2025-10.pkl").write_bytes(b"not a pickle")
    out = e.load_instrument("XAUUSD", raw_root=tmp_path)
    assert out.index.max() < e.HOLDOUT_START
    assert {"ask_open", "ask_close", "taker_buy_volume"} <= set(out.columns)
    assert np.allclose(out["ask_close"] - out["close"], 0.01)


def test_load_filters_holdout_rows_inside_a_pre_holdout_named_file(tmp_path):
    df = _bars(200, start="2025-09-30 23:00")  # spills past midnight into 2025-10-01
    for side in ("BID", "ASK"):
        d = tmp_path / f"GAS_{side}"
        d.mkdir(parents=True)
        df.to_pickle(d / "2025-09.pkl")
    out = e.load_instrument("GAS", raw_root=tmp_path)
    assert out.index.max() < e.HOLDOUT_START
    assert len(out) == 60


def test_folds_min_train_quarter_aligned_and_before_holdout():
    first = pd.Timestamp("2012-03-02 00:00", tz="UTC")
    folds = e.build_folds(first)
    assert folds[0][1] == pd.Timestamp("2015-04-01", tz="UTC")
    for t0, tr_end, te_end in folds:
        assert t0 == first
        assert tr_end >= first + pd.DateOffset(months=36)
        assert te_end == tr_end + pd.DateOffset(months=3)
        assert te_end <= e.HOLDOUT_START
    assert folds[-1][2] == e.HOLDOUT_START
    # contiguous, non-overlapping TEST windows
    for (_, a, b), (_, c, _) in zip(folds, folds[1:]):
        assert b == c


def test_folds_strict_three_years():
    folds = e.build_folds(pd.Timestamp("2012-01-01 22:00", tz="UTC"))
    assert folds[0][1] == pd.Timestamp("2015-04-01", tz="UTC")


def test_session_ids_split_on_gaps_over_30min():
    idx = pd.DatetimeIndex(pd.to_datetime(
        ["2020-01-01 00:00", "2020-01-01 00:01", "2020-01-01 00:21",  # 20-min gap: same session
         "2020-01-01 00:52", "2020-01-01 01:53"], utc=True))        # 31 and 61-min gaps: new sessions
    assert list(e.session_ids(idx)) == [0, 0, 0, 1, 2]


def test_simulate_ask_entry_next_open_bid_exit_50_bars():
    n = 200
    ask_open = np.arange(n, dtype=float) + 1000.0
    bid_close = np.arange(n, dtype=float) + 900.0
    hi = bid_close + 1
    lo = bid_close - 1
    sess = np.zeros(n, dtype=int)
    mask = np.zeros(n, bool)
    mask[[10, 30, 60, 61, 120]] = True
    tr = e.simulate(ask_open, bid_close, hi, lo, sess, mask, 0, n)
    # 10 -> exit 60; 30 skipped (in position); 60 allowed (exit bar close); 61 skipped; 120 -> exit 170
    assert [t["signal_idx"] for t in tr] == [10, 60, 120]
    t = tr[0]
    assert t["entry_idx"] == 11 and t["exit_idx"] == 60
    assert t["entry_ask"] == ask_open[11] and t["exit_bid"] == bid_close[60]
    assert t["ret_spread"] == pytest.approx(bid_close[60] / ask_open[11] - 1)
    assert t["mfe"] == pytest.approx(hi[11:61].max() / ask_open[11] - 1)
    assert t["mae"] == pytest.approx(lo[11:61].min() / ask_open[11] - 1)


def test_simulate_blocks_session_crossing_and_fold_end():
    n = 120
    a = np.full(n, 10.0)
    sess = np.zeros(n, dtype=int)
    sess[70:] = 1
    mask = np.zeros(n, bool)
    mask[[5, 25, 69]] = True
    tr = e.simulate(a, a, a, a, sess, mask, 0, n)
    assert [t["signal_idx"] for t in tr] == [5]  # 25 -> exit 75 crosses session; 69 -> exit 119 crosses
    mask[:] = False
    mask[[60]] = True
    assert e.simulate(a, a, a, a, sess, mask, 0, n) == []  # 60 -> exit 110 crosses session at 70
    mask[:] = False
    mask[[70]] = True
    assert e.simulate(a, a, a, a, sess, mask, 0, n) == []  # exit bar 120 is beyond the fold end (hi=120)
    a2 = np.full(121, 10.0)
    s2 = np.r_[sess, 1]
    m2 = np.r_[mask, False]
    assert e.simulate(a2, a2, a2, a2, s2, m2, 0, 121)[0]["exit_idx"] == 120


def test_commission_scenarios_are_two_per_side():
    assert e.COMMISSIONS == {"c0": 0.0, "c0005": 0.00005}


def test_profit_factor_edge_cases():
    assert np.isnan(e.profit_factor([]))
    assert e.profit_factor([0.01, 0.02]) == float("inf")
    assert e.profit_factor([0.03, -0.01]) == pytest.approx(3.0)


def test_features_causal_prefix_identical():
    """Justifies computing features once per instrument: on a prefix that
    starts at the same first bar, every feature value equals the value on
    the longer series (TRAIN slices are bit-identical)."""
    df = _bars(3000, seed=3)
    df["taker_buy_volume"] = df["volume"] / 2
    df["taker_sell_volume"] = df["volume"] / 2
    full = build_feature_matrix(df)
    pre = build_feature_matrix(df.iloc[:2000])
    pd.testing.assert_frame_equal(full.iloc[:2000], pre, check_exact=False, rtol=1e-12, atol=1e-15)
