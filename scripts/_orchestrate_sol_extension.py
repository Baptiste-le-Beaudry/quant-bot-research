"""
scripts/_orchestrate_sol_extension.py — one-shot driver for the SOL extension to
Experiment 33/34: (a) per-symbol optimization sweep for SOLUSDT under the TRANSFER config
(threshold/stop-pct/horizon, cheap 4-fold probe then full-fold confirm, same relative
n-floor discipline as multi_crypto_optimize_symbol.py's DOGE/LTC fix), (b) rebuild the
9-symbol portfolio (8 ADOPTED symbols + SOL) and risk-sweep it, (c) print a comparison
against the currently-ADOPTED 8-symbol portfolio (125.0% CAGR / -22.72% MaxDD / Calmar
5.501 @ 3.0% risk/trade) so the decision to adopt or not is explicit.

AVAXUSDT is NOT touched here -- already a clean REJECT on well-powered transfer-mode
walk-forward data (n=1394, 4/13 folds PF>1, median PF=0.911), nothing further to run.

Usage: python scripts/_orchestrate_sol_extension.py
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pandas as pd

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
SCRIPTS = os.path.dirname(__file__)
PY = sys.executable

BASELINE_WF_MEDIAN_PF = 1.441
BASELINE_WF_N_TOTAL = 1287
MIN_WF_N_TOTAL = max(20, int(0.4 * BASELINE_WF_N_TOTAL))  # = 514, same relative-floor fix as DOGE/LTC
MIN_RELATIVE_IMPROVEMENT = 0.15
PROBE_FOLDS = 4

SWEEP_GRID = {"threshold": [0.65, 0.75], "stop_pct": [80, 95], "horizon": [15, 20]}


def run(cmd, **kw):
    print("  $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 3600), **kw)


def summarize(tag: str) -> dict:
    path = os.path.join(DOCS, f"multi_crypto_wf_SOLUSDT_{tag}_summary.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    sub = df[df.get("n_trades", 0) > 0]
    if len(sub) == 0:
        return {"n_folds_with_trades": 0}
    pf = sub["profit_factor"].replace([float("inf")], pd.NA).dropna()
    return {
        "n_folds_with_trades": len(sub), "n_trades_total": int(sub["n_trades"].sum()),
        "median_pf": float(pf.median()) if len(pf) else None,
        "n_forced_liq": int(sub["n_forced_liq"].sum()),
    }


def main():
    print("=" * 110)
    print("  SOLUSDT TRANSFER-MODE OPTIMIZATION SWEEP")
    print(f"  baseline: median_pf={BASELINE_WF_MEDIAN_PF}, n_total={BASELINE_WF_N_TOTAL}, "
          f"MIN_WF_N_TOTAL floor={MIN_WF_N_TOTAL}")
    print("=" * 110)

    confirmed = []  # list of (param, value, wf_median_pf, wf_n_total)
    for param, values in SWEEP_GRID.items():
        print(f"\n--- SOLUSDT: {param} sweep {values} (transfer-mode baseline) ---")
        flag = "--" + param.replace("_", "-")
        best = None
        for v in values:
            tag_probe = f"transfer_{param}{v}_probe"
            cmd = [PY, os.path.join(SCRIPTS, "multi_crypto_transfer_walkforward.py"),
                   "--symbol", "SOLUSDT", "--max-folds", str(PROBE_FOLDS),
                   flag, str(v), "--tag", tag_probe]
            run(cmd, timeout=3600)
            s = summarize(tag_probe)
            n, pf = s.get("n_trades_total"), s.get("median_pf")
            print(f"    {param}={v}: probe(4 folds) n_total={n} median_pf={pf}")
            if n is not None and pf is not None and n >= 20:
                if best is None or pf > best[1]:
                    best = (v, pf, n)
        if best is None:
            print(f"  {param}: no probe cleared n>=20 in the 4-fold sample -- REJECT (insufficient sample)")
            continue
        v, probe_pf, probe_n = best
        if probe_pf > BASELINE_WF_MEDIAN_PF * (1 + MIN_RELATIVE_IMPROVEMENT):
            print(f"  {param}={v}: PROMISING probe (median_pf={probe_pf:.3f} vs baseline "
                  f"{BASELINE_WF_MEDIAN_PF}, >={MIN_RELATIVE_IMPROVEMENT*100:.0f}% better) "
                  f"-- confirming via FULL walk-forward (all folds)")
            tag_full = f"transfer_{param}{v}"
            cmd = [PY, os.path.join(SCRIPTS, "multi_crypto_transfer_walkforward.py"),
                   "--symbol", "SOLUSDT", "--max-folds", "20", flag, str(v), "--tag", tag_full]
            run(cmd, timeout=6 * 3600)
            s = summarize(tag_full)
            wf_pf, wf_n = s.get("median_pf"), s.get("n_trades_total", 0)
            wf_liq = s.get("n_forced_liq", 1)
            print(f"    full confirmation: {s}")
            if wf_n is None or wf_n < MIN_WF_N_TOTAL:
                print(f"  {param}={v}: REJECTED -- confirming n_total={wf_n} < {MIN_WF_N_TOTAL} "
                      f"(floor=max(20, 40% of baseline n={BASELINE_WF_N_TOTAL})) -- INSUFFICIENT SAMPLE")
            elif wf_pf is not None and wf_pf > BASELINE_WF_MEDIAN_PF and wf_liq == 0:
                print(f"  {param}={v}: CONFIRMED improvement (median_pf={wf_pf:.3f} > baseline "
                      f"{BASELINE_WF_MEDIAN_PF}, 0 forced liq, n={wf_n}>={MIN_WF_N_TOTAL})")
                confirmed.append((param, v, wf_pf, wf_n, tag_full))
            else:
                print(f"  {param}={v}: REJECTED -- did not hold up under full walk-forward "
                      f"(median_pf={wf_pf}, baseline={BASELINE_WF_MEDIAN_PF}, forced_liq={wf_liq})")
        else:
            print(f"  {param}={v}: best probe median_pf={probe_pf:.3f} does not clear the "
                  f"{MIN_RELATIVE_IMPROVEMENT*100:.0f}% bar over baseline {BASELINE_WF_MEDIAN_PF} -- REJECT")

    print(f"\n{'='*110}\n  SOLUSDT OPTIMIZATION SUMMARY: {len(confirmed)} confirmed improvement(s): {confirmed}\n{'='*110}")
    out_path = os.path.join(DOCS, "multi_crypto_optimize_SOLUSDT_transfer.csv")
    if confirmed:
        pd.DataFrame([{"param": p, "value": v, "wf_median_pf": pf, "wf_n_total": n} for p, v, pf, n, _ in confirmed]).to_csv(out_path, index=False)
    else:
        pd.DataFrame([{"symbol": "SOLUSDT", "result": "no improvement found (transfer-mode V3 defaults kept)"}]).to_csv(out_path, index=False)
    print(f"Saved -> {out_path}")

    # Pick the best confirmed tag (highest wf_median_pf) if any, else the plain transfer baseline.
    if confirmed:
        best_conf = max(confirmed, key=lambda c: c[2])
        sol_tag = best_conf[4]
        print(f"\nUsing SOLUSDT:{sol_tag} (best confirmed) for the portfolio rebuild.")
    else:
        sol_tag = "transfer"
        print(f"\nNo optimization improvement -- using SOLUSDT:{sol_tag} (V3-default transfer config) for the portfolio rebuild.")

    # --- Etape 11/12/13: rebuild 9-symbol portfolio, correlate, risk-sweep ---
    confirmed_8 = "BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,LINKUSDT,LTCUSDT"
    all_9 = confirmed_8 + f",SOLUSDT:{sol_tag}"

    print(f"\n{'='*110}\n  Etape 11: correlation analysis (9 symbols)\n{'='*110}")
    r = subprocess.run([PY, os.path.join(SCRIPTS, "multi_crypto_correlation.py"), "--symbols", all_9],
                        timeout=1800)
    print(f"(correlation exit code {r.returncode})")

    print(f"\n{'='*110}\n  Etape 12: build 9-symbol combined portfolio\n{'='*110}")
    out9 = os.path.join(DOCS, "multi_crypto_portfolio_trades_9sym.csv")
    subprocess.run([PY, os.path.join(SCRIPTS, "multi_crypto_build_portfolio.py"),
                     "--symbols", all_9, "--out", out9], timeout=1800)

    print(f"\n{'='*110}\n  Etape 13: risk sweep on 9-symbol portfolio\n{'='*110}")
    plain_9 = ",".join(e.split(":")[0] for e in all_9.split(","))  # risk_sweep matches on the
    # combined CSV's plain "symbol" column, which build_portfolio.py already normalized (no tags)
    subprocess.run([PY, os.path.join(SCRIPTS, "multi_crypto_risk_sweep.py"),
                     "--data", out9, "--symbols", "BTCUSDT,ETHUSDT," + plain_9], timeout=3600)

    print(f"\n{'='*110}")
    print("  COMPARISON REMINDER: 8-symbol ADOPTED portfolio = CAGR=125.0% MaxDD=-22.72% "
          "Calmar=5.501 PF=1.778 @ 3.0%% risk/trade, 0 forced liq")
    print("  Compare the 9-symbol PORTFOLIO block above at the SAME or nearby risk-pct row. "
          "Adopt the 9-symbol version only if it beats that bar (better CAGR at comparable/"
          "controlled DD, or better DD at comparable CAGR); otherwise keep the 8-symbol "
          "portfolio frozen and document SOL as confirmed standalone but not blended in.")
    print("=" * 110)
    print("=== SOL EXTENSION ORCHESTRATOR COMPLETE ===")


if __name__ == "__main__":
    main()
