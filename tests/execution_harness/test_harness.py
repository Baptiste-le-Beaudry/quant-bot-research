"""Unit tests for quant_bot.execution_harness (synthetic in-memory fixtures only)."""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from quant_bot.execution_harness import (PLATFORMS, ExitRule, profit_factor, run_trades,
                                         simulate_account, simulate_trade, summarize)
import warnings

from quant_bot.execution_harness.costs import USD_PER_CAD, PlatformCosts, Sourced


def bars_from(rows, start="2024-01-01 00:00"):
    idx = pd.date_range(start, periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def arrays(df):
    return [df[k].to_numpy(float) for k in ("open", "high", "low", "close")]


FLAT = [(100, 100, 100, 100)]


def test_next_open_entry_and_time_exit_at_close_of_bar_n():
    rows = FLAT + [(101, 101, 101, 101), (102, 102, 102, 102), (103, 103, 103, 104), (105, 105, 105, 105)]
    o, h, l, c = arrays(bars_from(rows))
    r = simulate_trade(o, h, l, c, 0, ExitRule(max_bars=3))
    assert r["entry_price"] == 101 and r["entry_idx"] == 1
    assert r["exit_idx"] == 3 and r["exit_price"] == pytest.approx(104)
    assert r["exit_reason"] == "time" and r["bars_held"] == 3


def test_latency_shifts_entry():
    rows = FLAT + [(101, 101, 101, 101), (102, 102, 102, 102), (103, 103, 103, 103), (104, 104, 104, 104)]
    o, h, l, c = arrays(bars_from(rows))
    r = simulate_trade(o, h, l, c, 0, ExitRule(max_bars=2), latency_bars=1)
    assert r["entry_price"] == 102 and r["exit_idx"] == 3


def test_signal_close_mode_refuses_latency():
    o, h, l, c = arrays(bars_from(FLAT * 5))
    with pytest.raises(ValueError):
        simulate_trade(o, h, l, c, 0, ExitRule(max_bars=2), entry_mode="signal_close", latency_bars=1)


def test_intrabar_touch_fills_at_stop_level_even_if_close_recovers():
    rows = FLAT + [(100, 100, 100, 100), (100, 100.5, 97.9, 100.4), (101, 101, 101, 101)]
    o, h, l, c = arrays(bars_from(rows))
    r = simulate_trade(o, h, l, c, 0, ExitRule(max_bars=3, stop_distance=0.02))
    assert r["exit_reason"] == "stop" and r["exit_idx"] == 2
    assert r["gross_ret"] == pytest.approx(-0.02)


def test_gap_through_stop_fills_at_open_not_at_stop():
    rows = FLAT + [(100, 100, 100, 100), (95, 96, 94, 95.5), (95, 95, 95, 95)]
    o, h, l, c = arrays(bars_from(rows))
    r = simulate_trade(o, h, l, c, 0, ExitRule(max_bars=3, stop_distance=0.02))
    assert r["exit_price"] == pytest.approx(95) and r["gross_ret"] == pytest.approx(-0.05)


def test_trailing_level_uses_peak_up_to_previous_bar():
    rule = ExitRule(max_bars=5, stop_distance=0.05, trail_activation=0.01, trail_distance=0.01)
    # bar1: entry 100, high 102 -> peak 2 %, active. bar2: high 105 and low 101.5:
    # level for bar2 = 2 % - 1 % = 1 % -> 101 not touched (101.5). If the bar's own
    # high were folded first, level would be 4 % -> 104 and the trade would exit (wrong).
    rows = FLAT + [(100, 102, 100, 101.5), (102, 105, 101.5, 104), (104, 104.2, 103.5, 104), (104, 104, 104, 104),
                   (104, 104, 104, 104)]
    o, h, l, c = arrays(bars_from(rows))
    r = simulate_trade(o, h, l, c, 0, rule)
    assert r["exit_idx"] == 3 and r["exit_reason"] == "trail"
    assert r["gross_ret"] == pytest.approx(0.04)  # level = peak 5 % - 1 %, bar3 low 103.5 <= 104


def test_short_side_symmetric_gap():
    rows = FLAT + [(100, 100, 100, 100), (106, 107, 105, 106), (106, 106, 106, 106)]
    o, h, l, c = arrays(bars_from(rows))
    r = simulate_trade(o, h, l, c, 0, ExitRule(max_bars=3, stop_distance=0.02), side=-1)
    assert r["exit_price"] == pytest.approx(106) and r["gross_ret"] == pytest.approx(-0.06)


def test_end_of_data():
    o, h, l, c = arrays(bars_from(FLAT * 3))
    r = simulate_trade(o, h, l, c, 0, ExitRule(max_bars=10))
    assert r["exit_reason"] == "end_of_data" and r["exit_idx"] == 2
    assert simulate_trade(o, h, l, c, 2, ExitRule(max_bars=10)) is None


def _reference_sim(o, h, l, c, e, stop_d, ACT=0.0063, TRAIL=0.0080, MAXBARS=50):
    """Verbatim copy of scripts/strategy_a/exit_realism_check.py sim(mode='intrabar')."""
    entry = c[e]
    stop = -stop_d
    peak, active = -np.inf, False
    for k in range(1, MAXBARS + 1):
        if e + k >= len(c):
            break
        hi, lo = h[e + k] / entry - 1, l[e + k] / entry - 1
        level = max(stop, peak - TRAIL) if active else stop
        if lo <= level:
            return min(level, o[e + k] / entry - 1)
        peak = max(peak, hi)
        active = active or peak >= ACT
    return c[min(e + MAXBARS, len(c) - 1)] / entry - 1


def test_signal_close_mode_equals_reference_intrabar_on_random_walks():
    rng = np.random.default_rng(7)
    n = 4000
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    o = np.r_[100, c[:-1]] * np.exp(rng.normal(0, 0.001, n))  # gaps between close and next open
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.002, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.002, n)))
    rule = ExitRule(max_bars=50, trail_activation=0.0063, trail_distance=0.0080, use_candidate_stop=True)
    for e in range(0, n, 37):
        sd = float(rng.uniform(0.005, 0.04))
        got = simulate_trade(o, h, l, c, e, rule, stop_distance=sd, entry_mode="signal_close")
        if got is None:
            continue
        assert got["gross_ret"] == pytest.approx(_reference_sim(o, h, l, c, e, sd), abs=1e-12)


def _mini_platform(**kw):
    base = PLATFORMS["research_0p14"]
    return dataclasses.replace(base, name="test", **kw)


def test_costs_and_unsupported_symbol_counted():
    df = bars_from(FLAT + [(100, 100, 100, 100), (102, 102, 102, 102)])
    cand = pd.DataFrame({"symbol": ["AAA", "BBB"], "signal_time": [df.index[0]] * 2})
    plat = _mini_platform(symbols=frozenset({"AAA"}),
                          fixed_fee_usd_per_order=Sourced(0.5, "test"))
    t = run_trades(cand, ExitRule(max_bars=2), plat, bars_loader=lambda s: df, notional_usd=100.0)
    ok = t[t.status == "ok"].iloc[0]
    assert ok.gross_ret == pytest.approx(0.02)
    assert ok.net_ret == pytest.approx(0.02 - 0.0014)
    assert ok.net_ret_at_size == pytest.approx(0.02 - 0.0014 - 2 * 0.5 / 100)
    assert (t.status == "unsupported_symbol").sum() == 1
    assert summarize(t)["n_trades"] == 1


def test_every_platform_value_has_a_source():
    for p in PLATFORMS.values():
        for row in p.describe():
            assert row["source"], (p.name, row["param"])


def test_account_marks_on_lows_and_charges_fixed_fees():
    rows = FLAT + [(100, 100, 90, 100), (100, 100, 100, 100), (100, 110, 100, 110),
                   (110, 110, 110, 110)]
    df = bars_from(rows)
    cand = pd.DataFrame({"symbol": ["AAA"], "signal_time": [df.index[0]]})
    plat = _mini_platform(fee_pct=Sourced(0.0, "t"), fixed_fee_usd_per_order=Sourced(1.0, "t"))
    t = run_trades(cand, ExitRule(max_bars=3), plat, bars_loader=lambda s: df)
    a = simulate_account(t, plat, initial_cad=1000, usd_per_cad=1.0, position_fraction=0.5,
                         charge_funding_conversion=False)
    # notional 500, -10 % at the low of bar 1 -> -50 - 1 (entry fee) on 1000
    assert a["max_dd_pct"] == pytest.approx(-5.1)
    assert a["final_usd"] == pytest.approx(1000 + 500 * 0.10 - 2.0)


def test_account_min_order_and_symbol_busy_skips():
    df = bars_from(FLAT * 10)
    cand = pd.DataFrame({"symbol": ["AAA", "AAA"], "signal_time": [df.index[0], df.index[1]]})
    plat = _mini_platform(min_order_usd=Sourced(10.0, "t"))
    t = run_trades(cand, ExitRule(max_bars=5), plat, bars_loader=lambda s: df)
    a = simulate_account(t, plat, initial_cad=100, usd_per_cad=1.0, position_fraction=0.5,
                         charge_funding_conversion=False)
    assert a["n_trades"] == 1 and a["skips"]["symbol_busy"] == 1
    a = simulate_account(t, plat, initial_cad=10, usd_per_cad=1.0, position_fraction=0.5,
                         charge_funding_conversion=False)
    assert a["n_trades"] == 0 and a["skips"]["below_min_order"] == 2


def test_profit_factor():
    assert profit_factor(pd.Series([0.02, -0.01])) == pytest.approx(2.0)


# ---------------- v1.1 regression tests (review T-015) ----------------

def test_C1_rule_without_stop_never_applies_candidate_stop():
    # price dips 5 % then recovers: a 2 % candidate stop would exit; a no-stop rule must not.
    rows = FLAT + [(100, 100, 95, 96), (96, 101, 96, 101), (101, 101, 101, 101)]
    df = bars_from(rows)
    cand = pd.DataFrame({"symbol": ["AAA"], "signal_time": [df.index[0]], "stop_distance": [0.02]})
    t = run_trades(cand, ExitRule(max_bars=3), "research_0p14", bars_loader=lambda s: df)
    assert t.exit_reason.iloc[0] == "time" and t.gross_ret.iloc[0] == pytest.approx(0.01)
    t2 = run_trades(cand, ExitRule(max_bars=3, use_candidate_stop=True), "research_0p14", bars_loader=lambda s: df)
    assert t2.exit_reason.iloc[0] == "stop" and t2.gross_ret.iloc[0] == pytest.approx(-0.02)
    o, h, l, c = arrays(df)
    r = simulate_trade(o, h, l, c, 0, ExitRule(max_bars=3), stop_distance=0.02)
    assert r["exit_reason"] == "time"


def test_C5_data_defects_are_excluded_from_ok():
    nan_rows = FLAT + [(100, 100, np.nan, 100), (100, 100, 100, 100), (100, 100, 100, 100)]
    df = bars_from(nan_rows)
    cand = pd.DataFrame({"symbol": ["AAA"], "signal_time": [df.index[0]]})
    t = run_trades(cand, ExitRule(max_bars=2), "research_0p14", bars_loader=lambda s: df)
    assert t.status.iloc[0] == "nan_in_window"
    gap = bars_from(FLAT * 4)
    gap.index = gap.index[:2].append(gap.index[2:] + pd.Timedelta(hours=5))
    t = run_trades(cand.assign(signal_time=gap.index[0]), ExitRule(max_bars=2), "research_0p14",
                   bars_loader=lambda s: gap)
    assert t.status.iloc[0] == "gap_in_window"
    short = bars_from(FLAT * 3)
    t = run_trades(cand.assign(signal_time=short.index[0]), ExitRule(max_bars=10), "research_0p14",
                   bars_loader=lambda s: short)
    assert t.status.iloc[0] == "end_of_data"
    s = summarize(t)
    assert s["n_trades"] == 0 and np.isnan(s["mean_net_ret_pct"])


def test_C7_signal_close_warns():
    df = bars_from(FLAT * 5)
    cand = pd.DataFrame({"symbol": ["AAA"], "signal_time": [df.index[0]]})
    with pytest.warns(UserWarning, match="NOT executable"):
        run_trades(cand, ExitRule(max_bars=2), "research_0p14", bars_loader=lambda s: df, entry_mode="signal_close")


def test_C3_jupiter_sol_quote_not_double_counted():
    sol = PLATFORMS["jupiter_sol"]
    assert sol.round_trip_pct("SOLUSDT") == pytest.approx(0.00041)
    assert PLATFORMS["jupiter_build"].round_trip_pct("SOLUSDT") == pytest.approx(0.0002)
    assert PLATFORMS["jupiter_build"].fixed_fee_usd_per_order.value == pytest.approx(0.01)
    assert PLATFORMS["jupiter_order_btceth"].round_trip_pct("BTCUSDT") == pytest.approx(0.0020)
    assert not PLATFORMS["jupiter_order_btceth"].supports("SOLUSDT")


def test_C4_propr_two_fee_variants_unverified():
    assert PLATFORMS["propr_0p045"].fee_pct.value == pytest.approx(0.00045)
    assert PLATFORMS["propr_0p075"].fee_pct.value == pytest.approx(0.00075)
    assert not PLATFORMS["propr_0p045"].fee_pct.verified and not PLATFORMS["propr_0p075"].fee_pct.verified


def test_C2_cad_ramp_fixed_withdrawal_and_rate():
    assert USD_PER_CAD.value == pytest.approx(1 / 1.42075, abs=1e-6)
    rows = FLAT + [(100, 100, 100, 100), (100, 100, 100, 100)]
    df = bars_from(rows)
    cand = pd.DataFrame({"symbol": ["SOLUSDT"], "signal_time": [df.index[0]]})
    plat = dataclasses.replace(PLATFORMS["jupiter_build"], half_spread_pct=Sourced(0.0, "t"),
                               fixed_fee_usd_per_order=Sourced(0.0, "t"))
    t = run_trades(cand, ExitRule(max_bars=2), plat, bars_loader=lambda s: df)
    a = simulate_account(t, plat, initial_cad=500, position_fraction=0.33)
    assert a["final_cad_after_withdrawal"] == pytest.approx(500 * 0.995 * 0.995 - 10)


# ---------------- v1.2 sizer hook ----------------

def _two_symbol_trades(plat):
    df = bars_from(FLAT + [(100, 100, 100, 100), (100, 110, 100, 110)] + [(110, 110, 110, 110)] * 10)
    cand = pd.DataFrame({"symbol": ["AAA", "BBB", "AAA"],
                         "signal_time": [df.index[0], df.index[1], df.index[6]]})
    return run_trades(cand, ExitRule(max_bars=2), plat, bars_loader=lambda s: df)


def test_v12_sizer_none_and_identity_sizer_match_v11():
    plat = _mini_platform(fee_pct=Sourced(0.0, "t"))
    t = _two_symbol_trades(plat)
    kw = dict(initial_cad=1000, usd_per_cad=1.0, position_fraction=0.3, charge_funding_conversion=False)
    a = simulate_account(t, plat, **kw)
    b = simulate_account(t, plat, sizer=lambda tr, eq, op, base: (base, "same"), **kw)
    assert a["final_usd"] == pytest.approx(b["final_usd"]) and a["n_trades"] == b["n_trades"] == 3
    assert (a["ledger"].size_tag == "fraction").all() and (b["ledger"].size_tag == "same").all()


def test_v12_sizer_sees_realized_equity_and_open_positions_and_can_skip():
    plat = _mini_platform(fee_pct=Sourced(0.0, "t"))
    t = _two_symbol_trades(plat)
    seen = []

    def sizer(tr, eq, op, base):
        seen.append((tr.symbol, eq, [p["symbol"] for p in op], base))
        return (0.0, "custom_zero") if tr.symbol == "BBB" else (0.5 * eq, "half")

    a = simulate_account(t, plat, initial_cad=1000, usd_per_cad=1.0, position_fraction=0.3,
                         charge_funding_conversion=False, sizer=sizer)
    assert a["skips"]["custom_zero"] == 1 and a["n_trades"] == 2
    assert seen[1][0] == "BBB" and seen[1][2] == ["AAA"]   # AAA still open when BBB enters
    assert seen[1][1] == pytest.approx(1000.0) and seen[1][3] == pytest.approx(300.0)
    # first AAA: 500 notional, +10 % -> realized equity 1050 at the third entry
    assert seen[2][1] == pytest.approx(1050.0) and a["ledger"].notional_usd.iloc[1] == pytest.approx(525.0)


def test_v13_equity_platforms_round_trip_at_160_usd():
    """v1.3: IBKR per-order minimums expressed as fixed USD fees (exact at 160 USD notional)."""
    from quant_bot.execution_harness import apply_costs, get_platform
    t = pd.DataFrame({"symbol": ["ADBE"], "status": ["ok"], "gross_ret": [0.0]})
    tiered = apply_costs(t, get_platform("ibkr_ca_tiered"), notional_usd=160.0)
    fixed = apply_costs(t, get_platform("ibkr_ca_fixed"), notional_usd=160.0)
    prop_t = 2 * (0.0000103 + 0.0001 + 0.00002)
    assert tiered.net_ret_at_size.iloc[0] == pytest.approx(-(prop_t + 2 * 0.35 / 160))
    assert fixed.net_ret_at_size.iloc[0] == pytest.approx(-(2 * (0.0000103 + 0.0001) + 2 * 1.00 / 160))


def test_v13_with_per_share_fee():
    from quant_bot.execution_harness import get_platform, with_per_share_fee
    p = with_per_share_fee(get_platform("cfd_darwinex_assumed"), 0.04, {"MA": 400.0}, "test")
    assert p.side_cost_pct("MA") == pytest.approx(0.04 / 400 + 0.0001)
    assert p.side_cost_pct("XYZ") == pytest.approx(0.0001)
