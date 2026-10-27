"""
scripts/multi_crypto_optimize_symbol.py — multi-crypto expansion plan,
per-symbol OPTIMIZATION phase (user's 2026-08-20 extension, layered AFTER
generalization is confirmed): for ONE walk-forward-CONFIRMED symbol, try
to beat its own frozen-V3 walk-forward result the same way BTC/ETH's own
return was improved over Experiments 1-31 -- mirroring the SPECIFIC things
that actually moved the needle there: Experiment 5 (threshold sweep),
Experiments 6/10 (protective-stop percentile sweep), Experiments 29/30
(horizon sweep). One hypothesis at a time, TRAIN-only, cheap single-split
screen first (same discipline as Experiment 5/29) to find a candidate,
THEN one confirming full walk-forward (same discipline as Experiment
6b/30) before accepting any deviation from V3. A candidate that doesn't
beat the symbol's own registered walk-forward result on both quality
(median PF) is REJECTED and documented as such -- not forced.

Sweep grids kept intentionally small (2 alternatives per parameter, not
a wide grid) given each cheap screen still costs several minutes and each
confirming walk-forward costs much more -- this needs to stay tractable
across 6 symbols in a bounded time window, matching the "one hypothesis,
not 200 rules" methodology rule (fish for a plausible candidate cheaply,
confirm expensively, don't grid-search blindly).

Usage:
    python scripts/multi_crypto_optimize_symbol.py --symbol BNBUSDT
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
SCRIPTS_DIR = os.path.dirname(__file__)

SWEEP_GRID = {
    "threshold": [0.65, 0.75],
    "stop_pct": [80, 95],
    "horizon": [15, 20],
}
MIN_RELATIVE_IMPROVEMENT = 0.15  # screen PF must beat baseline screen PF by >=15% relative
MIN_N_CANDIDATE = 15             # candidate screen must still have a usable sample


def run_screen(symbol: str, **overrides) -> dict:
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "multi_crypto_screen.py"),
           "--symbol", symbol, "--mode", "own"]
    for k, v in overrides.items():
        cmd += [f"--{k.replace('_', '-')}", str(v)]
    print(f"  running: {' '.join(cmd)}")
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=3600).stdout
    result = {}
    for key in ("n_trades", "profit_factor", "win_rate_pct"):
        m = re.search(rf"^\s*{key}:\s*(.+)$", out, re.MULTILINE)
        if m:
            try:
                result[key] = float(m.group(1))
            except ValueError:
                result[key] = m.group(1).strip()
    return result


def run_walkforward(symbol: str, **overrides) -> dict:
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "multi_crypto_walkforward.py"),
           "--symbol", symbol, "--max-folds", "20"]
    for k, v in overrides.items():
        cmd += [f"--{k.replace('_', '-')}", str(v)]
    print(f"  running: {' '.join(cmd)}")
    subprocess.run(cmd, timeout=6 * 3600)
    tag = "_" + "_".join(f"{k.split('_')[0] if k!='stop_pct' else 'stop'}{v}" for k, v in overrides.items())
    summary_path = os.path.join(DOCS, f"multi_crypto_wf_{symbol}{tag}_summary.csv")
    if not os.path.exists(summary_path):
        return {}
    df = pd.read_csv(summary_path)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args()
    symbol = args.symbol.upper()

    decision_path = os.path.join(DOCS, "multi_crypto_wf_decision.csv")
    screen_path = os.path.join(DOCS, "multi_crypto_screen_raw.csv")
    if not os.path.exists(decision_path):
        print(f"No walk-forward decision file yet ({decision_path}) -- run multi_crypto_wf_decide.py first")
        return
    decision = pd.read_csv(decision_path)
    row = decision[decision["symbol"] == symbol]
    if len(row) == 0 or row.iloc[0]["verdict"] != "CONFIRMED":
        print(f"{symbol}: not CONFIRMED at walk-forward -- not eligible for optimization, skipping")
        return
    baseline_wf_median_pf = float(row.iloc[0]["median_pf"])
    baseline_wf_n_total = int(row.iloc[0]["n_trades_total"])
    # A candidate's confirming walk-forward must not have collapsed the entry population --
    # threshold increases in particular can cut per-fold trade counts to 1-5, producing
    # degenerate all-win/all-loss (PF=inf or 0.0) folds that look like a huge improvement but
    # are pure small-sample noise (caught in practice: DOGEUSDT/LTCUSDT threshold=0.75 both
    # technically cleared a bare n>=20 floor with n=23/21 but were dominated by 1-2-trade folds
    # and an 82-86% reduction vs baseline n -- the SAME statistical unreliability class as
    # SOLUSDT's rejected n=7 screen result, just spread across a walk-forward instead of one
    # split; a stop-pct-only change doesn't restrict entries at all, so it never triggers this).
    MIN_WF_N_TOTAL = max(20, int(0.4 * baseline_wf_n_total))

    screen = pd.read_csv(screen_path)
    own_row = screen[(screen["symbol"] == symbol) & (screen["mode"] == "own")]
    baseline_screen_pf = float(own_row.iloc[0]["profit_factor"]) if len(own_row) else None

    print("\n" + "=" * 110)
    print(f"  {symbol} -- PER-SYMBOL OPTIMIZATION PASS")
    print(f"  baseline (V3, frozen): walk-forward median PF={baseline_wf_median_pf}, "
          f"Etape-6 screen PF={baseline_screen_pf}")
    print("=" * 110)

    report = {"symbol": symbol, "baseline_wf_median_pf": baseline_wf_median_pf,
              "baseline_screen_pf": baseline_screen_pf}
    confirmed_improvements = []

    for param, values in SWEEP_GRID.items():
        print(f"\n--- {symbol}: {param} sweep {values} (baseline=V3 default) ---")
        best = None
        for v in values:
            r = run_screen(symbol, **{param: v})
            n, pf = r.get("n_trades"), r.get("profit_factor")
            print(f"    {param}={v}: n={n} PF={pf}")
            if n is not None and pf is not None and n >= MIN_N_CANDIDATE:
                if best is None or pf > best[1]:
                    best = (v, pf, n)
        report[f"{param}_sweep_best"] = best
        if best is None:
            print(f"  {param}: no candidate cleared n>={MIN_N_CANDIDATE} -- REJECT (insufficient sample)")
            continue
        v, pf, n = best
        if baseline_screen_pf and pf > baseline_screen_pf * (1 + MIN_RELATIVE_IMPROVEMENT):
            print(f"  {param}={v}: PROMISING screen result (PF={pf:.3f} vs baseline {baseline_screen_pf:.3f}, "
                  f">={MIN_RELATIVE_IMPROVEMENT*100:.0f}% better) -- confirming via full walk-forward")
            wf = run_walkforward(symbol, **{param: v})
            wf_pf = wf.get("median_pf")
            wf_n = wf.get("n_trades_total", 0)
            print(f"    walk-forward confirmation: {wf}")
            if wf_n < MIN_WF_N_TOTAL:
                print(f"  {param}={v}: REJECTED -- confirming walk-forward n_trades_total={wf_n} < "
                      f"{MIN_WF_N_TOTAL} (floor = max(20, 40% of baseline's own n={baseline_wf_n_total})) -- "
                      f"INSUFFICIENT SAMPLE, not a trustworthy improvement, keeping V3 default")
            elif wf_pf is not None and wf_pf > baseline_wf_median_pf and wf.get("n_forced_liq", 1) == 0:
                print(f"  {param}={v}: CONFIRMED improvement (walk-forward median PF {wf_pf:.3f} > "
                      f"baseline {baseline_wf_median_pf:.3f}, 0 forced liq, n={wf_n}>={MIN_WF_N_TOTAL})")
                confirmed_improvements.append({"param": param, "value": v, "screen_pf": pf,
                                                "wf_median_pf": wf_pf, "wf_n_total": wf_n})
            else:
                print(f"  {param}={v}: REJECTED -- promising screen did NOT hold up under walk-forward "
                      f"(wf_median_pf={wf_pf}, baseline={baseline_wf_median_pf}) -- keeping V3 default")
        else:
            print(f"  {param}={v}: best screen PF={pf:.3f} does not clear the "
                  f"{MIN_RELATIVE_IMPROVEMENT*100:.0f}% bar over baseline {baseline_screen_pf} -- "
                  f"REJECT, keeping V3 default")

    print(f"\n{'='*110}\n  {symbol} OPTIMIZATION SUMMARY: {len(confirmed_improvements)} confirmed "
          f"improvement(s): {confirmed_improvements}\n{'='*110}")

    out_path = os.path.join(DOCS, f"multi_crypto_optimize_{symbol}.csv")
    pd.DataFrame(confirmed_improvements if confirmed_improvements else [{"symbol": symbol, "result": "no improvement found"}]).to_csv(out_path, index=False)
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
