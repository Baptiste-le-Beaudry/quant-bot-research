"""
scripts/diagnostic_leverage.py — what happens to the best ETH config
(filtered entries, dca_rescue_trend exit) under leverage, done properly:
not just multiplying the % return by the leverage ratio (meaningless --
ignores that the position would get liquidated first), but checking each
trade's actual max adverse excursion (MAE) against what a given leverage
level's margin can absorb before a broker forces the position closed.

Standard retail CFD/futures broker mechanics: at leverage L, margin per
unit notional is 1/L. A broker's maintenance-margin stop-out typically
kicks in once realized loss reaches somewhere around 50-80% of margin, not
100% (they close you out before you can owe them money) -- this uses 50%
as a conservative (i.e., triggers stop-out EARLIER, giving leverage every
benefit of the doubt) approximation: liquidation happens once the adverse
move against a leg reaches 0.5/L.

Usage:
    python scripts/diagnostic_leverage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOL = "ETHUSDT"
TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
EXTENSION_CAP = 40
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
RISK_PCT = 0.01
CAPITAL = 10_000.0
STOP_OUT_FRACTION = 0.5  # broker closes you out at 50% margin loss, not 100%
LEVERAGES = [1, 10, 15, 25, 50, 100, 200, 500]
TARGET_LEVERAGE = 15


def build_trades_with_mae(close_arr: np.ndarray, entry_mask: np.ndarray,
                           ema_slope: np.ndarray, ret_1: np.ndarray) -> list[dict]:
    """Replays dca_rescue_trend exactly (same logic as diagnostic_exit_strategies.py)
    but additionally tracks each leg's own max adverse excursion (MAE) along
    its price path -- needed to check margin survival, which the P&L-only
    version didn't track."""
    n = len(close_arr)
    trades = []
    i = 0
    while i < n - HORIZON - EXTENSION_CAP - 1:
        if not entry_mask[i]:
            i += 1
            continue

        entry_price = close_arr[i]
        base_exit_price = close_arr[i + HORIZON]
        base_return = (base_exit_price / entry_price - 1.0) - COST_PCT
        leg1_path = close_arr[i:i + HORIZON + 1] / entry_price - 1.0
        leg1_mae = float(leg1_path.min())

        if base_return >= 0:
            trades.append({"pnl_return": base_return, "leg1_mae": leg1_mae, "leg2_mae": None, "rescued": False})
            i += HORIZON
            continue

        target = entry_price
        leg2_opened, entry_price2, leg2_start_offset = False, None, None
        exit_offset = HORIZON + EXTENSION_CAP
        exit_price = close_arr[i + exit_offset]
        rescued = False
        for j in range(HORIZON, HORIZON + EXTENSION_CAP + 1):
            p = close_arr[i + j]
            if p >= target:
                exit_price, exit_offset, rescued = p, j, leg2_opened
                break
            if not leg2_opened and ema_slope[i + j] > 0 and ret_1[i + j] > 0:
                leg2_opened, entry_price2, leg2_start_offset = True, p, j

        full_path = close_arr[i:i + exit_offset + 1] / entry_price - 1.0
        leg1_mae = float(full_path.min())  # leg 1 lives the whole time
        leg1_pnl = (exit_price / entry_price - 1.0) - COST_PCT

        if leg2_opened:
            leg2_path = close_arr[i + leg2_start_offset:i + exit_offset + 1] / entry_price2 - 1.0
            leg2_mae = float(leg2_path.min())
            leg2_pnl = (exit_price / entry_price2 - 1.0) - COST_PCT
            combined_return = leg1_pnl + leg2_pnl  # in units of "1 leg notional"
        else:
            leg2_mae = None
            combined_return = leg1_pnl

        trades.append({"pnl_return": combined_return, "leg1_mae": leg1_mae,
                        "leg2_mae": leg2_mae, "rescued": rescued})
        i += exit_offset

    return trades


def simulate_leveraged_trades(close_arr: np.ndarray, entry_mask: np.ndarray,
                               ema_slope: np.ndarray, ret_1: np.ndarray, leverage: float) -> list[dict]:
    """Bar-by-bar replay of dca_rescue_trend WITH a real stop-out check on
    both legs at the given leverage -- not an MAE-vs-threshold approximation
    like leverage_analysis(), this actually walks the price path and closes
    each leg the instant it breaches its own margin, exactly like a broker
    would. This is what answers "what would leverage=X actually have
    returned," not just "how risky does it look.\""""
    n = len(close_arr)
    stop_out_move = STOP_OUT_FRACTION / leverage
    trades = []
    i = 0
    while i < n - HORIZON - EXTENSION_CAP - 1:
        if not entry_mask[i]:
            i += 1
            continue

        entry_price = close_arr[i]
        leg1_stopped, leg1_exit_return = False, None
        leg2_opened, entry_price2, leg2_stopped, leg2_exit_return = False, None, False, None
        target = entry_price
        final_j = HORIZON + EXTENSION_CAP

        for j in range(0, HORIZON + EXTENSION_CAP + 1):
            p = close_arr[i + j]

            if not leg1_stopped:
                move = p / entry_price - 1.0
                if move <= -stop_out_move:
                    leg1_stopped, leg1_exit_return = True, -stop_out_move - COST_PCT

            if leg2_opened and not leg2_stopped:
                move2 = p / entry_price2 - 1.0
                if move2 <= -stop_out_move:
                    leg2_stopped, leg2_exit_return = True, -stop_out_move - COST_PCT

            # only look for target/rescue logic once past the base horizon,
            # and only for legs still open
            if j >= HORIZON:
                if not leg1_stopped and leg1_exit_return is None and p >= target:
                    leg1_exit_return = (p / entry_price - 1.0) - COST_PCT
                if leg2_opened and not leg2_stopped and leg2_exit_return is None and p >= target:
                    leg2_exit_return = (p / entry_price2 - 1.0) - COST_PCT
                if (not leg2_opened and not leg1_stopped and leg1_exit_return is None
                        and ema_slope[i + j] > 0 and ret_1[i + j] > 0):
                    leg2_opened, entry_price2 = True, p

            if (leg1_stopped or leg1_exit_return is not None) and (
                    not leg2_opened or leg2_stopped or leg2_exit_return is not None):
                final_j = j
                break
        else:
            # cap reached with something still open -- close at cap price
            p = close_arr[i + final_j]
            if leg1_exit_return is None and not leg1_stopped:
                leg1_exit_return = (p / entry_price - 1.0) - COST_PCT
            if leg2_opened and leg2_exit_return is None and not leg2_stopped:
                leg2_exit_return = (p / entry_price2 - 1.0) - COST_PCT

        r1 = leg1_exit_return if leg1_exit_return is not None else -stop_out_move - COST_PCT
        combined = r1 + (leg2_exit_return if (leg2_opened and leg2_exit_return is not None) else 0.0)
        trades.append({
            "pnl_return": combined,
            "leg1_stopped": leg1_stopped,
            "leg2_stopped": leg2_opened and leg2_stopped,
            "rescued": leg2_opened,
        })
        i += final_j if final_j > 0 else HORIZON

    return trades


def leverage_analysis(trades: list[dict]) -> None:
    leg1_maes = np.array([abs(t["leg1_mae"]) for t in trades])
    leg2_maes = np.array([abs(t["leg2_mae"]) for t in trades if t["leg2_mae"] is not None])

    print(f"n_trades={len(trades)}")
    print(f"Leg 1 MAE (adverse excursion vs entry): avg={leg1_maes.mean()*100:.4f}%, "
          f"worst={leg1_maes.max()*100:.4f}%, median={np.median(leg1_maes)*100:.4f}%")
    if len(leg2_maes) > 0:
        print(f"Leg 2 MAE (n={len(leg2_maes)} trades with a rescue leg): "
              f"avg={leg2_maes.mean()*100:.4f}%, worst={leg2_maes.max()*100:.4f}%")

    print(f"\nImplied leverage at which even the AVERAGE trade's own worst moment "
          f"would trigger a stop-out (stop-out at {STOP_OUT_FRACTION*100:.0f}% margin loss):")
    print(f"  Leg 1: {STOP_OUT_FRACTION / leg1_maes.mean():.1f}x")
    if len(leg2_maes) > 0:
        print(f"  Leg 2: {STOP_OUT_FRACTION / leg2_maes.mean():.1f}x")

    print()
    header2 = f"{'leverage':>10}{'leg1_stopped_out':>18}{'leg1_%':>9}"
    if len(leg2_maes) > 0:
        header2 += f"{'leg2_stopped_out':>18}{'leg2_%':>9}"
    print(header2)
    print("-" * len(header2))
    for lev in LEVERAGES:
        stop_out_move = STOP_OUT_FRACTION / lev
        leg1_stopped = int((leg1_maes > stop_out_move).sum())
        row = f"{lev:>10}{leg1_stopped:>18}{leg1_stopped/len(leg1_maes)*100:>8.1f}%"
        if len(leg2_maes) > 0:
            leg2_stopped = int((leg2_maes > stop_out_move).sum())
            row += f"{leg2_stopped:>18}{leg2_stopped/len(leg2_maes)*100:>8.1f}%"
        print(row)

    returns = np.array([t["pnl_return"] for t in trades])
    notional_1x = CAPITAL * RISK_PCT
    naive_pnl_500x = (returns * notional_1x * 500).sum()
    print(f"\nNaive 500x (just scales notional, ignores stop-outs entirely): "
          f"${naive_pnl_500x:,.0f} ({naive_pnl_500x/CAPITAL*100:,.0f}% of capital) -- fiction, see below.")


def report_leveraged(trades: list[dict], leverage: float) -> None:
    notional_1x = CAPITAL * RISK_PCT
    returns = np.array([t["pnl_return"] for t in trades])
    pnl_dollars = returns * notional_1x * leverage
    total_pnl = pnl_dollars.sum()
    n_leg1_stopped = sum(t["leg1_stopped"] for t in trades)
    n_leg2_stopped = sum(t["leg2_stopped"] for t in trades)
    n_rescued = sum(t["rescued"] for t in trades)
    wins = pnl_dollars[pnl_dollars > 0]
    losses = pnl_dollars[pnl_dollars <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")

    print(f"n_trades={len(trades)}")
    print(f"Win rate: {(pnl_dollars > 0).mean()*100:.1f}% | Profit factor: {pf:.3f}")
    print(f"Leg 1 stopped out (before reaching its exit): {n_leg1_stopped}/{len(trades)} "
          f"({n_leg1_stopped/len(trades)*100:.1f}%)")
    if n_rescued:
        print(f"Rescue leg opened: {n_rescued}/{len(trades)} trades, "
              f"of which stopped out: {n_leg2_stopped}/{n_rescued}")
    print(f"Worst single trade: ${pnl_dollars.min():,.2f} ({pnl_dollars.min()/CAPITAL*100:.2f}% of capital)")
    print(f"Best single trade:  ${pnl_dollars.max():,.2f} ({pnl_dollars.max()/CAPITAL*100:.2f}% of capital)")
    print(f"\nTOTAL P&L at {leverage}x leverage: ${total_pnl:,.2f} "
          f"({total_pnl/CAPITAL*100:+.2f}% of capital) over the ETHUSDT VALIDATION period")


def main():
    print("Fitting tier-2 classifier, horizon=10min (identical to prior ETH runs)...")
    train_feats, train_labels = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.")

    train_df_eth = load_split("ETHUSDT", "train", verbose=False)
    train_feats_eth = build_feature_matrix(train_df_eth)
    train_proba_eth = model.predict_proba(train_feats_eth)
    train_selected_eth = train_proba_eth > THRESHOLD
    range_pos_cut = train_feats_eth.loc[train_selected_eth, "range_pos_60"].median()
    vol_cut = train_feats_eth.loc[train_selected_eth, "realized_vol_30"].median()

    df_val = load_split(SYMBOL, "validation", verbose=False)
    feats_val = build_feature_matrix(df_val)
    close_val = df_val["close"]
    proba = model.predict_proba(feats_val)
    filtered_mask = (
        (proba > THRESHOLD)
        & (feats_val["range_pos_60"] < range_pos_cut)
        & (feats_val["realized_vol_30"] > vol_cut)
    ).to_numpy()

    close_arr = close_val.to_numpy()
    ema_slope_arr = feats_val["ema_slope_20"].to_numpy()
    ret_1_arr = feats_val["ret_1"].to_numpy()

    trades = build_trades_with_mae(close_arr, filtered_mask, ema_slope_arr, ret_1_arr)

    print("\n" + "=" * 70)
    print(f"  LEVERAGE REALITY CHECK — {SYMBOL}, filtered + dca_rescue_trend")
    print("=" * 70)
    leverage_analysis(trades)

    print("\n" + "=" * 70)
    print(f"  PRECISE BAR-BY-BAR SIMULATION AT {TARGET_LEVERAGE}x LEVERAGE")
    print("=" * 70)
    print("(sanity check: same simulation at 1x should reproduce the un-leveraged result)")
    trades_1x = simulate_leveraged_trades(close_arr, filtered_mask, ema_slope_arr, ret_1_arr, leverage=1)
    report_leveraged(trades_1x, leverage=1)

    print(f"\n--- at {TARGET_LEVERAGE}x ---")
    trades_15x = simulate_leveraged_trades(close_arr, filtered_mask, ema_slope_arr, ret_1_arr, leverage=TARGET_LEVERAGE)
    report_leveraged(trades_15x, leverage=TARGET_LEVERAGE)


if __name__ == "__main__":
    main()
