"""
scripts/walk_forward_risk_sweep.py — Phase B of the risk-per-trade sweep
protocol (the user's detailed spec, 2026-08-18). Reads
docs/walk_forward_trades_export.csv (built once by
scripts/walk_forward_trade_export.py -- every individual walk-forward
TEST trade, its raw return, its fold's TRAIN-calibrated stop_distance,
and its fold's dynamic leverage_safe ceiling) and runs a full
COMPOUNDING risk-per-trade sweep on top of it. Nothing here refits any
model -- this is pure, fast post-processing, which is the whole point of
splitting Phase A (expensive) from Phase B (cheap, iterate freely).

Everything else stays frozen per the protocol's own Étape 2.1: model,
threshold, entry filter, trailing, stop method, fees, slippage, funding,
exit logic, data, and trade ORDER (chronological, exactly as the
walk-forward produced it) are all already baked into the exported CSV.
The ONLY thing this script varies is RISK_PCT_PER_TRADE.

Position sizing per trade (Étape 2.3/2.4), with compounding (Étape 2.5):
  risk_dollar   = equity_t * risk_pct
  notional      = risk_dollar / stop_distance_of_this_trade
  leverage_req  = notional / equity_t
  leverage_used = min(leverage_req, leverage_safe_of_this_fold)   <- the cap
  notional_used = leverage_used * equity_t
  pnl           = notional_used * raw_return
  equity_{t+1}  = equity_t + pnl
A simultaneous-trades risk cap (Étape 2.17) is also supported: if
max_total_open_risk is set, a new trade's risk_dollar is capped by
whatever open-risk budget remains given other currently-open positions
(tracked by exit_time, since BTC/ETH trades can overlap in real time even
though each symbol's own trades can't).

Usage:
    python scripts/walk_forward_risk_sweep.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from scripts.diagnostic_leverage import STOP_OUT_FRACTION

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "walk_forward_trades_export.csv")
INITIAL_EQUITY = 100_000.0

COARSE_GRID = [0.0025, 0.0050, 0.0075, 0.0100, 0.0125, 0.0150, 0.0175,
               0.0200, 0.0250, 0.0300, 0.0400, 0.0500]
# EXTENDED beyond the user's original grid: at the walk-forward's dynamic,
# TRAIN-calibrated leverage ceilings (2.4x-10x, from very WIDE protective
# stops of 3.9%-15.4%), leverage_req=risk_pct/stop_distance never approaches
# leverage_safe anywhere in the 0.25%-5% range (peak observed leverage_used
# stayed under 1.3x even at 5% risk) -- the safety cap never binds there,
# so no real elbow/plateau exists within that range to report honestly.
# Extending much higher to actually find where the leverage cap starts
# binding and where compounding drawdown genuinely becomes dangerous.
EXTENDED_GRID = [0.0750, 0.1000, 0.1500, 0.2000, 0.2500, 0.3000, 0.4000, 0.5000]

# Étape 2.10 elimination thresholds -- chosen BEFORE looking at results, per the protocol's own rule.
MAX_ACCEPTABLE_DD = 25.0        # %, reject if breached
MAX_MC_P_DD30 = 0.05            # reject if P(MaxDD > 30%) > 5% in the Monte Carlo
REJECT_ANY_FORCED_LIQ = True

MC_N_SIMULATIONS = 10_000
MC_SEED = 42


def load_trades(symbols=None) -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["entry_time", "exit_time"])
    if symbols is not None:
        df = df[df["symbol"].isin(symbols)]
    return df.sort_values("entry_time").reset_index(drop=True)


def simulate_compounding(trades: pd.DataFrame, risk_pct: float, initial_equity: float = INITIAL_EQUITY,
                          max_total_open_risk: float = None):
    equity = initial_equity
    equity_curve = [(trades.iloc[0]["entry_time"] if len(trades) else pd.Timestamp.now(tz="UTC"), equity)]
    open_positions = []  # list of dicts: {"exit_time":, "allocated_risk":}
    trade_log = []

    for _, t in trades.iterrows():
        open_positions = [p for p in open_positions if p["exit_time"] > t["entry_time"]]
        current_open_risk = sum(p["allocated_risk"] for p in open_positions)

        risk_dollar = equity * risk_pct
        if max_total_open_risk is not None:
            available = max(0.0, equity * max_total_open_risk - current_open_risk)
            risk_dollar = min(risk_dollar, available)
        if risk_dollar <= 0:
            continue

        stop_distance = t["stop_distance"]
        leverage_safe = t["leverage_safe"]
        notional = risk_dollar / stop_distance
        leverage_req = notional / equity
        leverage_used = min(leverage_req, leverage_safe)
        notional_used = leverage_used * equity
        actual_risk_dollar = notional_used * stop_distance

        pnl = notional_used * t["raw_return"]
        equity += pnl
        liq_move_used = STOP_OUT_FRACTION / leverage_used if leverage_used > 0 else np.inf
        forced = bool(t["was_stopped"]) and (liq_move_used <= stop_distance)

        equity_curve.append((t["exit_time"], equity))
        open_positions.append({"exit_time": t["exit_time"], "allocated_risk": actual_risk_dollar})
        trade_log.append({
            "symbol": t["symbol"], "fold": t["fold"], "entry_time": t["entry_time"], "exit_time": t["exit_time"],
            "pnl": pnl, "equity_after": equity, "leverage_used": leverage_used,
            "leverage_capped": leverage_req > leverage_safe, "forced_liq": forced,
        })

    return pd.DataFrame(trade_log), equity_curve


def compute_metrics(trade_log: pd.DataFrame, equity_curve: list, initial_equity: float = INITIAL_EQUITY) -> dict:
    if len(trade_log) == 0:
        return {"n_trades": 0}
    eq_times = [e[0] for e in equity_curve]
    eq_vals = np.array([e[1] for e in equity_curve])
    running_max = np.maximum.accumulate(eq_vals)
    dd = (eq_vals - running_max) / running_max
    max_dd_pct = float(dd.min() * 100)
    min_equity = float(eq_vals.min())

    # Recovery time: bars from the max-DD trough to the next new equity high.
    trough_idx = int(np.argmin(dd))
    recovery_idx = None
    if trough_idx < len(eq_vals) - 1:
        peak_before_trough = running_max[trough_idx]
        for k in range(trough_idx + 1, len(eq_vals)):
            if eq_vals[k] >= peak_before_trough:
                recovery_idx = k
                break
    if recovery_idx is not None:
        recovery_days = (eq_times[recovery_idx] - eq_times[trough_idx]).days
    else:
        recovery_days = None  # never recovered within the sample

    pnls = trade_log["pnl"].to_numpy()
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    total_return_pct = (eq_vals[-1] / initial_equity - 1) * 100
    years = max((eq_times[-1] - eq_times[0]).days / 365.25, 1 / 365.25)
    cagr_pct = ((eq_vals[-1] / initial_equity) ** (1 / years) - 1) * 100
    calmar = cagr_pct / abs(max_dd_pct) if max_dd_pct != 0 else float("inf")

    per_trade_ret = pnls / trade_log["equity_after"].shift(1).fillna(initial_equity).to_numpy()
    sharpe_like = float(per_trade_ret.mean() / (per_trade_ret.std() + 1e-12))
    downside = per_trade_ret[per_trade_ret < 0]
    sortino_like = float(per_trade_ret.mean() / (downside.std() + 1e-12)) if len(downside) > 1 else float("nan")

    # Worst losing streak (consecutive losing trades, by count).
    is_loss = (pnls <= 0).astype(int)
    worst_streak = 0
    cur = 0
    for v in is_loss:
        cur = cur + 1 if v else 0
        worst_streak = max(worst_streak, cur)

    return {
        "n_trades": len(trade_log), "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2), "max_dd_pct": round(max_dd_pct, 2),
        "profit_factor": round(pf, 3), "sharpe_like": round(sharpe_like, 4),
        "sortino_like": round(sortino_like, 4) if not np.isnan(sortino_like) else None,
        "calmar": round(calmar, 3), "worst_trade_pct_equity": round(float(pnls.min() / initial_equity * 100), 3),
        "worst_streak": int(worst_streak), "n_forced_liq": int(trade_log["forced_liq"].sum()),
        "avg_leverage_used": round(float(trade_log["leverage_used"].mean()), 2),
        "peak_leverage_used": round(float(trade_log["leverage_used"].max()), 2),
        "min_equity": round(min_equity, 0), "recovery_days": recovery_days,
        "return_over_maxdd": round(total_return_pct / abs(max_dd_pct), 3) if max_dd_pct != 0 else float("inf"),
    }


def monte_carlo_dd(trade_log: pd.DataFrame, initial_equity: float = INITIAL_EQUITY,
                    n_sims: int = MC_N_SIMULATIONS, seed: int = MC_SEED) -> dict:
    """Bootstrap resample the trade PNL-AS-FRACTION-OF-EQUITY-AT-ENTRY series
    (not raw $ pnls, so resampled sequences compound realistically at
    INITIAL_EQUITY regardless of the original path) into n_sims independent
    equal-length sequences and compute the resulting max-DD distribution."""
    if len(trade_log) < 5:
        return {}
    per_trade_frac = (trade_log["pnl"] / trade_log["equity_after"].shift(1).fillna(initial_equity)).to_numpy()
    rng = np.random.default_rng(seed)
    n = len(per_trade_frac)
    dds = np.empty(n_sims)
    ruin_50 = 0
    for s in range(n_sims):
        seq = rng.choice(per_trade_frac, size=n, replace=True)
        eq = initial_equity * np.cumprod(1 + seq)
        eq = np.concatenate([[initial_equity], eq])
        running_max = np.maximum.accumulate(eq)
        dd = ((eq - running_max) / running_max).min() * 100
        dds[s] = dd
        if eq.min() < initial_equity * 0.5:
            ruin_50 += 1
    return {
        "mc_median_dd": round(float(np.median(dds)), 2),
        "mc_p90_dd": round(float(np.percentile(dds, 10)), 2),  # 10th percentile of DD (most negative 10%) = p90 severity
        "mc_p95_dd": round(float(np.percentile(dds, 5)), 2),
        "mc_p99_dd": round(float(np.percentile(dds, 1)), 2),
        "mc_p_dd_gt_10": round(float((dds < -10).mean()), 4),
        "mc_p_dd_gt_20": round(float((dds < -20).mean()), 4),
        "mc_p_dd_gt_30": round(float((dds < -30).mean()), 4),
        "mc_p_dd_gt_50": round(float((dds < -50).mean()), 4),
        "mc_risk_of_ruin_50pct": round(ruin_50 / n_sims, 4),
    }


def print_sweep_table(rows: list, title: str) -> None:
    print("\n" + "=" * 130)
    print(f"  {title}")
    print("=" * 130)
    header = (f"{'Risk%':>7}{'n':>5}{'CAGR%':>9}{'PF':>8}{'MaxDD%':>9}{'Calmar':>8}{'Sharpe':>8}"
              f"{'WorstStrk':>10}{'ForcedLiq':>10}{'AvgLev':>8}{'PeakLev':>8}{'Ret/DD':>8}")
    print(header)
    for r in rows:
        if r.get("n_trades", 0) == 0:
            continue
        print(f"{r['risk_pct']*100:>6.2f}%{r['n_trades']:>5}{r['cagr_pct']:>9.2f}{r['profit_factor']:>8.3f}"
              f"{r['max_dd_pct']:>9.2f}{r['calmar']:>8.3f}{r['sharpe_like']:>8.4f}{r['worst_streak']:>10}"
              f"{r['n_forced_liq']:>10}{r['avg_leverage_used']:>8.2f}{r['peak_leverage_used']:>8.2f}"
              f"{r['return_over_maxdd']:>8.3f}")


def eliminate_and_recommend(rows: list, mc_rows: dict) -> None:
    print("\n  -- Étape 2.10 elimination --")
    survivors = []
    for r in rows:
        if r.get("n_trades", 0) == 0:
            continue
        reasons = []
        if REJECT_ANY_FORCED_LIQ and r["n_forced_liq"] > 0:
            reasons.append(f"forced_liq={r['n_forced_liq']}")
        if abs(r["max_dd_pct"]) > MAX_ACCEPTABLE_DD:
            reasons.append(f"maxDD={r['max_dd_pct']:.1f}%>{MAX_ACCEPTABLE_DD}%")
        mc = mc_rows.get(r["risk_pct"])
        if mc and mc.get("mc_p_dd_gt_30", 0) > MAX_MC_P_DD30:
            reasons.append(f"MC P(DD>30%)={mc['mc_p_dd_gt_30']*100:.1f}%>{MAX_MC_P_DD30*100:.0f}%")
        status = "REJECT: " + ", ".join(reasons) if reasons else "OK"
        print(f"  risk={r['risk_pct']*100:.2f}%: {status}")
        if not reasons:
            survivors.append(r)

    if not survivors:
        print("\n  No risk level survives elimination -- something is wrong with the grid or thresholds.")
        return

    best_return = max(rows, key=lambda r: r.get("total_return_pct", -1e9) if r.get("n_trades", 0) else -1e9)
    best_calmar = max(survivors, key=lambda r: r["calmar"])
    # "recommended robust zone": among survivors, the plateau where calmar is within 5% of its own max
    calmar_max = best_calmar["calmar"]
    plateau = [r for r in survivors if r["calmar"] >= calmar_max * 0.95]
    plateau_sorted = sorted(plateau, key=lambda r: r["risk_pct"])

    print(f"\n  BEST RAW RETURN (ignores risk):        {best_return['risk_pct']*100:.2f}% "
          f"(CAGR={best_return.get('cagr_pct','?')}%, MaxDD={best_return.get('max_dd_pct','?')}%)")
    print(f"  BEST RISK-ADJUSTED (max Calmar, survivors only): {best_calmar['risk_pct']*100:.2f}% "
          f"(CAGR={best_calmar['cagr_pct']}%, MaxDD={best_calmar['max_dd_pct']}%, Calmar={best_calmar['calmar']})")
    if plateau_sorted:
        lo, hi = plateau_sorted[0]["risk_pct"], plateau_sorted[-1]["risk_pct"]
        print(f"  RECOMMENDED ROBUST ZONE (Calmar within 5% of peak): {lo*100:.2f}%-{hi*100:.2f}%")
    print(f"\n  VERDICT: \"{plateau_sorted[-1]['risk_pct']*100:.2f}% is the highest risk level that stays in the\"")
    print(f"           \"robust zone -- no forced liquidations, MaxDD<{MAX_ACCEPTABLE_DD}%, Monte-Carlo P(DD>30%)<{MAX_MC_P_DD30*100:.0f}%,\"")
    print(f"           \"beyond which marginal return no longer compensates the added risk.\"")


def main():
    all_trades = load_trades()
    print(f"Loaded {len(all_trades)} total walk-forward trades "
          f"({all_trades['symbol'].value_counts().to_dict()})\n")

    for label, symbols in [("ETHUSDT solo", ["ETHUSDT"]), ("BTCUSDT solo", ["BTCUSDT"]),
                            ("PORTFOLIO (BTC+ETH combined)", ["BTCUSDT", "ETHUSDT"])]:
        trades = load_trades(symbols)
        rows, mc_rows = [], {}
        for risk_pct in COARSE_GRID + EXTENDED_GRID:
            trade_log, equity_curve = simulate_compounding(trades, risk_pct)
            m = compute_metrics(trade_log, equity_curve)
            m["risk_pct"] = risk_pct
            rows.append(m)
            if m.get("n_trades", 0) >= 5:
                mc = monte_carlo_dd(trade_log)
                mc_rows[risk_pct] = mc
        print_sweep_table(rows, f"{label} -- coarse + extended risk sweep")
        eliminate_and_recommend(rows, mc_rows)

    # Étape 2.17: simultaneous-trade risk cap -- does capping TOTAL open risk across
    # both symbols (not just per-trade risk) change the portfolio's risk profile?
    print("\n" + "=" * 130)
    print("  Étape 2.17 — simultaneous-trade risk cap (portfolio, BTC+ETH), at a representative risk_pct")
    print("=" * 130)
    portfolio_trades = load_trades(["BTCUSDT", "ETHUSDT"])
    for risk_pct in [0.0100, 0.0150, 0.0200]:
        for cap_label, cap in [("no cap", None), ("max_total_open_risk=1.5x per-trade", risk_pct * 1.5),
                                ("max_total_open_risk=2x per-trade", risk_pct * 2.0)]:
            trade_log, equity_curve = simulate_compounding(portfolio_trades, risk_pct, max_total_open_risk=cap)
            m = compute_metrics(trade_log, equity_curve)
            if m.get("n_trades", 0) == 0:
                continue
            print(f"  risk={risk_pct*100:.2f}%, {cap_label:<38}: n={m['n_trades']:>4} "
                  f"CAGR={m['cagr_pct']:>7.2f}% MaxDD={m['max_dd_pct']:>7.2f}% "
                  f"Calmar={m['calmar']:>7.3f} forced_liq={m['n_forced_liq']}")
        print()

    out_path = os.path.join(os.path.dirname(__file__), "..", "docs", "risk_sweep_summary.txt")
    print(f"\n(Full output should be redirected to a log file for the record -- see run instructions.)")


if __name__ == "__main__":
    main()
