"""Tests for scripts/agents/exp52_tail.py (Exp 52 CAPPED rule: size, burst, floor).
Synthetic fixtures only (in memory), never real data paths."""
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

import exp52_tail as e  # noqa: E402
from quant_bot.execution_harness import PLATFORMS, ExitRule, run_trades, simulate_account  # noqa: E402
from quant_bot.execution_harness.costs import Sourced  # noqa: E402

T0 = pd.Timestamp("2024-01-01 00:00", tz="UTC")
FIT = {"AAA": {"q995": 0.04, "rv30_median": 0.001}, "BBB": {"q995": 0.04, "rv30_median": 0.001}}


def _trade(sym, minute):
    st = T0 + pd.Timedelta(minutes=minute)
    return SimpleNamespace(symbol=sym, signal_time=st, entry_time=st + pd.Timedelta(minutes=1))


def _sizer(rv, **kw):
    return e.make_capped_sizer(FIT, rv, **kw)


# ---------------- size ----------------

def test_size_is_B_over_q_scaled_by_vol_and_capped_at_33pct():
    rv = {("AAA", T0): 0.002, ("AAA", T0 + pd.Timedelta(minutes=1)): 0.0005}
    s = _sizer(rv)
    # rv twice the median -> q = 0.08 -> 0.02/0.08 = 25 % of equity
    n, tag = s(_trade("AAA", 0), 1000.0, [], 330.0)
    assert n == pytest.approx(250.0) and tag == "tail_cap"
    # rv half the median -> q = 0.02 -> 100 % -> capped at 33 %
    n, tag = s(_trade("AAA", 1), 1000.0, [], 330.0)
    assert n == pytest.approx(330.0) and tag == "full"


def test_size_uses_equity_passed_at_entry():
    s = _sizer({("AAA", T0): 0.002})
    assert s(_trade("AAA", 0), 400.0, [], 132.0)[0] == pytest.approx(100.0)


def test_missing_vol_gives_zero():
    assert _sizer({})(_trade("AAA", 0), 1000.0, [], 330.0) == (0.0, "rv_missing")


# ---------------- burst ----------------

def test_burst_zero_for_other_symbol_within_60_min_only():
    rv = {("BBB", T0 + pd.Timedelta(minutes=m)): 0.001 for m in (30, 60, 61)}
    s = _sizer(rv)
    open_a = [{"symbol": "AAA", "entry_time": T0 + pd.Timedelta(minutes=1), "notional": 100.0}]
    assert s(_trade("BBB", 30), 1000.0, open_a, 330.0) == (0.0, "burst")
    assert s(_trade("BBB", 60), 1000.0, open_a, 330.0) == (0.0, "burst")          # 60 min after entry
    assert s(_trade("BBB", 61), 1000.0, open_a, 330.0)[1] != "burst"              # 61 min
    # same-symbol open position is not a burst (one position per symbol handles it)
    open_b = [{"symbol": "BBB", "entry_time": T0 + pd.Timedelta(minutes=1), "notional": 100.0}]
    assert s(_trade("BBB", 30), 1000.0, open_b, 330.0)[1] != "burst"
    # SOL-only instance: burst disabled
    assert _sizer(rv, burst=False)(_trade("BBB", 30), 1000.0, open_a, 330.0)[1] != "burst"


# ---------------- floor ----------------

def test_floor_20_usd():
    rv = {("AAA", T0): 0.001}               # q = 0.04 -> 0.5 -> capped 33 %
    s = _sizer(rv)
    assert s(_trade("AAA", 0), 60.0, [], 19.8) == (0.0, "floor")                 # 19.8 USD
    assert s(_trade("AAA", 0), 61.0, [], 20.13)[0] == pytest.approx(20.13)


# ---------------- tail estimate ----------------

def _bars(rows, start=T0, index=None):
    idx = index if index is not None else pd.date_range(start, periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_adverse_move_uses_next_open_and_hold_window_and_gaps():
    rows = [(100, 100, 100, 100), (100, 100, 97, 99), (99, 99, 95, 98), (98, 98, 90, 98), (98, 98, 98, 98)]
    m = e.adverse_move(_bars(rows), hold=2)
    assert m.iloc[0] == pytest.approx(0.05)     # entry open[1]=100, min low[1..2]=95
    assert m.iloc[1] == pytest.approx(1 - 90 / 99)
    assert np.isnan(m.iloc[3]) and np.isnan(m.iloc[4])   # window runs past the data
    idx = pd.DatetimeIndex([T0 + pd.Timedelta(minutes=k) for k in (0, 1, 3, 4, 5)])
    g = e.adverse_move(_bars(rows, index=idx), hold=2)
    assert np.isnan(g.iloc[0]) and np.isnan(g.iloc[1]) and not np.isnan(g.iloc[2])


def test_fit_tail_excludes_windows_reaching_the_end():
    idx = pd.date_range(T0, periods=200, freq="1min", tz="UTC")
    mae = pd.Series(0.01, index=idx)
    mae.iloc[150:] = 0.5                        # after the cut-off: must not leak
    vol = pd.Series(0.001, index=idx)
    f = e.fit_tail(mae, vol, None, idx[100], hold=50)
    assert f["q995"] == pytest.approx(0.01) and f["n_mae"] == 50


# ---------------- integration with the account replay ----------------

def test_account_replay_burst_and_size_at_current_capital():
    rows = [(100, 100, 100, 100), (100, 100, 100, 100), (100, 110, 100, 110)] + [(110, 110, 110, 110)] * 10
    df = _bars(rows)
    plat = dataclasses.replace(PLATFORMS["research_0p14"], name="t", fee_pct=Sourced(0.0, "t"))
    cand = pd.DataFrame({"symbol": ["AAA", "BBB", "AAA"], "signal_time": [df.index[0], df.index[1], df.index[6]]})
    t = run_trades(cand, ExitRule(max_bars=2), plat, bars_loader=lambda s: df)
    rv = {("AAA", df.index[0]): 0.002, ("BBB", df.index[1]): 0.001, ("AAA", df.index[6]): 0.002}
    a = simulate_account(t, plat, initial_cad=1000, usd_per_cad=1.0, position_fraction=0.33,
                         charge_funding_conversion=False, sizer=_sizer(rv))
    led = a["ledger"]
    assert a["skips"]["burst"] == 1 and list(led.symbol) == ["AAA", "AAA"]
    assert led.notional_usd.iloc[0] == pytest.approx(250.0)         # 25 % of 1000
    assert led.notional_usd.iloc[1] == pytest.approx(0.25 * 1025.0)  # +10 % on 250 realized first
