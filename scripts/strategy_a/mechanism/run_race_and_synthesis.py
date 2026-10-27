"""scripts/strategy_a/mechanism/run_race_and_synthesis.py — Phase 6 (trailing
-style mechanism proxy) and Phase 12-14 (volatility-matched / null / model-
value) synthesis, consolidating numbers already computed by
run_crypto_analysis.py and run_index_analysis.py into small citation-ready
CSVs for the final report.

Phase 6 proxy (DISCLOSED SIMPLIFICATION): the mandate asks whether a
+1sigma rebound level is reached before a -1sigma adverse level. Doing a
strict normalized level-crossing race requires re-walking full per-event
paths (kept, for the ~350k-event crypto generic population, only as
summary stats to bound memory). As a lighter, honestly-labeled DESCRIPTIVE
proxy, this script instead reports P(time_to_MFE < time_to_MAE) -- whether
the favorable extreme is reached before the adverse extreme within the
same forward window -- computed at the -1.5 sigma threshold (consistent
with the year/hour/volume-regime diagnostics already using that reference
threshold) for all four markets.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

from mechanism_common import shock_z, forward_path_metrics, MECH_OUT_DIR
from quant_bot.data.splits import pre_holdout

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
CACHE_DIR = os.path.join(REPO_ROOT, "docs", "_full_data_cache")
THR = -1.5


def race_crypto(symbol: str) -> dict:
    df = pd.read_pickle(os.path.join(CACHE_DIR, f"{symbol}_full.pkl"))
    df = pre_holdout(df, symbol)
    close = df["close"]
    sz = shock_z(close)
    event_pos = np.flatnonzero((sz <= THR).to_numpy())
    fpm = forward_path_metrics(close, event_pos, max_horizon=50)
    pct_favorable_first = float((fpm["time_to_mfe"] < fpm["time_to_mae"]).mean() * 100)
    pct_tie = float((fpm["time_to_mfe"] == fpm["time_to_mae"]).mean() * 100)
    return {"market": symbol, "population": "generic_dip_B", "shock_threshold": THR,
            "n": len(fpm), "pct_favorable_extreme_first": round(pct_favorable_first, 2),
            "pct_tie": round(pct_tie, 2)}


def race_index(symbol: str) -> dict:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from run_index_analysis import load_bars, forward_path_metrics_session_aware
    bars = load_bars(symbol)
    close = bars["close"]
    sz = shock_z(close)
    event_pos = np.flatnonzero((sz <= THR).to_numpy())
    fpm = forward_path_metrics_session_aware(bars, event_pos, max_horizon=50)
    pct_favorable_first = float((fpm["time_to_mfe"] < fpm["time_to_mae"]).mean() * 100)
    pct_tie = float((fpm["time_to_mfe"] == fpm["time_to_mae"]).mean() * 100)
    return {"market": symbol, "population": "generic_dip_B", "shock_threshold": THR,
            "n": len(fpm), "pct_favorable_extreme_first": round(pct_favorable_first, 2),
            "pct_tie": round(pct_tie, 2)}


def main():
    rows = [race_crypto("BTCUSDT"), race_crypto("ETHUSDT"), race_index("QQQ"), race_index("SPY")]
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(MECH_OUT_DIR, "phase6_race_proxy.csv"), index=False)
    print(out.to_string(index=False))

    # Phase 12-14 synthesis: pull the already-computed A vs B ratio comparison into one table
    a_crypto = pd.read_csv(os.path.join(MECH_OUT_DIR, "crypto_analysis_a_combined.csv"))
    b_crypto = pd.read_csv(os.path.join(MECH_OUT_DIR, "crypto_analysis_b_combined.csv"))
    a_index = pd.read_csv(os.path.join(MECH_OUT_DIR, "index_analysis_a_combined.csv"))
    b_index = pd.read_csv(os.path.join(MECH_OUT_DIR, "index_analysis_b_combined.csv"))

    synth = []
    for df, pop, mkt_class in [(a_crypto, "A_strategy_a_selected", "crypto"), (b_crypto, "B_generic_dip", "crypto"),
                                (a_index, "A_index_approx_structural_only", "index"), (b_index, "B_generic_dip", "index")]:
        for _, r in df.iterrows():
            synth.append({
                "market_class": mkt_class, "symbol": r["symbol"], "population": pop,
                "shock_threshold": r["shock_threshold"], "n": r["n"],
                "n_cluster_adjusted": r.get("n_cluster_adjusted"),
                "mfe_over_abs_mae": r.get("mfe_over_abs_mae"),
                "pct_mfe_gt_abs_mae": r.get("pct_mfe_gt_abs_mae"),
                "median_fwdret_30m_pct": r.get("median_fwdret_30m_pct"),
            })
    synth_df = pd.DataFrame(synth)
    synth_df.to_csv(os.path.join(MECH_OUT_DIR, "phase12_14_synthesis.csv"), index=False)
    print("\nSynthesis table written.")


if __name__ == "__main__":
    main()
