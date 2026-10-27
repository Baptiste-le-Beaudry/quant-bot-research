"""Tests for the Exp 65 criteria wrapper (synthetic inputs only)."""
import datetime as dt
import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp65", ROOT / "scripts" / "agents" / "exp65_mnq_holdout.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def st(s, traded=250, worst=-500.0, mdd=-1500.0):
    return {"sharpe_net": s, "days_traded": traded, "worst_day_usd": worst, "maxdd_usd": mdd}


def test_verdict65():
    assert m.verdict65(st(0.8), st(0.6))["verdict"] == "PASS"
    assert m.verdict65(st(0.3), st(0.9))["verdict"] == "REJET"
    assert m.verdict65(st(0.9), st(0.0))["verdict"] == "REJET"
    assert m.verdict65(st(0.6), st(0.6))["verdict"] == "INCERTAIN"
    assert m.verdict65(st(0.8), st(0.6, traded=200))["verdict"] == "INCERTAIN"
    assert m.verdict65(st(0.8, worst=-1000.0), st(0.6))["verdict"] == "INCERTAIN"
    assert m.verdict65(st(0.8, mdd=-2000.0), st(0.6))["verdict"] == "INCERTAIN"


def test_windows():
    days = pd.DataFrame({"date": [dt.date(2024, 3, 4), dt.date(2024, 3, 5), dt.date(2024, 11, 27)],
                         "n_trades": [1, 1, 0], "gross_usd": [5.0, 3.0, 0.0], "cost_usd": [2.22, 2.22, 0.0]})
    days["net_usd"] = days["gross_usd"] - days["cost_usd"]
    days["net_pct"] = 0.0
    assert m.window_stats(days, m.H_START["NASDAQ100"])["n_days"] == 2
    assert m.window_stats(days, m.H_POST_START)["n_days"] == 1
    assert set(m.by_year(days, m.H_START["NASDAQ100"])) == {2024}
