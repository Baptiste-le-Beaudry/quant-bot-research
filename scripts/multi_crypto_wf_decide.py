"""
scripts/multi_crypto_wf_decide.py — multi-crypto expansion plan, Etape 8:
read each survivor symbol's walk-forward summary CSV
(docs/multi_crypto_wf_{SYMBOL}_summary.csv, produced by
scripts/multi_crypto_walkforward.py) and decide, per Experiment 33's own
stated stability criteria (n_total, folds-with-trades, PF median/mean,
%folds PF>1, forced liquidations -- decided BEFORE looking at results,
same discipline as every prior screen), whether each symbol is CONFIRMED
for the portfolio stage or REJECTED despite passing the Etape 6 screen
(possible if walk-forward reveals instability a single-split screen
couldn't see -- exactly what walk-forward exists to catch).

Acceptance bar (mirrors BTC/ETH's own registered walk-forward quality,
Experiment 28: BTC median PF=1.628, ETH median PF=1.300, both 0 forced
liquidations, most folds with trades) -- NOT identical thresholds (BTC/
ETH's own numbers aren't a hard pass/fail line, they're context), but the
same STRUCTURE of judgment: reject on ANY forced liquidation (this
strategy family's most costly failure mode, consistent with every prior
elimination rule in this project), reject if median PF <= 1 (no
walk-forward-confirmed edge), reject if too few folds have trades to say
anything (<3 folds with trades), flag (not reject) low total n as a
separate caveat for the portfolio-weighting stage.

Usage:
    python scripts/multi_crypto_wf_decide.py --symbols BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,LINKUSDT,LTCUSDT
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")

MIN_FOLDS_WITH_TRADES = 3
REJECT_ANY_FORCED_LIQ = True
REJECT_MEDIAN_PF_LE_1 = True


def summarize(symbol: str) -> dict:
    path = os.path.join(DOCS, f"multi_crypto_wf_{symbol}_summary.csv")
    if not os.path.exists(path):
        return {"symbol": symbol, "verdict": "NO DATA", "reason": f"{path} not found"}
    df = pd.read_csv(path)
    sub = df[df.get("n_trades", 0) > 0].copy()
    if len(sub) < MIN_FOLDS_WITH_TRADES:
        return {"symbol": symbol, "n_folds_with_trades": len(sub), "verdict": "REJECT",
                "reason": f"only {len(sub)} folds with trades (<{MIN_FOLDS_WITH_TRADES})"}
    pf = sub["profit_factor"].replace([np.inf], np.nan).dropna()
    n_total = int(sub["n_trades"].sum())
    n_forced = int(sub["n_forced_liq"].sum())
    median_pf = float(pf.median())
    mean_pf = float(pf.mean())
    pct_pf_gt1 = float((sub["profit_factor"] > 1).mean() * 100)
    total_ret = float(sub["total_return_pct"].sum())

    reasons = []
    if REJECT_ANY_FORCED_LIQ and n_forced > 0:
        reasons.append(f"forced_liq={n_forced}")
    if REJECT_MEDIAN_PF_LE_1 and median_pf <= 1.0:
        reasons.append(f"median_PF={median_pf:.3f}<=1.0")
    verdict = "REJECT" if reasons else "CONFIRMED"

    return {
        "symbol": symbol, "n_folds_total": len(df), "n_folds_with_trades": len(sub),
        "n_trades_total": n_total, "median_pf": round(median_pf, 3), "mean_pf": round(mean_pf, 3),
        "pct_folds_pf_gt1": round(pct_pf_gt1, 1), "total_return_pct_summed": round(total_ret, 2),
        "n_forced_liq": n_forced, "verdict": verdict,
        "reason": ", ".join(reasons) if reasons else "clears all criteria",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True)
    args = parser.parse_args()
    symbols = args.symbols.split(",")

    rows = [summarize(s) for s in symbols]
    print("\n" + "=" * 130)
    print("  ETAPE 8 -- WALK-FORWARD STABILITY DECISION (per symbol)")
    print("=" * 130)
    for r in rows:
        print(f"\n{r['symbol']}: {r['verdict']}")
        for k, v in r.items():
            if k not in ("symbol", "verdict"):
                print(f"    {k}: {v}")

    confirmed = [r["symbol"] for r in rows if r["verdict"] == "CONFIRMED"]
    rejected = [r["symbol"] for r in rows if r["verdict"] != "CONFIRMED"]
    print(f"\nCONFIRMED (proceed to portfolio/correlation): {confirmed}")
    print(f"REJECTED at walk-forward: {rejected}")

    pd.DataFrame(rows).to_csv(os.path.join(DOCS, "multi_crypto_wf_decision.csv"), index=False)
    with open(os.path.join(DOCS, "multi_crypto_wf_confirmed_symbols.txt"), "w") as f:
        f.write(",".join(confirmed))
    print(f"\nSaved -> docs/multi_crypto_wf_decision.csv, docs/multi_crypto_wf_confirmed_symbols.txt")


if __name__ == "__main__":
    main()
