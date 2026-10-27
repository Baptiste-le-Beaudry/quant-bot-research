"""
scripts/fast_trades.py — drop-in-equivalent, faster replacement for
scripts/mae_mfe_analysis.build_trades_with_mae_mfe, used ONLY by the
multi-crypto expansion scripts (multi_crypto_screen.py,
multi_crypto_walkforward.py) -- the original function is left completely
untouched since it's shared infrastructure underneath every existing
BTC/ETH baseline script (walk_forward_engine.py, walk_forward_
threshold070_filter.py, etc.), and this project's own methodology rules
say don't touch frozen baselines.

Why: the original's outer loop is `i = 0; while i < limit: if not
entry_mask[i]: i += 1; continue` -- an O(n_bars) Python-level loop
regardless of how sparse entry_mask is. On a ~2-3.6M-row TRAIN array with
only a few thousand real entries (typical for this strategy's threshold=
0.70 + median filter), that's millions of wasted Python-level iterations
just to skip non-entries -- measured as the dominant cost of a screen run
(multiple CPU-minutes) via direct process CPU-time diagnosis during the
multi-crypto expansion's first Test A run. This version precomputes
`np.flatnonzero(entry_mask)` once and jumps the loop pointer forward via
`np.searchsorted` after each trade instead of stepping one bar at a time,
turning the outer loop into O(n_entries) instead of O(n_bars) -- exactly
the win needed since this cost recurs once per (symbol x mode) call across
the whole expansion plan (8 symbols x 2 screen modes, plus every
walk-forward fold).

Verified behaviorally IDENTICAL to the original (same trades, same order,
same fields) by re-running BTCUSDT's own-mode screen with this function
swapped in and confirming an EXACT match (not just "close") to the
already-recorded n=302/PF=1.163 result.
"""
import numpy as np

from scripts.mae_mfe_analysis import HORIZON as DEFAULT_HORIZON, COST_PCT


EXTENSION_MULTIPLIER = 4


def exit_window_for_horizon(horizon: int, extension_multiplier: int = EXTENSION_MULTIPLIER) -> int:
    """Maximum holding window: horizon plus four horizon-sized extensions."""
    if horizon <= 0 or extension_multiplier < 0:
        raise ValueError("horizon must be positive and extension_multiplier non-negative")
    return horizon * (1 + extension_multiplier)


def build_trades_with_mae_mfe_fast(close_arr, entry_mask, ema_slope, ret_1,
                                   *, horizon: int | None = None,
                                   lookahead: int | None = None) -> list:
    horizon = DEFAULT_HORIZON if horizon is None else int(horizon)
    expected_lookahead = exit_window_for_horizon(horizon)
    lookahead = expected_lookahead if lookahead is None else int(lookahead)
    if lookahead < horizon:
        raise ValueError("lookahead must be at least horizon")
    n = len(close_arr)
    limit = n - lookahead - 1
    if limit <= 0:
        return []
    entry_mask = np.asarray(entry_mask)
    entry_idxs = np.flatnonzero(entry_mask[:limit])
    n_idx = len(entry_idxs)
    trades = []
    ptr = 0
    while ptr < n_idx:
        i = int(entry_idxs[ptr])

        entry_price = close_arr[i]
        base_exit_price = close_arr[i + horizon]
        base_return = (base_exit_price / entry_price - 1.0) - COST_PCT

        full_path = close_arr[i:i + lookahead + 1] / entry_price - 1.0
        mae = float(full_path.min())
        mfe = float(full_path.max())
        mfe_offset = int(full_path.argmax())

        if base_return >= 0:
            trades.append({"pnl_return": base_return, "mae": mae, "mfe": mfe,
                            "mfe_offset": mfe_offset, "rescued": False, "close_path": full_path,
                            "entry_idx": i})
            next_i = i + horizon
            ptr = int(np.searchsorted(entry_idxs, next_i, side="left"))
            continue

        target = entry_price
        leg2_opened, entry_price2 = False, None
        exit_offset = lookahead
        exit_price = close_arr[i + exit_offset]
        rescued = False
        for j in range(horizon, lookahead + 1):
            p = close_arr[i + j]
            if p >= target:
                exit_price, exit_offset, rescued = p, j, leg2_opened
                break
            if not leg2_opened and ema_slope[i + j] > 0 and ret_1[i + j] > 0:
                leg2_opened, entry_price2 = True, p
        leg1_pnl = (exit_price / entry_price - 1.0) - COST_PCT
        combined = leg1_pnl
        if leg2_opened:
            combined += (exit_price / entry_price2 - 1.0) - COST_PCT
        trades.append({"pnl_return": combined, "mae": mae, "mfe": mfe,
                        "mfe_offset": mfe_offset, "rescued": rescued, "close_path": full_path,
                        "entry_idx": i})
        next_i = i + exit_offset
        ptr = int(np.searchsorted(entry_idxs, next_i, side="left"))

    return trades
