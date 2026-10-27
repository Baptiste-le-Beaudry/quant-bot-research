"""
scripts/walk_forward_v3_risk_sweep.py — Étape ⑦: re-run Experiment 26's
full compounding risk-per-trade sweep + Monte Carlo (scripts/
walk_forward_risk_sweep.py, unchanged) on BASELINE_CANDIDATE_V3's much
larger trade population (544 trades from docs/walk_forward_v3_trades_export.csv,
vs the original 55) instead of the old threshold=0.75 export. Nothing in
the sweep/Monte Carlo/elimination logic is duplicated or modified --
this only monkey-patches DATA_PATH before calling the existing main().

Usage:
    python scripts/walk_forward_v3_risk_sweep.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import scripts.walk_forward_risk_sweep as rs

rs.DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_v3_trades_export.csv")

if __name__ == "__main__":
    rs.main()
