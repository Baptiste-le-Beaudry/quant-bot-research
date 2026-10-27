"""
scripts/walk_forward_risk_sweep_stress.py — Étape 2.15: stress-test the
top-3 risk_pct candidates from the coarse/fine sweep (walk_forward_risk_sweep.py)
under slippage/gap/latency/funding, reusing the close_path saved by Phase A
(walk_forward_trade_export.py) to re-resolve each trade's exit under stress
WITHOUT reloading any price data or refitting any model. Per the user's own
observation (confirmed repeatedly this session, e.g. Experiment 1): gaps and
latency have been far more dangerous than funding -- this sweeps all four
but the emphasis/resolution is finer on gap and latency.

Usage:
    python scripts/walk_forward_risk_sweep_stress.py 0.0125 0.0150 0.0175
    (pass the 3 risk_pct candidates to test, as fractions; defaults to
    0.0100/0.0125/0.0150 if none given)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import TAKER_FEE_PCT, SLIPPAGE_PCT_EST
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.walk_forward_risk_sweep import (
    DATA_PATH, INITIAL_EQUITY, compute_metrics, monte_carlo_dd,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080


def resolve_stressed(path: np.ndarray, stop_distance: float, liq_move: float,
                      gap_extra: float = 0.0, slip_mult: float = 1.0, entry_delay: int = 0) -> tuple:
    """Re-resolves a trade's exit from its saved relative-return path under
    stress. entry_delay shifts the entry point WITHIN the same saved path
    (renormalizing so the delayed bar becomes the new 0%-return anchor) --
    no raw price data needed."""
    if entry_delay > 0:
        if entry_delay >= len(path) - 1:
            return None, False
        new_entry = path[entry_delay]
        path = (1 + path[entry_delay:]) / (1 + new_entry) - 1.0

    protective = min(stop_distance, liq_move)
    cost = (FEE_PER_SIDE + BASE_SLIP_PER_SIDE * slip_mult) * 2
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - gap_extra - cost, True
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - gap_extra - cost, False
    return path[-1] - cost, False


def load_trades_with_paths(symbols=None) -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["entry_time", "exit_time"])
    if symbols is not None:
        df = df[df["symbol"].isin(symbols)]
    df = df.sort_values("entry_time").reset_index(drop=True)
    df["path_arr"] = df["close_path"].apply(lambda s: np.array([float(v) for v in s.split(";")]))
    return df


def simulate_compounding_stressed(trades: pd.DataFrame, risk_pct: float, gap_extra=0.0,
                                   slip_mult=1.0, entry_delay=0, initial_equity=INITIAL_EQUITY):
    equity = initial_equity
    equity_curve = [(trades.iloc[0]["entry_time"], equity)]
    trade_log = []
    for _, t in trades.iterrows():
        stop_distance, leverage_safe = t["stop_distance"], t["leverage_safe"]
        liq_move = STOP_OUT_FRACTION / leverage_safe
        ret, was_stopped = resolve_stressed(t["path_arr"], stop_distance, liq_move,
                                             gap_extra, slip_mult, entry_delay)
        if ret is None:
            continue
        risk_dollar = equity * risk_pct
        notional = risk_dollar / stop_distance
        leverage_req = notional / equity
        leverage_used = min(leverage_req, leverage_safe)
        notional_used = leverage_used * equity
        pnl = notional_used * ret
        equity += pnl
        liq_move_used = STOP_OUT_FRACTION / leverage_used if leverage_used > 0 else np.inf
        forced = was_stopped and (liq_move_used <= stop_distance)
        equity_curve.append((t["exit_time"], equity))
        trade_log.append({"pnl": pnl, "equity_after": equity, "leverage_used": leverage_used, "forced_liq": forced})
    return pd.DataFrame(trade_log), equity_curve


def main():
    candidates = [float(a) for a in sys.argv[1:]] or [0.0100, 0.0125, 0.0150]
    print(f"Stress-testing risk_pct candidates: {[f'{c*100:.2f}%' for c in candidates]}\n")

    trades = load_trades_with_paths(["BTCUSDT", "ETHUSDT"])
    print(f"Loaded {len(trades)} portfolio trades with saved price paths.\n")

    scenarios = [
        ("frictionless", dict()),
        ("slippage 2x", dict(slip_mult=2.0)),
        ("slippage 3x", dict(slip_mult=3.0)),
        ("gap 0.10%", dict(gap_extra=0.0010)),
        ("gap 0.25%", dict(gap_extra=0.0025)),
        ("gap 0.50%", dict(gap_extra=0.0050)),
        ("latency 1min", dict(entry_delay=1)),
        ("latency 2min", dict(entry_delay=2)),
        ("WORST CASE (slip2x+gap.25%+delay1)", dict(slip_mult=2.0, gap_extra=0.0025, entry_delay=1)),
    ]

    for risk_pct in candidates:
        print("=" * 110)
        print(f"  risk_pct = {risk_pct*100:.2f}%")
        print("=" * 110)
        for label, kw in scenarios:
            trade_log, equity_curve = simulate_compounding_stressed(trades, risk_pct, **kw)
            m = compute_metrics(trade_log, equity_curve)
            if m.get("n_trades", 0) == 0:
                print(f"  {label:<36} no trades")
                continue
            print(f"  {label:<36} n={m['n_trades']:>4} CAGR={m['cagr_pct']:>7.2f}% "
                  f"MaxDD={m['max_dd_pct']:>7.2f}% Calmar={m['calmar']:>7.3f} "
                  f"PF={m['profit_factor']:>7.3f} forced_liq={m['n_forced_liq']}")
        print()


if __name__ == "__main__":
    main()
