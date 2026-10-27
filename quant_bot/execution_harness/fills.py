"""Bar-level fill simulation for one trade.

Rules (harness v1):
* Signal on bar ``s`` (bar labelled by its open time, signal known at its close).
* ``entry_mode="next_open"`` (default): fill at the OPEN of bar ``j = s + 1 + latency_bars``.
  ``entry_mode="signal_close"`` exists ONLY to reconcile with legacy research
  (fill at close[s], not executable); it refuses latency > 0.
* Bars evaluated: ``j .. j + max_bars - 1`` where ``j = s + 1 + latency_bars``.
  The time exit fills at the CLOSE of the last evaluated bar.
* Protective stop / trailing stop are resting orders tested on the bar's
  low (long) or high (short). The level used on bar t is computed from the
  favourable extreme (peak) observed up to bar t-1 only; bar t's own high is
  folded into the peak AFTER the test. Fill = min(level, open) for a long,
  max(level, open) for a short (gap through the level fills at the open).
* A per-trade stop distance is used ONLY if ``rule.use_candidate_stop`` is True.
* There is no "exit at the stop level on a close breach" convention.
* Bars are positional (row ``i+1`` is the next bar). ``gap_in_window`` flags
  windows whose timestamps are not contiguous minutes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

ENTRY_MODES = ("next_open", "signal_close")


@dataclass(frozen=True)
class ExitRule:
    """Exit rule in return space relative to the entry price.

    stop_distance : protective stop distance (fraction, e.g. 0.03). None = no stop.
    use_candidate_stop : if True, a per-trade ``stop_distance`` (candidate column)
                    overrides ``stop_distance``. If False (default) the candidate's
                    stop is NEVER applied -- a rule without a stop has no stop (v1.1, review C1).
    trail_activation : trailing activates once peak favourable return >= this (None = no trailing).
    trail_distance : trailing level = peak - trail_distance.
    max_bars : time exit at the close of the max_bars-th evaluated bar.
    """
    max_bars: int
    stop_distance: Optional[float] = None
    use_candidate_stop: bool = False
    trail_activation: Optional[float] = None
    trail_distance: Optional[float] = None

    def __post_init__(self):
        if self.max_bars < 1:
            raise ValueError("max_bars must be >= 1")
        if (self.trail_activation is None) != (self.trail_distance is None):
            raise ValueError("trail_activation and trail_distance go together")


def simulate_trade(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray,
                   signal_idx: int, rule: ExitRule, side: int = 1,
                   stop_distance: Optional[float] = None,
                   entry_mode: str = "next_open", latency_bars: int = 0,
                   ts: Optional[np.ndarray] = None) -> Optional[dict]:
    """Simulate one trade on positional OHLC arrays.

    Returns None when the entry bar does not exist (signal at the end of data).
    Returned dict: entry_idx, entry_price, exit_idx, exit_price, exit_reason
    ('stop' | 'trail' | 'time' | 'end_of_data'), gross_ret (side-signed, fraction),
    mae_low_ret (worst adverse excursion in return, from lows/highs incl. exit bar),
    bars_held, gap_in_window.
    """
    if entry_mode not in ENTRY_MODES:
        raise ValueError(f"entry_mode must be one of {ENTRY_MODES}")
    if side not in (1, -1):
        raise ValueError("side must be +1 (long) or -1 (short)")
    if latency_bars < 0:
        raise ValueError("latency_bars must be >= 0")
    if entry_mode == "signal_close" and latency_bars:
        raise ValueError("signal_close is a reconciliation mode; latency is not allowed")
    n = len(c)
    first = signal_idx + 1 + latency_bars
    if signal_idx < 0 or first >= n:
        return None
    entry = float(o[first]) if entry_mode == "next_open" else float(c[signal_idx])
    sd = stop_distance if (rule.use_candidate_stop and stop_distance is not None) else rule.stop_distance
    stop = -sd if sd is not None else -np.inf
    trailing = rule.trail_activation is not None
    peak, active = -np.inf, False
    mae = 0.0
    last = min(first + rule.max_bars - 1, n - 1)

    def ret(px):
        return side * (px / entry - 1.0)

    exit_idx, exit_ret, reason = None, None, None
    for t in range(first, last + 1):
        if side == 1:
            adverse, favourable, op = ret(l[t]), ret(h[t]), ret(o[t])
        else:
            adverse, favourable, op = ret(h[t]), ret(l[t]), ret(o[t])
        level = max(stop, peak - rule.trail_distance) if (trailing and active) else stop
        if adverse <= level:
            # in return space a gap through the level shows as op < level
            exit_idx, exit_ret = t, min(level, op)
            reason = "trail" if (trailing and active and level > stop) else "stop"
            mae = min(mae, exit_ret)
            break
        mae = min(mae, adverse)
        peak = max(peak, favourable)
        if trailing:
            active = active or peak >= rule.trail_activation
    if exit_idx is None:
        exit_idx = last
        exit_ret = ret(c[last])
        reason = "time" if last == first + rule.max_bars - 1 else "end_of_data"
    exit_price = entry * (1.0 + side * exit_ret)
    gap = False
    if ts is not None:
        lo = signal_idx if entry_mode == "signal_close" else first
        span = (ts[exit_idx] - ts[lo]) / np.timedelta64(1, "m")
        gap = bool(span != exit_idx - lo)
    return {"entry_idx": first if entry_mode == "next_open" else signal_idx,
            "entry_price": entry, "exit_idx": int(exit_idx), "exit_price": float(exit_price),
            "exit_reason": reason, "gross_ret": float(exit_ret), "mae_ret": float(mae),
            "bars_held": int(exit_idx - first + 1), "gap_in_window": gap}
