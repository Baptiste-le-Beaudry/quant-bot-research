"""Tests for Exp 70 step 0 (DIX.csv revision check). Synthetic fixtures in tmp_path only."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exp70_step0", ROOT / "scripts" / "agents" / "exp70_step0.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _write(path, rows):
    path.write_text("date,price,dix,gex\n" + "".join(f"{d},100,0.4,{g}\n" for d, g in rows), encoding="utf-8")
    return path


def _dates(n):
    import datetime as dt
    return [str(dt.date(2020, 1, 1) + dt.timedelta(days=i)) for i in range(n)]


def test_identical_ok(tmp_path):
    rows = [(d, 1e9 + i) for i, d in enumerate(_dates(200))]
    snap = _write(tmp_path / "snap.csv", rows)
    a = _write(tmp_path / "a.csv", rows[:100])
    b = _write(tmp_path / "b.csv", rows[:150])
    r = m.step0(snap, {"20221205000000": a, "20250429000000": b}, expected_sha=None)
    assert r["verdict_step0"] == "OK_CONTINUER"
    assert r["archives"]["20221205000000"]["gex"]["n_common"] == 100
    assert r["archives"]["20221205000000"]["gex"]["n_diff_conservative"] == 0


def test_revised_reject(tmp_path):
    rows = [(d, 1e9) for d in _dates(200)]
    snap = _write(tmp_path / "snap.csv", rows)
    rev = [(d, 1.02e9 if i < 3 else 1e9) for i, (d, _) in enumerate(rows[:200])]  # 3/200 = 1.5 % differ by 2 %
    a = _write(tmp_path / "a.csv", rev)
    b = _write(tmp_path / "b.csv", rows)
    r = m.step0(snap, {"20221205000000": a, "20250429000000": b}, expected_sha=None)
    assert r["archives"]["20221205000000"]["exceeds_1pct"]
    assert r["verdict_step0"] == "REJET_DONNEES_REVISEES"


def test_threshold_boundaries(tmp_path):
    rows = [(d, 1e9) for d in _dates(200)]
    snap = _write(tmp_path / "snap.csv", rows)
    # 2/200 = 1 % exactly differ -> not "more than 1 %"; and 0.5 % gaps never count
    rev = [(d, 1.02e9 if i < 2 else (1.005e9 if i < 50 else 1e9)) for i, (d, _) in enumerate(rows)]
    a = _write(tmp_path / "a.csv", rev)
    r = m.step0(snap, {"20221205000000": a, "20250429000000": a}, expected_sha=None)
    assert r["archives"]["20221205000000"]["gex"]["n_diff_conservative"] == 2
    assert r["verdict_step0"] == "OK_CONTINUER"


def test_conservative_denominator(tmp_path):
    # snapshot 1.0e9, archive 0.9905e9: gap/|s| = 0.95 % (not flagged), gap/min = 0.959 % ; use a sign flip case
    snap = _write(tmp_path / "snap.csv", [("2020-01-01", 1e8)])
    a = _write(tmp_path / "a.csv", [("2020-01-01", -1e8)])
    c = m.compare(m.load_dix(snap), m.load_dix(a))
    assert c["n_diff_conservative"] == 1


def test_missing_archive_kinds(tmp_path):
    rows = [(d, 1e9) for d in _dates(50)]
    snap = _write(tmp_path / "snap.csv", rows)
    a = _write(tmp_path / "a.csv", rows)
    assert m.step0(snap, {"20250429000000": a}, expected_sha=None)["verdict_step0"] == "INCOMPLET_ARCHIVES_MANQUANTES"
    assert m.step0(snap, {}, expected_sha=None)["verdict_step0"] == "AUCUNE_ARCHIVE_FORWARD_SEUL"


def test_sha_guard(tmp_path):
    snap = _write(tmp_path / "snap.csv", [("2020-01-01", 1e9)])
    try:
        m.step0(snap, {})
    except ValueError:
        return
    raise AssertionError("sha guard not triggered")
