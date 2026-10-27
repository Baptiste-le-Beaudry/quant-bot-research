"""Regression tests for Exp 73 (MNQ random-entry nulls). Synthetic fixtures only, in tmp_path."""
import datetime as dt
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp73", ROOT / "scripts" / "agents" / "exp73_mnq_random_null.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
e64 = m.e64

COLS = ["date", "side", "decision", "entry_bar", "entry_px", "exit_bar", "exit_px", "exit_reason",
        "gross_usd", "cost_usd", "net_usd", "index", "future"]


def trades_df(rows):
    t = pd.DataFrame(rows, columns=["date", "side", "entry_bar", "entry_px", "exit_bar", "exit_px"])
    t["date"] = [d if isinstance(d, dt.date) else dt.date.fromisoformat(d) for d in t["date"]]
    t["net_usd"] = t["side"] * (t["exit_px"] - t["entry_px"]) * 2 - 2.22
    return t


def test_entry_bars_convention():
    assert m.ENTRY_BARS[0] == 30 and m.ENTRY_BARS[-1] == 360 and len(m.ENTRY_BARS) == 12
    assert m.EXIT_IDX == 389


def test_exec_tables_match_exp64_exec_price():
    rng = np.random.default_rng(0)
    o = rng.normal(100, 1, size=(6, e64.N_MIN))
    o[rng.random(o.shape) < 0.3] = np.nan
    o[2, 300:389] = np.nan            # no bar until the exit bar -> falls to 389
    o[:, 389] = 100.0 + np.arange(6)
    px, idx = m.exec_tables(o)
    for i in range(6):
        for b in list(m.ENTRY_BARS) + [31, 200, 388]:
            j, p = e64._exec_price(o[i], b)
            assert idx[i, b] == j and px[i, b] == p
        assert idx[i, 389] == 389 and px[i, 389] == o[i, 389]
    assert idx[2, 330] == 389


def test_recompute_net_and_reprice_check():
    o = np.full((1, e64.N_MIN), np.nan)
    o[0, 30], o[0, 389] = 100.0, 110.0
    t = trades_df([("2024-03-05", -1, 30, 100.0, 389, 110.0)])
    assert m.recompute_net(t)[0] == pytest.approx(-20 - 2.22)
    ok = m.reprice_check(t, o, np.array([0]))
    assert ok["n_mismatch"] == 0
    t.loc[0, "exit_px"] = 111.0
    assert m.reprice_check(t, o, np.array([0]))["n_mismatch"] == 1


def test_null_a_degenerate_and_pvalue():
    moves = np.array([10.0, -5.0, 3.0])
    masks = {"all": np.ones(3, bool), "drop0": np.array([False, True, True])}
    s = m.null_a(moves, 1.0, masks, n_draws=50, seed=1)
    assert np.allclose(s["all"], (moves * 2 - 2.22).sum())
    assert np.allclose(s["drop0"], (moves[1:] * 2 - 2.22).sum())
    # perfectly informed direction on many trades -> tiny p under q = 0.5
    mv = np.full(200, 5.0)
    real = (mv * 2 - 2.22).sum()
    s = m.null_a(mv, 0.5, {"all": np.ones(200, bool)}, n_draws=2000, seed=2)
    assert m.p_value(s["all"], real) == pytest.approx(1 / 2001)
    # chunking does not change the stream
    a = m.null_a(mv, 0.5, {"all": np.ones(200, bool)}, n_draws=1200, seed=3)["all"]
    old = m.CHUNK
    try:
        m.CHUNK = 7
        b = m.null_a(mv, 0.5, {"all": np.ones(200, bool)}, n_draws=1200, seed=3)["all"]
    finally:
        m.CHUNK = old
    assert np.allclose(a, b)                # null A only draws uniforms: chunk-size invariant


def test_p_value_formula():
    sims = np.array([1.0, 2.0, 3.0, 4.0])
    assert m.p_value(sims, 3.0) == pytest.approx(3 / 5)
    assert m.p_value(sims, 10.0) == pytest.approx(1 / 5)


def test_null_b_deterministic_and_cap():
    o = np.tile(np.arange(e64.N_MIN, dtype=float), (2, 1))   # price = bar index
    px, idx = m.exec_tables(o)
    masks = {"all": np.ones(3, bool)}
    rows = np.array([0, 0, 1])
    # single entry bar 30, duration 30, q=1 -> each trade earns 30 pts
    s = m.null_b(rows, np.array([30]), 1.0, px, idx, masks, n_draws=20, seed=0, entry_bars=np.array([30]))
    assert np.allclose(s["all"], 3 * (30 * 2 - 2.22))
    # entry 360 + duration 100 -> capped at 389
    s = m.null_b(rows, np.array([100]), 0.0, px, idx, masks, n_draws=5, seed=0, entry_bars=np.array([360]))
    assert np.allclose(s["all"], 3 * (-29 * 2 - 2.22))


def test_null_b_uses_rule_bars_and_fallback():
    o = np.tile(np.arange(e64.N_MIN, dtype=float), (1, 1))
    o[0, 60:65] = np.nan                                  # order at 60 fills at 65
    px, idx = m.exec_tables(o)
    s = m.null_b(np.array([0]), np.array([10]), 1.0, px, idx, {"all": np.ones(1, bool)},
                 n_draws=5, seed=0, entry_bars=np.array([60]))
    assert np.allclose(s["all"], 10 * 2 - 2.22)            # 65 -> 75


def test_exclusion_masks():
    t = trades_df([("2025-04-09", 1, 30, 100, 389, 200), ("2025-04-10", 1, 30, 100, 389, 101),
                   ("2025-04-10", -1, 60, 100, 389, 99), ("2025-04-11", 1, 30, 100, 389, 90)])
    masks, info = m.exclusion_masks(t, m.recompute_net(t))
    assert info["best_day"] == ["2025-04-09"] and info["prereg_best_day_2025_04_09_is_best"]
    assert masks["without_best_day"].tolist() == [False, True, True, True]
    assert masks["without_5_best_days"].sum() == 0


def test_verdict73():
    assert m.verdict73(0.01, 0.04, 0.09)["verdict"] == "SIGNAL"
    assert m.verdict73(0.01, 0.06, 0.09)["verdict"] == "INCERTAIN"
    assert m.verdict73(0.01, 0.04, 0.11)["verdict"] == "INCERTAIN"
    assert m.verdict73(0.21, 0.01, 0.01)["verdict"] == "HASARD"
    assert m.verdict73(0.20, 0.5, 0.5)["verdict"] == "INCERTAIN"


def test_load_trades_filters(tmp_path):
    rows = [["2024-03-04", 1, "10:00", 30, 1, 389, 2, "eod", 2, 2.22, -0.22, "NASDAQ100", "MNQ", "noise_area"],
            ["2024-03-05", 1, "10:00", 30, 1, 389, 2, "eod", 2, 2.22, -0.22, "NASDAQ100", "MNQ", "noise_area"],
            ["2024-03-05", 1, "15:30", 360, 1, 389, 2, "eod", 2, 2.22, -0.22, "NASDAQ100", "MNQ", "gao_last_half_hour"],
            ["2024-03-05", 1, "10:00", 30, 1, 389, 2, "eod", 5, 3.72, 1.28, "SP500", "MES", "noise_area"]]
    p = tmp_path / "tr.csv"
    pd.DataFrame(rows, columns=COLS + ["variant"]).to_csv(p, index=False)
    assert len(m.load_trades(p)) == 2
    assert len(m.load_trades(p, dt.date(2024, 3, 5))) == 1
    assert len(m.load_trades(p, None, dt.date(2024, 3, 4))) == 1


# ------------------------------------------------------------------ end to end on synthetic bars
def sessions(start, n):
    d, out = start, []
    while len(out) < n:
        if e64.is_session(d) and d not in e64.nyse_half_days(d.year):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def test_main_end_to_end(tmp_path):
    days = sessions(dt.date(2024, 11, 20), 8)             # spans H and H-post
    rows = []
    for di, d in enumerate(days):
        base = pd.Timestamp(d.isoformat() + " 09:30", tz=e64.ET)
        for k in range(e64.N_MIN):
            p = 20000.0 + di * 10 + 0.5 * k
            ts = (base + pd.Timedelta(minutes=k)).tz_convert("UTC")
            rows.append((ts.strftime("%Y-%m-%d %H:%M:%S+00:00"), p, p + 1, p - 1, p + 0.5, 100.0))
    bars = tmp_path / "bars.csv"
    pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"]).to_csv(bars, index=False)
    tr = []
    for di, d in enumerate(days):
        side = 1 if di % 3 else -1
        e_px = 20000.0 + di * 10 + 0.5 * 30
        x_px = 20000.0 + di * 10 + 0.5 * 389
        g = side * (x_px - e_px) * 2
        tr.append([str(d), side, "10:00", 30, e_px, 389, x_px, "eod", g, 2.22, g - 2.22, "NASDAQ100", "MNQ"])
    tr65 = tmp_path / "tr65.csv"
    pd.DataFrame(tr, columns=COLS).to_csv(tr65, index=False)
    dec = tmp_path / "decision.md"
    dec.write_text("ok")
    out = tmp_path / "crit.json"
    crit = m.main(["--bars", str(bars), "--holdout-decision", str(dec), "--trades65", str(tr65),
                   "--out", str(out), "--n-draws", "300"])
    h = crit["windows"]["H"]
    assert h["reprice_check"]["n_mismatch"] == 0
    assert h["real_net_recomputed_usd"] == pytest.approx(h["real_net_csv_usd"])
    assert h["n_trades"] == 8 and crit["windows"]["H_post"]["n_trades"] < 8
    assert "P1" not in crit["windows"]
    assert crit["verdict"]["verdict"] in {"SIGNAL", "HASARD", "INCERTAIN"}
    assert json.loads(out.read_text(encoding="utf-8"))["seed"] == m.SEED
