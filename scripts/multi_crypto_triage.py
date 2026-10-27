"""
scripts/multi_crypto_triage.py — multi-crypto expansion plan, Etape 6:
build the first-screen triage table from docs/multi_crypto_screen_raw.csv
(produced by scripts/multi_crypto_screen.py's Test A "transfer" and Test B
"own" modes) plus the known BTC/ETH reference rows, and apply the
elimination bands decided BEFORE looking at results (Experiment 33 card,
docs/research_plan_status.md): PF>1.30 "very promising", 1.15-1.30
"investigate" (-> proceeds to walk-forward), 1.00-1.15 "weak", <1
"provisional reject". Only Test B ("own", the realistic recalibrated
screen) drives the triage verdict/walk-forward decision -- Test A
("transfer") is reported alongside for context (pure-generalization
signal) but is not itself gating, per the plan's Etape 4 vs Etape 7 split.

Usage:
    python scripts/multi_crypto_triage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "multi_crypto_screen_raw.csv")

BTC_ETH_REFERENCE = [
    # From Experiment 28 (walk-forward, not a single-split screen -- BTC/ETH never had a separate
    # Test B screen since V3 IS the outcome of their own iterative development). Shown for context.
    {"symbol": "BTCUSDT", "mode": "reference(walk-forward)", "n_trades": 211, "profit_factor": 1.628},
    {"symbol": "ETHUSDT", "mode": "reference(walk-forward)", "n_trades": 333, "profit_factor": 1.300},
]


MIN_N_FOR_VERDICT = 20  # matches the codebase-wide "train_selected.sum() < 20" convention
                         # (e.g. walk_forward_engine.py) for "too few to calibrate/trust at all"


def verdict(pf, n) -> str:
    if pf is None or pd.isna(pf):
        return "N/A"
    if n is not None and n < MIN_N_FOR_VERDICT:
        return f"INSUFFICIENT SAMPLE (n={int(n)}<{MIN_N_FOR_VERDICT}) -- PF not trustworthy"
    if pf > 1.30:
        return "VERY PROMISING"
    if pf >= 1.15:
        return "INVESTIGATE (-> walk-forward)"
    if pf >= 1.00:
        return "WEAK"
    return "PROVISIONAL REJECT"


def main():
    if not os.path.exists(RAW_PATH):
        print(f"No screen results yet at {RAW_PATH}")
        return
    df = pd.read_csv(RAW_PATH)

    print("\n" + "=" * 110)
    print("  EXPERIMENT 33 -- MULTI-CRYPTO FIRST SCREEN TABLE (Etape 6)")
    print("=" * 110)
    print(f"{'Symbol':<10}{'Mode':<10}{'n':>8}{'PF':>8}{'WinRate%':>10}{'TotalRet%':>11}{'CAGR%':>9}{'MaxDD%':>9}{'Verdict':<28}")
    for row in BTC_ETH_REFERENCE:
        print(f"{row['symbol']:<10}{'ref-WF':<10}{row['n_trades']:>8}{row['profit_factor']:>8.3f}"
              f"{'':>10}{'':>11}{'':>9}{'':>9}{'(established baseline)':<28}")
    for _, r in df.sort_values(["symbol", "mode"]).iterrows():
        n = r.get("n_trades", 0)
        if not n or n == 0:
            print(f"{r['symbol']:<10}{r['mode']:<10}{'0':>8}{'--':>8}{'--':>10}{'--':>11}{'--':>9}{'--':>9}"
                  f"{r.get('reason', 'no trades'):<28}")
            continue
        pf = r.get("profit_factor")
        v = verdict(pf, n) if r["mode"] == "own" else "(context only)"
        cagr = r.get("cagr_pct")
        print(f"{r['symbol']:<10}{r['mode']:<10}{int(n):>8}{pf:>8.3f}{r.get('win_rate_pct', float('nan')):>10.1f}"
              f"{r.get('total_return_pct', float('nan')):>11.2f}"
              f"{cagr if cagr == cagr else float('nan'):>9.2f}{r.get('max_dd_pct', float('nan')):>9.2f}{v:<28}")

    own = df[df["mode"] == "own"]
    survivors = own[(own["n_trades"] >= MIN_N_FOR_VERDICT) & (own["profit_factor"] >= 1.15)]["symbol"].tolist()
    rejects = own[(own["n_trades"] < MIN_N_FOR_VERDICT) | (own["profit_factor"] < 1.15)]["symbol"].tolist()
    print(f"\nSURVIVORS (Test B PF>=1.15 AND n>={MIN_N_FOR_VERDICT}, proceed to walk-forward): {survivors}")
    print(f"REJECTED/DEFERRED at screen (PF<1.15 OR n<{MIN_N_FOR_VERDICT} -- too few trades to trust "
          f"regardless of PF, e.g. a 3.0 PF on 7 trades is NOT evidence of anything): {rejects}")
    missing = [s for s in ["SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT"]
               if s not in own["symbol"].tolist()]
    if missing:
        print(f"NOT YET SCREENED: {missing}")


if __name__ == "__main__":
    main()
