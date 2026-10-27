"""Regression tests for Exp 82 (treasury DRIP discount).  Synthetic fixtures only (tmp_path, never a real data path)."""
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp82", ROOT / "scripts" / "agents" / "exp82_drip_discount.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

EV_COLS = ["event_id", "country", "issuer", "ticker", "group", "decl_date", "pay_date", "record_date", "window_a_def",
           "window_a_start", "window_a_end", "source_achat", "rabais_pct", "statut_doc", "souscripteur",
           "url_source", "url_regime", "notes"]


def _ev_row(i, country, ticker, group, pay, rabais, statut="explicite", source="tresor", wa0="", wa1=""):
    return {"event_id": f"E{i:03d}", "country": country, "issuer": ticker, "ticker": ticker, "group": group,
            "decl_date": "", "pay_date": pay, "record_date": "", "window_a_def": "P-5..P-1", "window_a_start": wa0,
            "window_a_end": wa1, "source_achat": source, "rabais_pct": rabais, "statut_doc": statut,
            "souscripteur": "", "url_source": "https://example.invalid", "url_regime": "", "notes": ""}


def _write_events(tmp_path, rows):
    p = tmp_path / "events.csv"
    pd.DataFrame(rows, columns=EV_COLS).to_csv(p, index=False)
    return p


# ------------------------------------------------------------------ calendar
def test_roll_forward_weekend_and_holiday():
    cal = pd.bdate_range("2024-01-01", "2024-02-29").drop(pd.Timestamp("2024-02-19"))  # Family Day closed
    assert cal[m.roll_forward(pd.Timestamp("2024-01-31"), cal)] == pd.Timestamp("2024-01-31")
    # Saturday -> Monday
    assert cal[m.roll_forward(pd.Timestamp("2024-02-03"), cal)] == pd.Timestamp("2024-02-05")
    # holiday Monday -> Tuesday
    assert cal[m.roll_forward(pd.Timestamp("2024-02-19"), cal)] == pd.Timestamp("2024-02-20")
    assert m.roll_forward(pd.Timestamp("2025-01-01"), cal) is None


def test_window_idx_bounds():
    assert m.window_idx(10, -5, -1, 100) == [5, 6, 7, 8, 9]
    assert m.window_idx(10, 0, 4, 100) == [10, 11, 12, 13, 14]
    assert m.window_idx(3, -5, -1, 100) is None
    assert m.window_idx(97, 0, 4, 100) is None


# ------------------------------------------------------------------ events table
def test_load_events_usable_flags(tmp_path):
    rows = [_ev_row(1, "CA", "AAA.TO", "banque", "2024-01-31", "2"),
            _ev_row(2, "CA", "AAA.TO", "banque", "2024-04-30", "0"),
            _ev_row(3, "CA", "AAA.TO", "banque", "2024-07-31", "", statut="non_documente")]
    ev = m.load_events(_write_events(tmp_path, rows))
    assert ev["usable"].tolist() == [True, True, False]
    assert ev["D"].tolist()[:2] == [1, 0]


def test_active_discount_table_next_payment_rule(tmp_path):
    cal = pd.bdate_range("2024-01-01", "2024-12-31")
    rows = [_ev_row(1, "CA", "AAA.TO", "banque", "2024-03-15", "2"),
            _ev_row(2, "CA", "AAA.TO", "banque", "2024-06-14", "0"),
            _ev_row(3, "CA", "AAA.TO", "banque", "2024-09-16", "", statut="non_documente")]
    ev = m.load_events(_write_events(tmp_path, rows))
    act = m.active_discount_table(ev, ["AAA.TO", "BBB.TO"], cal)
    assert act.loc["2024-03-15", "AAA.TO"] == 1.0      # payment day itself: discount active
    assert act.loc["2024-01-02", "AAA.TO"] == 1.0      # next payment is the discount one
    assert act.loc["2024-03-18", "AAA.TO"] == 0.0      # next payment is the no-discount one
    assert np.isnan(act.loc["2024-07-01", "AAA.TO"])   # next payment undocumented -> unknown
    assert np.isnan(act.loc["2024-11-01", "AAA.TO"])   # after the last event -> unknown
    assert act["BBB.TO"].isna().all()                  # no events -> unknown


def test_bank_benchmark_excludes_active_and_unknown_falls_back_to_index():
    cal = pd.bdate_range("2024-01-01", periods=4)
    rets = pd.DataFrame({"A": [0.01, 0.01, 0.01, 0.01], "B": [0.02, 0.02, 0.02, 0.02], "C": [0.04, 0.04, 0.04, 0.04]},
                        index=cal)
    active = pd.DataFrame({"A": [0, 0, 0, 0], "B": [0, 1, np.nan, 1], "C": [0, 0, np.nan, 1]}, index=cal, dtype=float)
    idx = pd.Series([0.005] * 4, index=cal)
    b = m.bank_benchmark(rets, active, idx, own="A")
    assert b.iloc[0] == pytest.approx(0.03)   # mean(B, C)
    assert b.iloc[1] == pytest.approx(0.04)   # B active -> only C
    assert b.iloc[2] == pytest.approx(0.005)  # both unknown -> index
    assert b.iloc[3] == pytest.approx(0.005)  # both active -> index


# ------------------------------------------------------------------ statistics
def test_cluster_did_matches_mean_difference_and_ols():
    rng = np.random.default_rng(0)
    y = np.r_[rng.normal(-0.01, 0.01, 30), rng.normal(0.0, 0.01, 60)]
    d = np.r_[np.ones(30), np.zeros(60)]
    g = np.arange(90)   # singleton clusters -> HC1-like
    r = m.cluster_did(y, d, g)
    assert r["did"] == pytest.approx(y[:30].mean() - y[30:].mean())
    # singleton-cluster CR1 equals HC1: G/(G-1) * (n-1)/(n-k) = n/(n-k)
    X = np.column_stack([np.ones(90), d])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    u = y - X @ b
    xtx = np.linalg.inv(X.T @ X)
    V = xtx @ (X.T * u ** 2) @ X @ xtx * 90 / 88
    assert r["se"] == pytest.approx(math.sqrt(V[1, 1]), rel=1e-9)
    assert r["n_discount"] == 30 and r["n_none"] == 60


def test_cluster_did_clusters_widen_se_when_shared_shock():
    d = np.r_[np.ones(20), np.zeros(20)]
    y = np.r_[np.repeat([0.02, -0.02], 10), np.zeros(20)] + np.linspace(0, 1e-4, 40)
    g_single = np.arange(40)
    g_pair = np.r_[np.repeat(np.arange(2), 10), np.arange(2, 22)]
    assert m.cluster_did(y, d, g_pair)["se"] > m.cluster_did(y, d, g_single)["se"]


def test_cluster_did_degenerate_one_state():
    r = m.cluster_did(np.array([0.1, 0.2]), np.array([1, 1]), np.array([0, 1]))
    assert math.isnan(r["did"])


def test_deflated_sharpe_monotone_in_trials():
    rng = np.random.default_rng(1)
    ex = pd.Series(rng.normal(0.0004, 0.01, 2000))
    a = m.deflated_sharpe(ex, 96)
    b = m.deflated_sharpe(ex, 133)
    assert 0 <= b["dsr"] <= a["dsr"] <= 1
    assert a["sr0_ann"] < b["sr0_ann"]


# ------------------------------------------------------------------ verdict
def _blk(did, t):
    return {"did": did, "t": t}


def test_verdict_pass_reject_incertain():
    good = {"A": _blk(-0.004, -3.0), "B": _blk(0.003, 2.0), "VOL": _blk(0.1, 2.5)}
    rob = {k: _blk(-0.001, -1) for k in ("a", "b", "c", "d")}
    au = {"did": -0.001}
    assert m.verdict(50, good, 0.001, rob, au, 5, 0.1)["verdict"] == "PASS"
    # Australia with >= 20 events and wrong sign blocks PASS (but is not a reject trigger)
    assert m.verdict(50, good, 0.001, rob, {"did": 0.002}, 25, 0.1)["verdict"] == "INCERTAIN"
    # ... and with < 20 events it is only reported
    assert m.verdict(50, good, 0.001, rob, {"did": 0.002}, 5, 0.1)["verdict"] == "PASS"
    bad_a = {**good, "A": _blk(0.0, -0.1)}
    assert m.verdict(50, bad_a, 0.001, rob, au, 5, 0.1)["verdict"] == "REJET"
    bad_v = {**good, "VOL": _blk(-0.01, -1)}
    assert m.verdict(50, bad_v, 0.001, rob, au, 5, 0.1)["verdict"] == "REJET"
    weak = {**good, "A": _blk(-0.001, -1.0)}
    assert m.verdict(50, weak, 0.001, rob, au, 5, 0.1)["verdict"] == "INCERTAIN"
    assert m.verdict(39, good, 0.001, rob, au, 5, 0.1)["verdict"] == "INCERTAIN"
    assert m.verdict(50, good, -0.0001, rob, au, 5, 0.1)["verdict"] == "INCERTAIN"
    assert m.verdict(50, good, 0.001, rob, au, 5, -0.01)["verdict"] == "INCERTAIN"


# ------------------------------------------------------------------ synthetic end-to-end
def _synthetic_market(tmp_path, effect=-0.01):
    """Two banks + index; bank AAA drops `effect` spread over window A of discount events then recovers."""
    raw = tmp_path / "raw"
    raw.mkdir()
    cal = pd.bdate_range("2015-01-01", "2020-12-31")
    rng = np.random.default_rng(7)
    base = rng.normal(0.0002, 0.006, len(cal))
    idx = pd.Series(base, index=cal)
    tick = {t: base + rng.normal(0, 0.004, len(cal)) for t in m.CA_BANKS}
    pays = pd.date_range("2015-03-20", "2020-09-30", freq="QS-MAR") + pd.Timedelta(days=19)
    rows = []
    for i, p in enumerate(pays):
        pi = cal.searchsorted(p)
        disc = (i % 2 == 0)
        rows.append(_ev_row(i, "CA", "RY.TO", "banque", str(p.date()), "2" if disc else "0"))
        if disc:
            for k in range(pi - 5, pi):
                tick["RY.TO"][k] += effect / 5
            for k in range(pi, pi + 5):
                tick["RY.TO"][k] -= effect / 5
    vol = pd.Series(1e6, index=cal)

    def save(t, r):
        px = 100 * np.cumprod(1 + r)
        df = pd.DataFrame({"Close": px, "Adj Close": px, "Volume": vol.values}, index=cal).rename_axis("Date")
        df.to_csv(raw / m.ycsv(t))
    save(m.CA_INDEX, idx.values)
    for t in m.CA_BANKS:
        save(t, tick[t])
    rf = pd.DataFrame({"DATE": pd.date_range("2014-01-01", "2021-01-01", freq="MS").strftime("%Y-%m-%d"),
                       m.FRED_RF: 1.0})
    rf.to_csv(raw / f"FRED_{m.FRED_RF}.csv", index=False)
    evp = _write_events(tmp_path, rows)
    return raw, evp


def test_event_measures_recover_injected_effect(tmp_path):
    raw, evp = _synthetic_market(tmp_path, effect=-0.02)
    ev = m.load_events(evp)
    px = m.load_prices(raw, m.tickers_from_events(ev))
    cal = px[m.CA_INDEX].index
    idx_ret = px[m.CA_INDEX]["adj"].pct_change().reindex(cal)
    meas = m.event_measures(ev, px, cal, idx_ret, m.CA_BANKS)
    did = m.did_block(meas)
    assert did["A"]["did"] == pytest.approx(-0.02, abs=0.006)
    assert did["B"]["did"] == pytest.approx(0.02, abs=0.006)
    assert did["A"]["t"] < -2


def test_run_writes_outputs_in_tmp_only(tmp_path):
    raw, evp = _synthetic_market(tmp_path, effect=-0.02)
    out = tmp_path / "out"
    out.mkdir()
    res = m.run(raw, evp, out, "T")
    assert (out / "T_criteria.json").exists() and (out / "T_events_measured.csv").exists()
    j = json.loads((out / "T_criteria.json").read_text())
    assert j["criteria"]["verdict"] in ("PASS", "REJET", "INCERTAIN")
    # 12 discount events < 40 -> INCERTAIN by rule
    assert j["criteria"]["n_discount_events"] < 40 and j["criteria"]["verdict"] == "INCERTAIN"
    assert res["rule_per_event"]["n"] == j["criteria"]["n_discount_events"]


def test_rule_series_cost_and_switch():
    cal = pd.bdate_range("2024-01-01", periods=20)
    rets = pd.DataFrame(0.0, index=cal, columns=m.CA_BANKS)
    rets["RY.TO"] = 0.01
    meas = pd.DataFrame([{"P": cal[5], "ticker": "RY.TO", "D": 1}])
    rule, bk = m.rule_series(meas, rets, cal, m.CA_BANKS, None)
    assert bk.iloc[5] == pytest.approx(0.01 / 6)
    assert rule.iloc[5] == pytest.approx(0.01 - 0.001)        # switched + entry cost
    assert rule.iloc[6] == pytest.approx(0.01)
    assert rule.iloc[9] == pytest.approx(0.01 - 0.001)        # exit cost on P+4
    assert rule.iloc[10] == pytest.approx(0.01 / 6)           # back in basket


def test_underwritten_and_pembina_window(tmp_path):
    rows = [_ev_row(1, "AU", "NAB.AX", "banque", "2024-07-03", "1.5"),
            _ev_row(2, "CA", "PPL.TO", "pipeline", "2024-03-15", "5")]
    rows[0]["souscripteur"] = "oui"
    rows[1]["window_a_def"] = "regle Pembina : ..."
    rows[1]["record_date"] = "2024-02-26"
    ev = m.load_events(_write_events(tmp_path, rows))
    assert ev.set_index("ticker").loc["NAB.AX", "usable"] == False  # noqa: E712
    cal = pd.bdate_range("2024-01-01", "2024-04-30")
    px = {t: pd.DataFrame({"close": 1.0, "adj": np.linspace(10, 11, len(cal)), "vol": 1e5}, index=cal)
          for t in ("PPL.TO", "^GSPTSE")}
    idx = px["^GSPTSE"]["adj"].pct_change()
    meas = m.event_measures(ev, px, cal, idx, m.CA_BANKS)
    # record 2024-02-26 (Mon) + 2 trading days = 2024-02-28 ; P = 2024-03-15 ; end = P-2 = 2024-03-13
    assert meas.iloc[0]["nA"] == len(pd.bdate_range("2024-02-28", "2024-03-13"))
